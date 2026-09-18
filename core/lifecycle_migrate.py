"""Safe legacy status → lifecycle event backfill (PR30).

Keeps existing ``application_cases.status`` readable. Snapshots into
``legacy_status`` and seeds one lifecycle event per case when the event
log is empty. Unmappable statuses are left untouched (rollback path:
continue reading ``legacy_status`` / ``status``).
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any

from core.lifecycle import (
    CANONICAL_CASE_STATUSES,
    CaseStatus,
    seed_event_for_status,
)
from core.models import utc_now_iso


def ensure_lifecycle_schema(conn: sqlite3.Connection) -> None:
    """Idempotent DDL for lifecycle_events + legacy_status."""
    case_cols = {
        row[1] for row in conn.execute("PRAGMA table_info(application_cases)").fetchall()
    }
    if case_cols and "legacy_status" not in case_cols:
        conn.execute(
            "ALTER TABLE application_cases ADD COLUMN legacy_status TEXT DEFAULT ''"
        )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS lifecycle_events (
            id TEXT PRIMARY KEY,
            case_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            occurred_at TEXT NOT NULL,
            recorded_at TEXT NOT NULL,
            idempotency_key TEXT DEFAULT '',
            payload_json TEXT DEFAULT '{}',
            source TEXT DEFAULT '',
            confidence REAL DEFAULT 1.0,
            FOREIGN KEY(case_id) REFERENCES application_cases(id)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_lifecycle_events_case ON lifecycle_events(case_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_lifecycle_events_occurred "
        "ON lifecycle_events(case_id, occurred_at)"
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_lifecycle_events_idem
        ON lifecycle_events(case_id, idempotency_key)
        WHERE idempotency_key != ''
        """
    )


def backfill_legacy_statuses(conn: sqlite3.Connection) -> dict[str, Any]:
    """Backfill seed events. Never deletes history. Returns stats.

    On failure / unmapped status: leaves row status intact for read-only use.
    """
    ensure_lifecycle_schema(conn)
    stats = {
        "cases_seen": 0,
        "seeded": 0,
        "skipped_existing_events": 0,
        "unmapped": 0,
        "unmapped_statuses": [],
    }
    conn.execute(
        """
        UPDATE application_cases
        SET legacy_status = status
        WHERE COALESCE(legacy_status, '') = ''
          AND COALESCE(status, '') != ''
        """
    )
    rows = conn.execute(
        "SELECT id, status, legacy_status, created_at, updated_at, applied_at "
        "FROM application_cases"
    ).fetchall()
    for row in rows:
        stats["cases_seen"] += 1
        case_id = row["id"]
        existing = conn.execute(
            "SELECT COUNT(*) AS c FROM lifecycle_events WHERE case_id = ?",
            (case_id,),
        ).fetchone()
        if existing and int(existing["c"] or 0) > 0:
            stats["skipped_existing_events"] += 1
            continue
        status = (row["legacy_status"] or row["status"] or "").strip().lower()
        if status and status not in CANONICAL_CASE_STATUSES:
            stats["unmapped"] += 1
            stats["unmapped_statuses"].append({"case_id": case_id, "status": status})
            continue
        status = status or CaseStatus.TO_APPLY.value
        seed = seed_event_for_status(status)
        if not seed:
            stats["unmapped"] += 1
            stats["unmapped_statuses"].append({"case_id": case_id, "status": status})
            continue
        occurred = (
            row["applied_at"] or row["created_at"] or row["updated_at"] or utc_now_iso()
        )
        recorded = row["updated_at"] or occurred
        conn.execute(
            """
            INSERT OR IGNORE INTO lifecycle_events (
                id, case_id, event_type, occurred_at, recorded_at,
                idempotency_key, payload_json, source, confidence
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                case_id,
                seed,
                occurred,
                recorded,
                f"backfill:{case_id}:{seed}:{status}",
                json.dumps(
                    {
                        "backfill": True,
                        "legacy_status": status,
                        "from": "migration",
                    },
                    ensure_ascii=False,
                ),
                "migration_backfill",
                1.0,
            ),
        )
        stats["seeded"] += 1
    return stats


def migrate_database_file(path: Path) -> dict[str, Any]:
    """Run backfill against a SQLite file path."""
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    try:
        return backfill_legacy_statuses(conn)
    finally:
        conn.commit()
        conn.close()
