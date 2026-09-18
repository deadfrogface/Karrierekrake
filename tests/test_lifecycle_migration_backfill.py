"""Migration / backfill tests for PR30 lifecycle events."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from core.database import Database
from core.lifecycle import ApplicationCase, CaseStatus, LifecycleEventType
from core.lifecycle_migrate import backfill_legacy_statuses, migrate_database_file


def test_backfill_preserves_legacy_status_and_seeds_event(tmp_path: Path):
    db_path = tmp_path / "legacy.db"
    # Simulate pre-PR30 DB: cases without lifecycle_events / legacy_status.
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE application_cases (
            id TEXT PRIMARY KEY,
            job_id TEXT DEFAULT '',
            company TEXT,
            position TEXT,
            status TEXT DEFAULT 'to_apply',
            source TEXT DEFAULT '',
            url TEXT DEFAULT '',
            application_url TEXT DEFAULT '',
            contact_email TEXT DEFAULT '',
            contact_name TEXT DEFAULT '',
            contact_phone TEXT DEFAULT '',
            applied_at TEXT DEFAULT '',
            updated_at TEXT,
            created_at TEXT,
            notes TEXT DEFAULT '',
            company_key TEXT DEFAULT '',
            title_key TEXT DEFAULT '',
            url_key TEXT DEFAULT ''
        );
        INSERT INTO application_cases (
            id, company, position, status, created_at, updated_at, applied_at
        ) VALUES (
            'c1', 'Acme', 'Dev', 'rejected',
            '2026-01-01T00:00:00Z', '2026-01-02T00:00:00Z', '2026-01-01T12:00:00Z'
        );
        INSERT INTO application_cases (
            id, company, position, status, created_at, updated_at
        ) VALUES (
            'c2', 'Beta', 'QA', 'interview',
            '2026-01-01T00:00:00Z', '2026-01-03T00:00:00Z'
        );
        """
    )
    conn.commit()
    conn.close()

    stats = migrate_database_file(db_path)
    assert stats["cases_seen"] == 2
    assert stats["seeded"] == 2
    assert stats["unmapped"] == 0

    # Opening via Database must not wipe history / status.
    db = Database(db_path)
    c1 = db.get_case("c1")
    assert c1 is not None
    assert c1.status == CaseStatus.REJECTED.value
    assert c1.legacy_status == CaseStatus.REJECTED.value
    events = db.list_lifecycle_events("c1")
    assert len(events) >= 1
    assert events[0].event_type == LifecycleEventType.REJECTION_RECEIVED.value

    c2 = db.get_case("c2")
    assert c2 is not None
    assert c2.status == CaseStatus.INTERVIEW.value
    assert any(
        e.event_type == LifecycleEventType.INTERVIEW_REQUESTED.value
        for e in db.list_lifecycle_events("c2")
    )


def test_backfill_skips_when_events_exist(tmp_path: Path):
    db = Database(tmp_path / "fresh.db")
    case = db.upsert_case(
        ApplicationCase(
            company="X",
            position="Y",
            status=CaseStatus.APPLIED.value,
        )
    )
    db.apply_lifecycle_event_for_email(
        case.id,
        LifecycleEventType.REJECTION_RECEIVED.value,
        email_id="e1",
    )
    before = len(db.list_lifecycle_events(case.id))
    with db.connection() as conn:
        stats = backfill_legacy_statuses(conn)
    assert stats["skipped_existing_events"] >= 1
    assert len(db.list_lifecycle_events(case.id)) == before


def test_rollback_path_legacy_status_readable_without_events(tmp_path: Path):
    """If event reduce fails / empty, status stays available via legacy_status."""
    db = Database(tmp_path / "roll.db")
    case = db.upsert_case(
        ApplicationCase(
            company="Roll",
            position="Back",
            status=CaseStatus.OFFER.value,
            legacy_status=CaseStatus.OFFER.value,
        )
    )
    # Wipe events to simulate migration failure cleanup path.
    with db.connection() as conn:
        conn.execute("DELETE FROM lifecycle_events WHERE case_id = ?", (case.id,))
    refreshed = db.recompute_case_status(case.id)
    assert refreshed is not None
    assert refreshed.status == CaseStatus.OFFER.value
