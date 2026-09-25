"""SQLite persistence for Karrierekrake."""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from core.models import ApplicationRecord, Job, JobStatus, utc_now_iso
from core.deduplicator import company_key as _company_key, title_key as _title_key
from core.lifecycle import (
    ApplicationCase,
    CaseEvent,
    CaseEventType,
    CaseStatus,
    LifecycleEvent,
    LifecycleEventType,
    can_transition,
    reduce_lifecycle_events,
    seed_event_for_status,
    status_to_lifecycle_event,
)

from urllib.parse import parse_qs, urlparse


def _url_identity(url: str) -> str:
    """Stable identity for job URLs (Indeed jk=, strip tracking params)."""
    raw = (url or "").strip()
    if not raw:
        return ""
    try:
        parsed = urlparse(raw)
    except Exception:
        return raw.lower()
    host = (parsed.netloc or "").lower()
    path = (parsed.path or "").rstrip("/").lower()
    qs = parse_qs(parsed.query or "")
    if "jk" in qs and qs["jk"]:
        return f"indeed:jk:{qs['jk'][0].lower()}"
    # Drop common tracking params
    keep = []
    for key in sorted(qs):
        if key.lower() in {"utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term", "from", "ref", "si"}:
            continue
        for val in qs[key]:
            keep.append(f"{key.lower()}={val.lower()}")
    query = "&".join(keep)
    return f"{host}{path}?{query}" if query else f"{host}{path}"


SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    source TEXT,
    source_job_id TEXT,
    title TEXT,
    company TEXT,
    description TEXT,
    city TEXT,
    postal_code TEXT,
    address TEXT,
    country_code TEXT DEFAULT '',
    latitude REAL,
    longitude REAL,
    distance_km REAL,
    commute_duration_minutes REAL,
    distance_source TEXT DEFAULT '',
    remote_type TEXT,
    employment_type TEXT,
    salary_min REAL,
    salary_max REAL,
    salary_text TEXT,
    published_at TEXT,
    discovered_at TEXT,
    url TEXT,
    application_url TEXT,
    ats_type TEXT,
    match_score INTEGER DEFAULT 0,
    match_reasons TEXT DEFAULT '[]',
    rejection_reasons TEXT DEFAULT '[]',
    status TEXT DEFAULT 'new',
    duplicate_of TEXT,
    alt_sources TEXT DEFAULT '[]',
    run_id TEXT DEFAULT '',
    ranking_version TEXT DEFAULT '',
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS applications (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    company TEXT,
    position TEXT,
    application_date TEXT,
    platform TEXT,
    status TEXT,
    cv_used TEXT,
    cover_letter_used TEXT,
    result TEXT,
    error_message TEXT,
    FOREIGN KEY(job_id) REFERENCES jobs(id)
);

CREATE TABLE IF NOT EXISTS geocode_cache (
    query TEXT PRIMARY KEY,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    display_name TEXT,
    cached_at TEXT,
    data_source TEXT DEFAULT '',
    data_version TEXT DEFAULT '',
    country_code TEXT DEFAULT '',
    resolution_status TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS source_status (
    source TEXT PRIMARY KEY,
    status TEXT,
    message TEXT,
    checked_at TEXT,
    jobs_found INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS search_runs (
    id TEXT PRIMARY KEY,
    started_at TEXT,
    finished_at TEXT,
    status TEXT,
    stats_json TEXT DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_company_title ON jobs(company, title);
CREATE INDEX IF NOT EXISTS idx_jobs_match ON jobs(match_score DESC);
CREATE INDEX IF NOT EXISTS idx_apps_job ON applications(job_id);
-- Query patterns: find_by_source, has_applied URL/status, dashboard date counts
CREATE INDEX IF NOT EXISTS idx_jobs_source_job_id ON jobs(source, source_job_id);
CREATE INDEX IF NOT EXISTS idx_jobs_discovered ON jobs(discovered_at);
CREATE INDEX IF NOT EXISTS idx_jobs_url ON jobs(url);
CREATE INDEX IF NOT EXISTS idx_apps_date ON applications(application_date);
CREATE INDEX IF NOT EXISTS idx_apps_status ON applications(status);

CREATE TABLE IF NOT EXISTS application_cases (
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
    url_key TEXT DEFAULT '',
    legacy_status TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS case_events (
    id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload_json TEXT DEFAULT '{}',
    created_at TEXT,
    confidence REAL DEFAULT 1.0,
    FOREIGN KEY(case_id) REFERENCES application_cases(id)
);

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
);

CREATE TABLE IF NOT EXISTS email_messages (
    id TEXT PRIMARY KEY,
    gmail_id TEXT DEFAULT '',
    thread_id TEXT DEFAULT '',
    subject TEXT DEFAULT '',
    sender TEXT DEFAULT '',
    body_text TEXT DEFAULT '',
    category TEXT DEFAULT '',
    confidence REAL DEFAULT 0,
    case_id TEXT DEFAULT '',
    association_status TEXT DEFAULT 'unlinked',
    association_policy_version TEXT DEFAULT '',
    association_explanation TEXT DEFAULT '',
    association_evidence_json TEXT DEFAULT '[]',
    association_confirmed INTEGER DEFAULT 0,
    received_at TEXT DEFAULT '',
    created_at TEXT,
    UNIQUE(gmail_id)
);

CREATE TABLE IF NOT EXISTS lifecycle_tasks (
    id TEXT PRIMARY KEY,
    case_id TEXT DEFAULT '',
    kind TEXT DEFAULT '',
    title TEXT DEFAULT '',
    body TEXT DEFAULT '',
    status TEXT DEFAULT 'open',
    due_at TEXT DEFAULT '',
    created_at TEXT,
    auto_send INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS followup_reminders (
    id TEXT PRIMARY KEY,
    case_id TEXT DEFAULT '',
    kind TEXT DEFAULT '',
    title TEXT DEFAULT '',
    body TEXT DEFAULT '',
    status TEXT DEFAULT 'open',
    due_at TEXT DEFAULT '',
    created_at TEXT,
    fired_at TEXT DEFAULT '',
    auto_send INTEGER DEFAULT 0,
    schema_version INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_cases_status ON application_cases(status);
CREATE INDEX IF NOT EXISTS idx_cases_company_title ON application_cases(company_key, title_key);
CREATE INDEX IF NOT EXISTS idx_cases_url_key ON application_cases(url_key);
CREATE INDEX IF NOT EXISTS idx_cases_job ON application_cases(job_id);
CREATE INDEX IF NOT EXISTS idx_case_events_case ON case_events(case_id);
CREATE INDEX IF NOT EXISTS idx_lifecycle_events_case ON lifecycle_events(case_id);
CREATE INDEX IF NOT EXISTS idx_lifecycle_events_occurred ON lifecycle_events(case_id, occurred_at);
CREATE UNIQUE INDEX IF NOT EXISTS idx_lifecycle_events_idem
    ON lifecycle_events(case_id, idempotency_key)
    WHERE idempotency_key != '';
CREATE INDEX IF NOT EXISTS idx_email_case ON email_messages(case_id);
CREATE INDEX IF NOT EXISTS idx_email_assoc ON email_messages(association_status);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON lifecycle_tasks(status);
CREATE INDEX IF NOT EXISTS idx_followup_reminders_status ON followup_reminders(status);
CREATE INDEX IF NOT EXISTS idx_followup_reminders_case ON followup_reminders(case_id);

CREATE TABLE IF NOT EXISTS recruiting_contacts (
    id TEXT PRIMARY KEY,
    job_id TEXT DEFAULT '',
    case_id TEXT DEFAULT '',
    schema_version INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    source_type TEXT DEFAULT '',
    source_url TEXT DEFAULT '',
    discovered_at TEXT,
    invalidated_at TEXT DEFAULT '',
    cache_key TEXT DEFAULT '',
    contact_kind TEXT DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_recruiting_contacts_job ON recruiting_contacts(job_id);
CREATE INDEX IF NOT EXISTS idx_recruiting_contacts_case ON recruiting_contacts(case_id);
CREATE INDEX IF NOT EXISTS idx_recruiting_contacts_cache ON recruiting_contacts(cache_key);
CREATE INDEX IF NOT EXISTS idx_recruiting_contacts_status ON recruiting_contacts(status);
"""


class Database:
    def __init__(self, path: Path, *, recover: bool = False) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # (data_version, block keys). Watcher stays open so a cache hit does not
        # connect again. None until the first has_applied.
        self._applied_cache = None
        self._applied_watch: sqlite3.Connection | None = None
        self._init_schema()
        # Default off: GUI page opens construct Database() frequently and must not
        # mark a live search/apply as interrupted. Call with recover=True once at
        # app/pipeline start (crash heal).
        if recover:
            self.recover_interrupted_state()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        conn = self._connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self.connection() as conn:
            # 1) Base tables/indexes that are safe for both fresh and legacy DBs.
            #    Do NOT create idx_jobs_run_id here — legacy jobs tables lack run_id.
            conn.executescript(SCHEMA)

            # 2) Migrate older DBs that predate run_id / search_runs / ranking_version / DACH.
            cols = {row[1] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()}
            if "run_id" not in cols:
                conn.execute("ALTER TABLE jobs ADD COLUMN run_id TEXT DEFAULT ''")
            if "ranking_version" not in cols:
                conn.execute(
                    "ALTER TABLE jobs ADD COLUMN ranking_version TEXT DEFAULT ''"
                )
            if "country_code" not in cols:
                # Lazy-normalize on enrich; no mass backfill without backup.
                conn.execute(
                    "ALTER TABLE jobs ADD COLUMN country_code TEXT DEFAULT ''"
                )
            if "commute_duration_minutes" not in cols:
                conn.execute(
                    "ALTER TABLE jobs ADD COLUMN commute_duration_minutes REAL"
                )
            if "distance_source" not in cols:
                conn.execute(
                    "ALTER TABLE jobs ADD COLUMN distance_source TEXT DEFAULT ''"
                )

            # Geocode cache provenance (data_source / version) for DACH invalidation.
            geo_cols = {
                row[1]
                for row in conn.execute("PRAGMA table_info(geocode_cache)").fetchall()
            }
            if geo_cols:
                if "data_source" not in geo_cols:
                    conn.execute(
                        "ALTER TABLE geocode_cache ADD COLUMN data_source TEXT DEFAULT ''"
                    )
                if "data_version" not in geo_cols:
                    conn.execute(
                        "ALTER TABLE geocode_cache ADD COLUMN data_version TEXT DEFAULT ''"
                    )
                if "country_code" not in geo_cols:
                    conn.execute(
                        "ALTER TABLE geocode_cache ADD COLUMN country_code TEXT DEFAULT ''"
                    )
                if "resolution_status" not in geo_cols:
                    conn.execute(
                        "ALTER TABLE geocode_cache ADD COLUMN resolution_status TEXT DEFAULT ''"
                    )
                # Local-first migration: invalidate Google/Nominatim/empty-provenance rows.
                # Old API keys are never migrated; LocationService ignores stale sources.
                try:
                    conn.execute(
                        """
                        UPDATE geocode_cache
                        SET resolution_status = 'STALE',
                            data_source = 'stale_cleared',
                            data_version = '',
                            latitude = 0.0,
                            longitude = 0.0,
                            display_name = '__unresolved__'
                        WHERE lower(COALESCE(data_source, '')) IN (
                            '', 'google_geocoding', 'google_route_matrix',
                            'nominatim', 'maps', 'stale_cleared'
                        )
                        OR COALESCE(data_version, '') = ''
                        """
                    )
                    conn.execute(
                        """
                        DELETE FROM app_meta WHERE key IN (
                            'google_maps_api_key', 'maps_api_key',
                            'GOOGLE_MAPS_API_KEY', 'KARRIEREKRAKE_GOOGLE_MAPS_API_KEY',
                            'maps_proxy_token', 'maps_proxy_url'
                        )
                        """
                    )
                except Exception:
                    pass

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS search_runs (
                    id TEXT PRIMARY KEY,
                    started_at TEXT,
                    finished_at TEXT,
                    status TEXT,
                    stats_json TEXT DEFAULT '{}'
                )
                """
            )

            # 3) Index only after run_id is guaranteed to exist.
            cols = {row[1] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()}
            if "run_id" in cols:
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_jobs_run_id ON jobs(run_id)"
                )

            # 4) Invalidate cached match scores from older ranking/alias algorithms.
            self._invalidate_stale_ranking_scores(conn)

            # 5) Recruiting contact discovery store (PR25).
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS recruiting_contacts (
                    id TEXT PRIMARY KEY,
                    job_id TEXT DEFAULT '',
                    case_id TEXT DEFAULT '',
                    schema_version INTEGER NOT NULL DEFAULT 1,
                    status TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    source_type TEXT DEFAULT '',
                    source_url TEXT DEFAULT '',
                    discovered_at TEXT,
                    invalidated_at TEXT DEFAULT '',
                    cache_key TEXT DEFAULT '',
                    contact_kind TEXT DEFAULT ''
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_recruiting_contacts_job "
                "ON recruiting_contacts(job_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_recruiting_contacts_case "
                "ON recruiting_contacts(case_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_recruiting_contacts_cache "
                "ON recruiting_contacts(cache_key)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_recruiting_contacts_status "
                "ON recruiting_contacts(status)"
            )

            # 6) Email association policy metadata (PR29) — never auto-overwrite confirmed.
            email_cols = {
                row[1]
                for row in conn.execute("PRAGMA table_info(email_messages)").fetchall()
            }
            if email_cols:
                if "association_policy_version" not in email_cols:
                    conn.execute(
                        "ALTER TABLE email_messages ADD COLUMN "
                        "association_policy_version TEXT DEFAULT ''"
                    )
                if "association_explanation" not in email_cols:
                    conn.execute(
                        "ALTER TABLE email_messages ADD COLUMN "
                        "association_explanation TEXT DEFAULT ''"
                    )
                if "association_evidence_json" not in email_cols:
                    conn.execute(
                        "ALTER TABLE email_messages ADD COLUMN "
                        "association_evidence_json TEXT DEFAULT '[]'"
                    )
                if "association_confirmed" not in email_cols:
                    conn.execute(
                        "ALTER TABLE email_messages ADD COLUMN "
                        "association_confirmed INTEGER DEFAULT 0"
                    )

            self._ensure_lifecycle_event_schema(conn)
            self._backfill_lifecycle_events_if_needed(conn)

            # 7) PR32 follow-up reminders (restart-persistent; never auto-send).
            self._ensure_followup_reminders_schema(conn)

    @staticmethod
    def _ensure_lifecycle_event_schema(conn: sqlite3.Connection) -> None:
        case_cols = {
            row[1]
            for row in conn.execute("PRAGMA table_info(application_cases)").fetchall()
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

    @staticmethod
    def _backfill_lifecycle_events_if_needed(conn: sqlite3.Connection) -> None:
        case_cols = {
            row[1]
            for row in conn.execute("PRAGMA table_info(application_cases)").fetchall()
        }
        if "legacy_status" not in case_cols:
            return
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
            case_id = row["id"]
            existing = conn.execute(
                "SELECT COUNT(*) AS c FROM lifecycle_events WHERE case_id = ?",
                (case_id,),
            ).fetchone()
            if existing and int(existing["c"] or 0) > 0:
                continue
            status = (row["legacy_status"] or row["status"] or CaseStatus.TO_APPLY.value).strip()
            seed = seed_event_for_status(status)
            if not seed:
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
                        {"backfill": True, "legacy_status": status, "from": "migration"},
                        ensure_ascii=False,
                    ),
                    "migration_backfill",
                    1.0,
                ),
            )

    @staticmethod
    def _ensure_followup_reminders_schema(conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS followup_reminders (
                id TEXT PRIMARY KEY,
                case_id TEXT DEFAULT '',
                kind TEXT DEFAULT '',
                title TEXT DEFAULT '',
                body TEXT DEFAULT '',
                status TEXT DEFAULT 'open',
                due_at TEXT DEFAULT '',
                created_at TEXT,
                fired_at TEXT DEFAULT '',
                auto_send INTEGER DEFAULT 0,
                schema_version INTEGER NOT NULL DEFAULT 1
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_followup_reminders_status "
            "ON followup_reminders(status)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_followup_reminders_case "
            "ON followup_reminders(case_id)"
        )

    @staticmethod
    def _invalidate_stale_ranking_scores(conn: sqlite3.Connection) -> None:
        """Zero scores whose ranking_version does not match the current strategy.

        Never softens hard filters — only clears stale soft scores so rematch
        can recompute. Jobs already hard-ignored keep their status.
        """
        from core.intent_aliases import ranking_version_token

        current = ranking_version_token()
        cols = {row[1] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()}
        if "ranking_version" not in cols:
            return
        # Incomplete legacy stubs in tests may lack status/source_job_id — skip safely.
        required = {"match_score", "match_reasons", "ranking_version"}
        if not required.issubset(cols):
            return
        try:
            conn.execute(
                """
                UPDATE jobs
                SET match_score = 0,
                    match_reasons = '[]',
                    ranking_version = ''
                WHERE ranking_version IS NOT NULL
                  AND ranking_version != ''
                  AND ranking_version != ?
                """,
                (current,),
            )
        except Exception:
            return

    def recover_interrupted_state(self) -> None:
        """Heal rows left mid-flight after a crash / force-kill."""
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        with self.connection() as conn:
            conn.execute(
                "UPDATE jobs SET status = ?, updated_at = ? WHERE status = ?",
                ("needs_review", now, "applying"),
            )
            # Only status='running' — do not treat empty finished_at alone as interrupted
            # (live runs insert finished_at='' and must survive GUI Database() opens).
            try:
                conn.execute(
                    "UPDATE search_runs SET status = ?, finished_at = ? "
                    "WHERE status = ?",
                    ("interrupted", now, "running"),
                )
            except Exception:
                pass


    def upsert_job(self, job: Job) -> None:
        data = job.to_dict()
        data["match_reasons"] = json.dumps(job.match_reasons, ensure_ascii=False)
        data["rejection_reasons"] = json.dumps(job.rejection_reasons, ensure_ascii=False)
        data["alt_sources"] = json.dumps(job.alt_sources, ensure_ascii=False)
        data["updated_at"] = utc_now_iso()
        # Soft-dedup losers re-upsert with status=new — do not wipe attempt /
        # outcome rows (keeps has_applied twin blocks). Explicit transitions
        # (e.g. applying → applied/failed/needs_review/captcha) must still win.
        existing = self.get_job(job.id) if job.id else None
        protected = {
            JobStatus.APPLIED.value,
            JobStatus.FAILED.value,
            JobStatus.NEEDS_REVIEW.value,
            JobStatus.CAPTCHA.value,
            JobStatus.APPLYING.value,
        }
        incoming = data.get("status") or JobStatus.NEW.value
        # Soft-dedup uses NEW; rematch may try IGNORED/INTERESTING — neither
        # may erase a prior attempt/outcome (twins must stay blocked).
        wipe_statuses = {
            JobStatus.NEW.value,
            JobStatus.IGNORED.value,
            JobStatus.INTERESTING.value,
        }
        # APPLIED is terminal for automation — never demote via rematch, blocked
        # re-apply paths, or soft status noise.
        if existing and existing.status == JobStatus.APPLIED.value and incoming != JobStatus.APPLIED.value:
            data["status"] = existing.status
            job.status = existing.status
        elif (
            existing
            and existing.status in protected
            and incoming in wipe_statuses
        ):
            data["status"] = existing.status
            job.status = existing.status
        cols = list(data.keys())
        placeholders = ", ".join("?" for _ in cols)
        col_names = ", ".join(cols)
        updates = ", ".join(f"{c}=excluded.{c}" for c in cols if c != "id")
        sql = (
            f"INSERT INTO jobs ({col_names}) VALUES ({placeholders}) "
            f"ON CONFLICT(id) DO UPDATE SET {updates}"
        )
        with self.connection() as conn:
            conn.execute(sql, [data[c] for c in cols])

    def get_job(self, job_id: str) -> Job | None:
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return self._row_to_job(row) if row else None

    def list_jobs(
        self,
        *,
        min_match: int | None = None,
        max_distance: float | None = None,
        statuses: list[str] | None = None,
        hide_applied: bool = False,
        hide_duplicates: bool = True,
        remote_types: list[str] | None = None,
        source: str | None = None,
        company_query: str | None = None,
        title_query: str | None = None,
        city_query: str | None = None,
        limit: int = 500,
    ) -> list[Job]:
        clauses: list[str] = []
        params: list[Any] = []
        if min_match is not None:
            clauses.append("match_score >= ?")
            params.append(min_match)
        if max_distance is not None:
            # Remote always passes; hybrid/onsite need a known distance within radius.
            # NULL distance must not slip through (was: IS NULL OR …).
            clauses.append(
                "(remote_type = 'remote' OR (distance_km IS NOT NULL AND distance_km <= ?))"
            )
            params.append(max_distance)
        if statuses:
            clauses.append(f"status IN ({','.join('?' for _ in statuses)})")
            params.extend(statuses)
        if hide_applied:
            clauses.append("status != ?")
            params.append(JobStatus.APPLIED.value)
        if hide_duplicates:
            clauses.append("duplicate_of IS NULL")
        if remote_types:
            clauses.append(f"remote_type IN ({','.join('?' for _ in remote_types)})")
            params.extend(remote_types)
        if source:
            clauses.append("source = ?")
            params.append(source)
        if company_query:
            clauses.append("LOWER(company) LIKE ?")
            params.append(f"%{company_query.lower()}%")
        if title_query:
            clauses.append("LOWER(title) LIKE ?")
            params.append(f"%{title_query.lower()}%")
        if city_query:
            clauses.append("LOWER(city) LIKE ?")
            params.append(f"%{city_query.lower()}%")
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = (
            f"SELECT * FROM jobs{where} "
            "ORDER BY match_score DESC, discovered_at DESC LIMIT ?"
        )
        params.append(limit)
        with self.connection() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row_to_job(r) for r in rows]

    def update_job_status(self, job_id: str, status: str) -> None:
        """Update status with the same rematch protections as upsert_job.

        Soft/wipe statuses (new/ignored/interesting) must not erase attempt or
        outcome rows (applied/failed/needs_review/captcha/applying). APPLIED is
        terminal and must never be demoted via this API.
        """
        protected = {
            JobStatus.APPLIED.value,
            JobStatus.FAILED.value,
            JobStatus.NEEDS_REVIEW.value,
            JobStatus.CAPTCHA.value,
            JobStatus.APPLYING.value,
        }
        wipe_statuses = {
            JobStatus.NEW.value,
            JobStatus.IGNORED.value,
            JobStatus.INTERESTING.value,
        }
        incoming = status or JobStatus.NEW.value
        existing = self.get_job(job_id)
        if existing and existing.status == JobStatus.APPLIED.value and incoming != JobStatus.APPLIED.value:
            return
        if existing and existing.status in protected and incoming in wipe_statuses:
            return
        with self.connection() as conn:
            conn.execute(
                "UPDATE jobs SET status = ?, updated_at = ? WHERE id = ?",
                (incoming, utc_now_iso(), job_id),
            )

    def _applied_watcher(self) -> sqlite3.Connection:
        watch = self._applied_watch
        if watch is None:
            watch = self._connect()
            watch.rollback()
            self._applied_watch = watch
        return watch

    def _applied_block_keys(
        self,
    ) -> tuple[set[str], set[str], set[str], set[tuple[str, str]]]:
        """Normalized block keys. Rebuilt when another connection commits.

        ``PRAGMA data_version`` on the long-lived watcher changes for every
        commit except one made on the watcher itself. Hits do not open a
        connection. The watcher is rolled back so it does not keep a lock.
        """
        watch = self._applied_watcher()
        version = int(watch.execute("PRAGMA data_version").fetchone()[0])
        cached = self._applied_cache
        if cached is not None and cached[0] == version:
            watch.rollback()
            return cached[1]
        try:
            keys = self._load_applied_block_keys(watch)
        finally:
            watch.rollback()
        self._applied_cache = (version, keys)
        return keys

    @staticmethod
    def _load_applied_block_keys(
        conn: sqlite3.Connection,
    ) -> tuple[set[str], set[str], set[str], set[tuple[str, str]]]:
        prior_statuses = (
            JobStatus.APPLIED.value,
            JobStatus.FAILED.value,
            JobStatus.NEEDS_REVIEW.value,
            JobStatus.CAPTCHA.value,
            JobStatus.APPLYING.value,
        )
        placeholders = ",".join("?" for _ in prior_statuses)
        rows = conn.execute(
            f"""
            SELECT id, status, url, application_url, company, title FROM jobs
            WHERE status IN ({placeholders})
            """,
            prior_statuses,
        ).fetchall()
        applied_ids: set[str] = set()
        blocked_urls: set[str] = set()
        blocked_pairs: set[tuple[str, str]] = set()
        applied = JobStatus.APPLIED.value
        for record in rows:
            if record["status"] == applied and record["id"] is not None:
                applied_ids.add(record["id"])
            for candidate in (record["url"], record["application_url"]):
                key = _url_identity(candidate or "")
                if key:
                    blocked_urls.add(key)
            company_key = _company_key(record["company"] or "")
            title_key = _title_key(record["title"] or "")
            if company_key and title_key:
                blocked_pairs.add((company_key, title_key))
        application_job_ids = {
            record["job_id"]
            for record in conn.execute("SELECT job_id FROM applications").fetchall()
            if record["job_id"] is not None
        }
        return applied_ids, application_job_ids, blocked_urls, blocked_pairs

    def has_applied(self, job: Job) -> bool:
        """Hard safety: never apply twice (id, normalized URL, or company+title).

        Twin URL / company+title matching scans prior attempt statuses, not only
        APPLIED — FAILED/NEEDS_REVIEW/CAPTCHA/APPLYING must also block re-apply.

        The old body loaded every prior-status row and normalized URL, company
        and title in Python on every call, so n calls over n rows were
        superlinear. Block keys are built once per database generation.
        """
        url_keys = {_url_identity(u) for u in (job.url, job.application_url) if u}
        url_keys.discard("")
        company_key = _company_key(job.company)
        title_key = _title_key(job.title)
        applied_ids, application_job_ids, blocked_urls, blocked_pairs = (
            self._applied_block_keys()
        )
        if job.id in applied_ids:
            return True
        # Any applications row for this job_id counts as already handled,
        # including status APPLIED.
        if job.id in application_job_ids:
            return True
        for key in url_keys:
            if key in blocked_urls:
                return True
        if company_key and title_key and (company_key, title_key) in blocked_pairs:
            return True
        return False

    def count_applications_today(self) -> int:
        """Count only real applied submissions toward the daily cap."""
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        with self.connection() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS c FROM applications
                WHERE application_date LIKE ?
                  AND LOWER(COALESCE(status, '')) IN ('applied', 'submitted', 'ok')
                """,
                (f"{day}%",),
            ).fetchone()
        return int(row["c"] if row else 0)

    def list_applications(
        self,
        *,
        statuses: list[str] | None = None,
        limit: int = 500,
    ) -> list[ApplicationRecord]:
        sql = "SELECT * FROM applications"
        params: list[Any] = []
        if statuses:
            placeholders = ", ".join("?" for _ in statuses)
            sql += f" WHERE status IN ({placeholders})"
            params.extend(statuses)
        sql += " ORDER BY application_date DESC LIMIT ?"
        params.append(limit)
        with self.connection() as conn:
            rows = conn.execute(sql, params).fetchall()
        result: list[ApplicationRecord] = []
        for row in rows:
            data = dict(row)
            result.append(
                ApplicationRecord(
                    id=data.get("id") or "",
                    job_id=data.get("job_id") or "",
                    company=data.get("company") or "",
                    position=data.get("position") or "",
                    application_date=data.get("application_date") or "",
                    platform=data.get("platform") or "",
                    status=data.get("status") or "",
                    cv_used=data.get("cv_used") or "",
                    cover_letter_used=data.get("cover_letter_used") or "",
                    result=data.get("result") or "",
                    error_message=data.get("error_message") or "",
                )
            )
        return result

    def get_meta(self, key: str) -> str | None:
        with self.connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS app_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at TEXT
                )
                """
            )
            row = conn.execute(
                "SELECT value FROM app_meta WHERE key = ?", (key,)
            ).fetchone()
        return row["value"] if row else None

    def set_meta(self, key: str, value: str) -> None:
        with self.connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS app_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at TEXT
                )
                """
            )
            conn.execute(
                """
                INSERT INTO app_meta (key, value, updated_at) VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
                """,
                (key, value, utc_now_iso()),
            )

    def save_application(self, record: ApplicationRecord) -> str:
        if not record.id:
            record.id = str(uuid.uuid4())
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO applications (
                    id, job_id, company, position, application_date, platform,
                    status, cv_used, cover_letter_used, result, error_message
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.id,
                    record.job_id,
                    record.company,
                    record.position,
                    record.application_date,
                    record.platform,
                    record.status,
                    record.cv_used,
                    record.cover_letter_used,
                    record.result,
                    record.error_message,
                ),
            )
        return record.id

    def get_geocode(self, query: str) -> tuple[float, float, str, str] | None:
        """Return (lat, lon, display_name, cached_at) or None.

        Extra provenance columns (data_source/version) are available via
        ``get_geocode_record`` — this tuple shape stays backward compatible.
        """
        rec = self.get_geocode_record(query)
        if not rec:
            return None
        return (
            float(rec["latitude"]),
            float(rec["longitude"]),
            rec.get("display_name") or "",
            rec.get("cached_at") or "",
        )

    def get_geocode_record(self, query: str) -> dict[str, Any] | None:
        """Full geocode cache row including data_source / data_version."""
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM geocode_cache WHERE query = ?",
                (query.lower().strip(),),
            ).fetchone()
        if not row:
            return None
        keys = row.keys()
        return {k: row[k] for k in keys}

    def set_geocode(
        self,
        query: str,
        latitude: float,
        longitude: float,
        display_name: str = "",
        *,
        data_source: str = "",
        data_version: str = "",
        country_code: str = "",
        resolution_status: str = "",
    ) -> None:
        status = resolution_status or (
            "UNKNOWN" if display_name == "__unresolved__" else "RESOLVED"
        )
        with self.connection() as conn:
            # Ensure provenance columns exist (legacy DBs).
            geo_cols = {
                row[1]
                for row in conn.execute("PRAGMA table_info(geocode_cache)").fetchall()
            }
            if "data_source" in geo_cols:
                conn.execute(
                    """
                    INSERT INTO geocode_cache (
                        query, latitude, longitude, display_name, cached_at,
                        data_source, data_version, country_code, resolution_status
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(query) DO UPDATE SET
                        latitude=excluded.latitude,
                        longitude=excluded.longitude,
                        display_name=excluded.display_name,
                        cached_at=excluded.cached_at,
                        data_source=excluded.data_source,
                        data_version=excluded.data_version,
                        country_code=excluded.country_code,
                        resolution_status=excluded.resolution_status
                    """,
                    (
                        query.lower().strip(),
                        latitude,
                        longitude,
                        display_name,
                        utc_now_iso(),
                        data_source,
                        data_version,
                        country_code,
                        status,
                    ),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO geocode_cache (query, latitude, longitude, display_name, cached_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(query) DO UPDATE SET
                        latitude=excluded.latitude,
                        longitude=excluded.longitude,
                        display_name=excluded.display_name,
                        cached_at=excluded.cached_at
                    """,
                    (
                        query.lower().strip(),
                        latitude,
                        longitude,
                        display_name,
                        utc_now_iso(),
                    ),
                )

    def set_source_status(
        self, source: str, status: str, message: str = "", jobs_found: int = 0
    ) -> None:
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO source_status (source, status, message, checked_at, jobs_found)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(source) DO UPDATE SET
                    status=excluded.status,
                    message=excluded.message,
                    checked_at=excluded.checked_at,
                    jobs_found=excluded.jobs_found
                """,
                (source, status, message, utc_now_iso(), jobs_found),
            )

    def list_source_status(self) -> list[dict[str, Any]]:
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM source_status ORDER BY source"
            ).fetchall()
        return [dict(r) for r in rows]

    def dashboard_stats(self, run_id: str | None = None) -> dict[str, int]:
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        with self.connection() as conn:
            found = conn.execute(
                "SELECT COUNT(*) AS c FROM jobs WHERE discovered_at LIKE ?",
                (f"{day}%",),
            ).fetchone()["c"]
            new = conn.execute(
                "SELECT COUNT(*) AS c FROM jobs WHERE status = 'new' AND discovered_at LIKE ?",
                (f"{day}%",),
            ).fetchone()["c"]
            matches = conn.execute(
                "SELECT COUNT(*) AS c FROM jobs WHERE match_score >= 75 AND duplicate_of IS NULL"
            ).fetchone()["c"]
            applied = conn.execute(
                "SELECT COUNT(*) AS c FROM applications WHERE status = 'applied' AND application_date LIKE ?",
                (f"{day}%",),
            ).fetchone()["c"]
            needs = conn.execute(
                "SELECT COUNT(*) AS c FROM jobs WHERE status = 'needs_review'"
            ).fetchone()["c"]
            errors = conn.execute(
                "SELECT COUNT(*) AS c FROM jobs WHERE status = 'failed'"
            ).fetchone()["c"]
            captcha = conn.execute(
                "SELECT COUNT(*) AS c FROM jobs WHERE status = 'captcha'"
            ).fetchone()["c"]
            applications_active = conn.execute(
                """
                SELECT COUNT(*) AS c FROM applications
                WHERE LOWER(COALESCE(status, '')) NOT IN (
                    'failed', 'closed', 'rejected', 'withdrawn', 'cancelled'
                )
                """
            ).fetchone()["c"]
            replies_attention = conn.execute(
                """
                SELECT COUNT(*) AS c FROM email_messages
                WHERE association_status IN ('ambiguous', 'review_required')
                """
            ).fetchone()["c"]
            this_run = 0
            rid = run_id or self.latest_run_id()
            if rid:
                this_run = conn.execute(
                    "SELECT COUNT(*) AS c FROM jobs WHERE run_id = ? AND duplicate_of IS NULL",
                    (rid,),
                ).fetchone()["c"]
            total_jobs = conn.execute("SELECT COUNT(*) AS c FROM jobs").fetchone()["c"]
        return {
            "jobs_found_today": int(found),
            "new_today": int(new),
            "matches_ge_75": int(matches),
            "applications_today": int(applied),
            "applications_active": int(applications_active),
            "replies_attention": int(replies_attention),
            "needs_review": int(needs),
            "errors": int(errors),
            "captcha": int(captcha),
            "this_run": int(this_run),
            "total_jobs": int(total_jobs),
        }

    def start_search_run(self, run_id: str | None = None) -> str:
        rid = run_id or uuid.uuid4().hex
        with self.connection() as conn:
            conn.execute(
                "INSERT INTO search_runs (id, started_at, finished_at, status, stats_json) "
                "VALUES (?, ?, ?, ?, ?)",
                (rid, utc_now_iso(), "", "running", "{}"),
            )
        return rid

    def finish_search_run(self, run_id: str, status: str, stats: dict[str, Any] | None = None) -> None:
        with self.connection() as conn:
            conn.execute(
                "UPDATE search_runs SET finished_at = ?, status = ?, stats_json = ? WHERE id = ?",
                (utc_now_iso(), status, json.dumps(stats or {}, ensure_ascii=False), run_id),
            )

    def latest_run_id(self) -> str | None:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT id FROM search_runs ORDER BY started_at DESC, rowid DESC LIMIT 1"
            ).fetchone()
        return str(row["id"]) if row else None

    def clear_job_data(
        self,
        *,
        clear_applications: bool = True,
        clear_source_status: bool = True,
        clear_search_runs: bool = True,
        clear_geocode_cache: bool = False,
    ) -> dict[str, int]:
        """Remove job search data; never touches applicant profile files."""
        counts: dict[str, int] = {}
        with self.connection() as conn:
            if clear_applications:
                counts["applications"] = conn.execute("SELECT COUNT(*) AS c FROM applications").fetchone()["c"]
                conn.execute("DELETE FROM applications")
            counts["jobs"] = conn.execute("SELECT COUNT(*) AS c FROM jobs").fetchone()["c"]
            conn.execute("DELETE FROM jobs")
            if clear_source_status:
                counts["source_status"] = conn.execute(
                    "SELECT COUNT(*) AS c FROM source_status"
                ).fetchone()["c"]
                conn.execute("DELETE FROM source_status")
            if clear_search_runs:
                counts["search_runs"] = conn.execute(
                    "SELECT COUNT(*) AS c FROM search_runs"
                ).fetchone()["c"]
                conn.execute("DELETE FROM search_runs")
            if clear_geocode_cache:
                counts["geocode_cache"] = conn.execute(
                    "SELECT COUNT(*) AS c FROM geocode_cache"
                ).fetchone()["c"]
                conn.execute("DELETE FROM geocode_cache")
        return {k: int(v) for k, v in counts.items()}

    def find_existing_by_source(self, source: str, source_job_id: str) -> Job | None:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM jobs WHERE source = ? AND source_job_id = ?",
                (source, source_job_id),
            ).fetchone()
        return self._row_to_job(row) if row else None

    # --- ApplicationCase / lifecycle ---

    def upsert_case(self, case: ApplicationCase) -> ApplicationCase:
        if not case.id:
            case.id = str(uuid.uuid4())
        if not case.company_key:
            case.company_key = _company_key(case.company)
        if not case.title_key:
            case.title_key = _title_key(case.position)
        if not case.url_key:
            case.url_key = _url_identity(case.application_url or case.url)
        case.updated_at = utc_now_iso()
        if not case.created_at:
            case.created_at = case.updated_at
        data = case.to_dict()
        cols = list(data.keys())
        placeholders = ", ".join("?" for _ in cols)
        col_names = ", ".join(cols)
        updates = ", ".join(f"{c}=excluded.{c}" for c in cols if c != "id")
        sql = (
            f"INSERT INTO application_cases ({col_names}) VALUES ({placeholders}) "
            f"ON CONFLICT(id) DO UPDATE SET {updates}"
        )
        with self.connection() as conn:
            conn.execute(sql, [data[c] for c in cols])
        return case

    def get_case(self, case_id: str) -> ApplicationCase | None:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM application_cases WHERE id = ?", (case_id,)
            ).fetchone()
        return ApplicationCase.from_dict(dict(row)) if row else None

    def list_cases(
        self,
        *,
        statuses: list[str] | None = None,
        limit: int = 500,
    ) -> list[ApplicationCase]:
        sql = "SELECT * FROM application_cases"
        params: list[Any] = []
        if statuses:
            sql += f" WHERE status IN ({','.join('?' for _ in statuses)})"
            params.extend(statuses)
        sql += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)
        with self.connection() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [ApplicationCase.from_dict(dict(r)) for r in rows]

    def find_case_for_job(
        self,
        *,
        job_id: str = "",
        url_keys: set[str] | None = None,
        company_key: str = "",
        title_key: str = "",
        statuses: set[str] | frozenset[str] | None = None,
    ) -> dict[str, Any] | None:
        """Match a suppressing case. Never company-only (no company blacklist)."""
        url_keys = {k for k in (url_keys or set()) if k}
        status_filter = list(statuses) if statuses else None
        with self.connection() as conn:
            if job_id:
                row = conn.execute(
                    "SELECT * FROM application_cases WHERE job_id = ? LIMIT 1",
                    (job_id,),
                ).fetchone()
                if row and (
                    status_filter is None or (row["status"] or "") in status_filter
                ):
                    data = dict(row)
                    data["match_reason"] = "job_id"
                    return data
            if url_keys:
                rows = conn.execute(
                    "SELECT * FROM application_cases WHERE url_key != ''"
                ).fetchall()
                for r in rows:
                    if status_filter is not None and (r["status"] or "") not in status_filter:
                        continue
                    if (r["url_key"] or "") in url_keys:
                        data = dict(r)
                        data["match_reason"] = "url"
                        return data
            if company_key and title_key:
                rows = conn.execute(
                    """
                    SELECT * FROM application_cases
                    WHERE company_key = ? AND title_key = ?
                    """,
                    (company_key, title_key),
                ).fetchall()
                for r in rows:
                    if status_filter is not None and (r["status"] or "") not in status_filter:
                        continue
                    data = dict(r)
                    data["match_reason"] = "company_title"
                    return data
        return None

    def set_case_status(
        self,
        case_id: str,
        new_status: str,
        *,
        force: bool = False,
        confidence: float = 1.0,
        payload: dict[str, Any] | None = None,
        occurred_at: str = "",
        idempotency_key: str = "",
        source: str = "",
    ) -> ApplicationCase | None:
        """Mutate status only by appending a lifecycle event and reducing."""
        case = self.get_case(case_id)
        if case is None:
            return None
        new_status = (new_status or "").strip().lower()
        if not new_status:
            return case
        if not force and not can_transition(case.status, new_status, force=False):
            return case

        extra = dict(payload or {})
        if force:
            event_type = LifecycleEventType.MANUAL_OVERRIDE.value
            extra.setdefault("to", new_status)
            extra.setdefault("from", case.status)
            audit_type = CaseEventType.MANUAL_OVERRIDE.value
        else:
            mapped = status_to_lifecycle_event(new_status)
            if not mapped:
                return case
            event_type = mapped
            audit_type = CaseEventType.STATUS_CHANGED.value

        self.append_lifecycle_event(
            LifecycleEvent(
                case_id=case_id,
                event_type=event_type,
                occurred_at=occurred_at or utc_now_iso(),
                idempotency_key=idempotency_key,
                payload=extra,
                source=source
                or extra.get("source", "")
                or ("manual" if force else "status_write"),
                confidence=confidence,
            )
        )
        self.add_case_event(
            CaseEvent(
                case_id=case_id,
                event_type=audit_type,
                payload_json=json.dumps(
                    {
                        "from": case.status,
                        "to": new_status,
                        "lifecycle_event": event_type,
                        **extra,
                    },
                    ensure_ascii=False,
                ),
                confidence=confidence,
            )
        )
        return self.get_case(case_id)

    def append_lifecycle_event(
        self,
        event: LifecycleEvent,
        *,
        recompute: bool = True,
    ) -> tuple[LifecycleEvent, bool]:
        if not event.case_id:
            raise ValueError("lifecycle event requires case_id")
        case = self.get_case(event.case_id)
        if case is None:
            raise ValueError(f"unknown case_id: {event.case_id}")

        self._ensure_seed_lifecycle_event(case)

        ev = event.with_defaults()
        if not ev.id:
            ev = LifecycleEvent(
                event_type=ev.event_type,
                occurred_at=ev.occurred_at,
                idempotency_key=ev.idempotency_key,
                payload=dict(ev.payload or {}),
                id=str(uuid.uuid4()),
                case_id=ev.case_id or event.case_id,
                recorded_at=ev.recorded_at,
                source=ev.source,
                confidence=ev.confidence,
            )
        inserted = True
        try:
            with self.connection() as conn:
                conn.execute(
                    """
                    INSERT INTO lifecycle_events (
                        id, case_id, event_type, occurred_at, recorded_at,
                        idempotency_key, payload_json, source, confidence
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        ev.id,
                        ev.case_id,
                        ev.event_type,
                        ev.occurred_at,
                        ev.recorded_at,
                        ev.idempotency_key or "",
                        json.dumps(ev.payload or {}, ensure_ascii=False),
                        ev.source or "",
                        float(ev.confidence),
                    ),
                )
        except sqlite3.IntegrityError:
            inserted = False
            if ev.idempotency_key:
                with self.connection() as conn:
                    row = conn.execute(
                        """
                        SELECT * FROM lifecycle_events
                        WHERE case_id = ? AND idempotency_key = ?
                        LIMIT 1
                        """,
                        (ev.case_id, ev.idempotency_key),
                    ).fetchone()
                if row:
                    ev = self._row_to_lifecycle_event(row)

        if recompute:
            self.recompute_case_status(ev.case_id)
        return ev, inserted

    def _ensure_seed_lifecycle_event(self, case: ApplicationCase) -> None:
        with self.connection() as conn:
            count = conn.execute(
                "SELECT COUNT(*) AS c FROM lifecycle_events WHERE case_id = ?",
                (case.id,),
            ).fetchone()
        if count and int(count["c"] or 0) > 0:
            return
        status = (case.legacy_status or case.status or CaseStatus.TO_APPLY.value).strip()
        seed = seed_event_for_status(status)
        if not seed:
            return
        if not case.legacy_status and case.status:
            with self.connection() as conn:
                conn.execute(
                    "UPDATE application_cases SET legacy_status = ? WHERE id = ? "
                    "AND COALESCE(legacy_status, '') = ''",
                    (case.status, case.id),
                )
        occurred = case.applied_at or case.created_at or utc_now_iso()
        try:
            with self.connection() as conn:
                conn.execute(
                    """
                    INSERT INTO lifecycle_events (
                        id, case_id, event_type, occurred_at, recorded_at,
                        idempotency_key, payload_json, source, confidence
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(uuid.uuid4()),
                        case.id,
                        seed,
                        occurred,
                        case.updated_at or occurred,
                        f"seed:{case.id}:{seed}:{status}",
                        json.dumps({"seed": True, "legacy_status": status}, ensure_ascii=False),
                        "status_seed",
                        1.0,
                    ),
                )
        except sqlite3.IntegrityError:
            return

    @staticmethod
    def _row_to_lifecycle_event(row: Any) -> LifecycleEvent:
        payload_raw = row["payload_json"] or "{}"
        try:
            payload = json.loads(payload_raw) if isinstance(payload_raw, str) else {}
        except json.JSONDecodeError:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        return LifecycleEvent(
            id=row["id"],
            case_id=row["case_id"],
            event_type=row["event_type"],
            occurred_at=row["occurred_at"] or "",
            recorded_at=row["recorded_at"] or "",
            idempotency_key=row["idempotency_key"] or "",
            payload=payload,
            source=row["source"] or "",
            confidence=float(row["confidence"] or 0),
        )

    def list_lifecycle_events(
        self, case_id: str, *, limit: int = 500
    ) -> list[LifecycleEvent]:
        with self.connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM lifecycle_events WHERE case_id = ?
                ORDER BY occurred_at ASC, recorded_at ASC, id ASC
                LIMIT ?
                """,
                (case_id, limit),
            ).fetchall()
        return [self._row_to_lifecycle_event(r) for r in rows]

    def recompute_case_status(self, case_id: str) -> ApplicationCase | None:
        case = self.get_case(case_id)
        if case is None:
            return None
        events = self.list_lifecycle_events(case_id)
        if not events:
            fallback = case.legacy_status or case.status
            if fallback and case.status != fallback:
                case.status = fallback
                case.updated_at = utc_now_iso()
                return self.upsert_case(case)
            return case
        result = reduce_lifecycle_events(events)
        if case.status != result.status:
            case.status = result.status
            case.updated_at = utc_now_iso()
            return self.upsert_case(case)
        return case

    def apply_lifecycle_event_for_email(
        self,
        case_id: str,
        event_type: str,
        *,
        email_id: str = "",
        occurred_at: str = "",
        confidence: float = 1.0,
        payload: dict[str, Any] | None = None,
    ) -> ApplicationCase | None:
        extra = dict(payload or {})
        if email_id:
            extra.setdefault("email_id", email_id)
        idem = f"email:{case_id}:{email_id}:{event_type}" if email_id else ""
        self.append_lifecycle_event(
            LifecycleEvent(
                case_id=case_id,
                event_type=event_type,
                occurred_at=occurred_at or utc_now_iso(),
                idempotency_key=idem,
                payload=extra,
                source="email",
                confidence=confidence,
            )
        )
        self.add_case_event(
            CaseEvent(
                case_id=case_id,
                event_type=CaseEventType.LIFECYCLE_EVENT.value,
                payload_json=json.dumps(
                    {"lifecycle_event": event_type, **extra},
                    ensure_ascii=False,
                ),
                confidence=confidence,
            )
        )
        return self.get_case(case_id)

    def add_case_event(self, event: CaseEvent) -> CaseEvent:
        if not event.id:
            event.id = str(uuid.uuid4())
        if not event.created_at:
            event.created_at = utc_now_iso()
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO case_events (id, case_id, event_type, payload_json, created_at, confidence)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    event.id,
                    event.case_id,
                    event.event_type,
                    event.payload_json or "{}",
                    event.created_at,
                    float(event.confidence),
                ),
            )
        return event

    def list_case_events(self, case_id: str, *, limit: int = 100) -> list[CaseEvent]:
        with self.connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM case_events WHERE case_id = ?
                ORDER BY created_at DESC LIMIT ?
                """,
                (case_id, limit),
            ).fetchall()
        out: list[CaseEvent] = []
        for r in rows:
            out.append(
                CaseEvent(
                    id=r["id"],
                    case_id=r["case_id"],
                    event_type=r["event_type"],
                    payload_json=r["payload_json"] or "{}",
                    created_at=r["created_at"] or "",
                    confidence=float(r["confidence"] or 0),
                )
            )
        return out

    def ensure_case_from_job(
        self, job: Job, *, status: str = CaseStatus.APPLIED.value
    ) -> ApplicationCase:
        existing = self.find_case_for_job(
            job_id=job.id or "",
            url_keys={_url_identity(u) for u in (job.url, job.application_url) if u} - {""},
            company_key=_company_key(job.company),
            title_key=_title_key(job.title),
            statuses=None,
        )
        if existing:
            case = ApplicationCase.from_dict(existing)
            case.job_id = case.job_id or job.id
            case = self.upsert_case(case)
            if status and status != case.status:
                self.set_case_status(
                    case.id,
                    status,
                    source="ensure_case_from_job",
                    payload={"job_id": job.id},
                )
                refreshed = self.get_case(case.id)
                return refreshed or case
            return case
        case = ApplicationCase(
            job_id=job.id,
            company=job.company,
            position=job.title,
            status=CaseStatus.TO_APPLY.value,
            source=job.source,
            url=job.url,
            application_url=job.application_url,
            applied_at=utc_now_iso() if status != CaseStatus.TO_APPLY.value else "",
            company_key=_company_key(job.company),
            title_key=_title_key(job.title),
            url_key=_url_identity(job.application_url or job.url),
            legacy_status=CaseStatus.TO_APPLY.value,
        )
        case = self.upsert_case(case)
        self.append_lifecycle_event(
            LifecycleEvent(
                case_id=case.id,
                event_type=LifecycleEventType.APPLICATION_CREATED.value,
                occurred_at=case.created_at or utc_now_iso(),
                idempotency_key=f"created:{case.id}",
                payload={"job_id": job.id},
                source="ensure_case_from_job",
            )
        )
        if status and status != CaseStatus.TO_APPLY.value:
            self.set_case_status(
                case.id,
                status,
                source="ensure_case_from_job",
                payload={"job_id": job.id},
                idempotency_key=f"ensure:{case.id}:{status}",
            )
        self.add_case_event(
            CaseEvent(
                case_id=case.id,
                event_type=CaseEventType.CREATED.value,
                payload_json=json.dumps({"status": status}, ensure_ascii=False),
            )
        )
        return self.get_case(case.id) or case

    def get_email_message(self, email_id: str) -> dict[str, Any] | None:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM email_messages WHERE id = ? OR gmail_id = ? LIMIT 1",
                (email_id, email_id),
            ).fetchone()
        return dict(row) if row else None

    def save_email_message(self, row: dict[str, Any]) -> str:
        """Persist email. Confirmed associations are never silently overwritten."""
        mid = row.get("id") or str(uuid.uuid4())
        gmail_id = row.get("gmail_id") or mid
        evidence = row.get("association_evidence_json")
        if not isinstance(evidence, str):
            evidence = json.dumps(evidence or [], ensure_ascii=False)
        with self.connection() as conn:
            existing = conn.execute(
                "SELECT * FROM email_messages WHERE gmail_id = ? LIMIT 1",
                (gmail_id,),
            ).fetchone()
            if existing is not None:
                prev = dict(existing)
                confirmed = bool(int(prev.get("association_confirmed") or 0))
                prev_case = prev.get("case_id") or ""
                if confirmed and prev_case:
                    new_case = row.get("case_id") or ""
                    # Protect confirmed link — classification may update, case_id may not.
                    if new_case and new_case != prev_case:
                        conn.execute(
                            """
                            UPDATE email_messages SET
                                subject=?, body_text=?, category=?, confidence=?
                            WHERE gmail_id=?
                            """,
                            (
                                row.get("subject") or prev.get("subject") or "",
                                row.get("body_text") or prev.get("body_text") or "",
                                row.get("category") or prev.get("category") or "",
                                float(row.get("confidence") or prev.get("confidence") or 0),
                                gmail_id,
                            ),
                        )
                        return str(prev.get("id") or mid)
                    conn.execute(
                        """
                        UPDATE email_messages SET
                            subject=?, body_text=?, category=?, confidence=?
                        WHERE gmail_id=?
                        """,
                        (
                            row.get("subject") or prev.get("subject") or "",
                            row.get("body_text") or prev.get("body_text") or "",
                            row.get("category") or prev.get("category") or "",
                            float(row.get("confidence") or prev.get("confidence") or 0),
                            gmail_id,
                        ),
                    )
                    return str(prev.get("id") or mid)

            conn.execute(
                """
                INSERT INTO email_messages (
                    id, gmail_id, thread_id, subject, sender, body_text,
                    category, confidence, case_id, association_status,
                    association_policy_version, association_explanation,
                    association_evidence_json, association_confirmed,
                    received_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(gmail_id) DO UPDATE SET
                    subject=excluded.subject,
                    body_text=excluded.body_text,
                    category=excluded.category,
                    confidence=excluded.confidence,
                    case_id=CASE
                        WHEN email_messages.association_confirmed = 1
                        THEN email_messages.case_id
                        ELSE excluded.case_id
                    END,
                    association_status=CASE
                        WHEN email_messages.association_confirmed = 1
                        THEN email_messages.association_status
                        ELSE excluded.association_status
                    END,
                    association_policy_version=CASE
                        WHEN email_messages.association_confirmed = 1
                        THEN email_messages.association_policy_version
                        ELSE excluded.association_policy_version
                    END,
                    association_explanation=CASE
                        WHEN email_messages.association_confirmed = 1
                        THEN email_messages.association_explanation
                        ELSE excluded.association_explanation
                    END,
                    association_evidence_json=CASE
                        WHEN email_messages.association_confirmed = 1
                        THEN email_messages.association_evidence_json
                        ELSE excluded.association_evidence_json
                    END
                """,
                (
                    mid,
                    gmail_id,
                    row.get("thread_id") or "",
                    row.get("subject") or "",
                    row.get("sender") or "",
                    row.get("body_text") or "",
                    row.get("category") or "",
                    float(row.get("confidence") or 0),
                    row.get("case_id") or "",
                    row.get("association_status") or "unlinked",
                    row.get("association_policy_version") or "",
                    row.get("association_explanation") or "",
                    evidence,
                    1 if row.get("association_confirmed") else 0,
                    row.get("received_at") or "",
                    row.get("created_at") or utc_now_iso(),
                ),
            )
        return mid


    def get_email_by_gmail_id(self, gmail_id: str) -> dict[str, Any] | None:
        gid = (gmail_id or "").strip()
        if not gid:
            return None
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM email_messages WHERE gmail_id = ? LIMIT 1",
                (gid,),
            ).fetchone()
        return dict(row) if row else None

    def has_gmail_message(self, gmail_id: str) -> bool:
        return self.get_email_by_gmail_id(gmail_id) is not None

    def list_ambiguous_emails(self, *, limit: int = 100) -> list[dict[str, Any]]:
        with self.connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM email_messages
                WHERE association_status IN ('ambiguous', 'review_required')
                ORDER BY created_at DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def list_inbox_emails(self, *, limit: int = 200, query: str = "") -> list[dict[str, Any]]:
        """Recent mailbox messages for Postfach (needs-review first, then newest)."""
        q = (query or "").strip().lower()
        with self.connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM email_messages
                ORDER BY
                  CASE
                    WHEN association_status IN ('ambiguous', 'review_required') THEN 0
                    ELSE 1
                  END,
                  COALESCE(NULLIF(received_at, ''), created_at) DESC
                LIMIT ?
                """,
                (int(limit),),
            ).fetchall()
        out = [dict(r) for r in rows]
        if not q:
            return out
        return [
            e
            for e in out
            if q in (e.get("subject") or "").lower()
            or q in (e.get("sender") or "").lower()
            or q in (e.get("body_text") or "").lower()
        ]

    def resolve_email_association(self, email_id: str, case_id: str) -> None:
        """Manual user confirmation — sets confirmed flag (rollback-safe)."""
        from integrations.email_associate import ASSOCIATION_POLICY_VERSION

        with self.connection() as conn:
            conn.execute(
                """
                UPDATE email_messages
                SET case_id = ?,
                    association_status = 'linked',
                    association_confirmed = 1,
                    association_policy_version = ?,
                    association_explanation = ?
                WHERE id = ? OR gmail_id = ?
                """,
                (
                    case_id,
                    ASSOCIATION_POLICY_VERSION,
                    f"Manually confirmed link to {case_id}",
                    email_id,
                    email_id,
                ),
            )
        self.add_case_event(
            CaseEvent(
                case_id=case_id,
                event_type=CaseEventType.EMAIL_LINKED.value,
                payload_json=json.dumps(
                    {
                        "email_id": email_id,
                        "manual": True,
                        "confirmed": True,
                        "policy_version": ASSOCIATION_POLICY_VERSION,
                    }
                ),
            )
        )

    def save_lifecycle_task(self, task: dict[str, Any]) -> str:
        tid = task.get("id") or str(uuid.uuid4())
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO lifecycle_tasks (
                    id, case_id, kind, title, body, status, due_at, created_at, auto_send
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    status=excluded.status,
                    body=excluded.body,
                    title=excluded.title
                """,
                (
                    tid,
                    task.get("case_id") or "",
                    task.get("kind") or "",
                    task.get("title") or "",
                    task.get("body") or "",
                    task.get("status") or "open",
                    task.get("due_at") or "",
                    task.get("created_at") or utc_now_iso(),
                    1 if task.get("auto_send") else 0,
                ),
            )
        return tid

    def save_followup_reminder(self, reminder: dict[str, Any]) -> str:
        rid = reminder.get("id") or str(uuid.uuid4())
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO followup_reminders (
                    id, case_id, kind, title, body, status, due_at, created_at,
                    fired_at, auto_send, schema_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    status=excluded.status,
                    body=excluded.body,
                    title=excluded.title,
                    due_at=excluded.due_at,
                    fired_at=excluded.fired_at,
                    auto_send=0
                """,
                (
                    rid,
                    reminder.get("case_id") or "",
                    reminder.get("kind") or "",
                    reminder.get("title") or "",
                    reminder.get("body") or "",
                    reminder.get("status") or "open",
                    reminder.get("due_at") or "",
                    reminder.get("created_at") or utc_now_iso(),
                    reminder.get("fired_at") or "",
                    0,  # never auto-send
                    int(reminder.get("schema_version") or 1),
                ),
            )
        return rid

    def list_followup_reminders(
        self, *, status: str = "open", limit: int = 100
    ) -> list[dict[str, Any]]:
        with self.connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM followup_reminders WHERE status = ?
                ORDER BY due_at ASC, created_at DESC LIMIT ?
                """,
                (status, limit),
            ).fetchall()
        out = [dict(r) for r in rows]
        for row in out:
            row["auto_send"] = 0
        return out

    def update_followup_reminder(self, reminder_id: str, **fields: Any) -> None:
        allowed = {"status", "fired_at", "body", "title", "due_at"}
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return
        sets = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [reminder_id]
        with self.connection() as conn:
            conn.execute(
                f"UPDATE followup_reminders SET {sets}, auto_send = 0 WHERE id = ?",
                values,
            )

    def list_lifecycle_tasks(
        self, *, status: str = "open", limit: int = 100
    ) -> list[dict[str, Any]]:
        with self.connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM lifecycle_tasks WHERE status = ?
                ORDER BY created_at DESC LIMIT ?
                """,
                (status, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def lifecycle_dashboard_counts(self) -> dict[str, int]:
        with self.connection() as conn:
            by_status: dict[str, int] = {}
            for r in conn.execute(
                "SELECT status, COUNT(*) AS c FROM application_cases GROUP BY status"
            ).fetchall():
                by_status[str(r["status"])] = int(r["c"])
            ambiguous = conn.execute(
                "SELECT COUNT(*) AS c FROM email_messages WHERE association_status = 'ambiguous'"
            ).fetchone()["c"]
            open_tasks = conn.execute(
                "SELECT COUNT(*) AS c FROM lifecycle_tasks WHERE status = 'open'"
            ).fetchone()["c"]
        return {
            "cases_total": sum(by_status.values()),
            "ambiguous_emails": int(ambiguous),
            "open_tasks": int(open_tasks),
            **{f"case_{k}": v for k, v in by_status.items()},
        }

    @staticmethod
    def _row_to_job(row: sqlite3.Row) -> Job:
        data = dict(row)
        data.pop("updated_at", None)
        return Job.from_dict(data)

    # --- Recruiting contact discovery (PR25) ---

    def upsert_recruiting_contact_result(
        self, result: Any, *, cache_key: str = ""
    ) -> str:
        """Persist a DiscoveryResult (FOUND / NOT_FOUND / …). Returns row id."""
        from core.contacts.models import DiscoveryResult

        if not isinstance(result, DiscoveryResult):
            raise TypeError("expected DiscoveryResult")
        best = result.best
        row_id = str(uuid.uuid4())
        payload = json.dumps(result.to_dict(), ensure_ascii=False)
        with self.connection() as conn:
            # Replace previous cache_key row if present
            if cache_key:
                conn.execute(
                    "DELETE FROM recruiting_contacts WHERE cache_key = ? AND status != 'INVALIDATED'",
                    (cache_key,),
                )
            conn.execute(
                """
                INSERT INTO recruiting_contacts (
                    id, job_id, case_id, schema_version, status, payload_json,
                    source_type, source_url, discovered_at, invalidated_at,
                    cache_key, contact_kind
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, '', ?, ?)
                """,
                (
                    row_id,
                    result.job_id or "",
                    result.case_id or "",
                    int(result.schema_version),
                    result.status,
                    payload,
                    (best.source_type if best else ""),
                    (best.source_url if best else ""),
                    result.discovered_at or utc_now_iso(),
                    cache_key or "",
                    (best.contact_kind if best else ""),
                ),
            )
        return row_id

    def get_recruiting_contact_cache(self, cache_key: str) -> dict[str, Any] | None:
        if not cache_key:
            return None
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM recruiting_contacts WHERE cache_key = ? "
                "AND status != 'INVALIDATED' ORDER BY discovered_at DESC LIMIT 1",
                (cache_key,),
            ).fetchone()
        if not row:
            return None
        data = dict(row)
        try:
            data["payload_json"] = json.loads(data.get("payload_json") or "{}")
        except json.JSONDecodeError:
            data["payload_json"] = {}
        return data

    def list_recruiting_contacts(
        self,
        *,
        job_id: str | None = None,
        case_id: str | None = None,
        include_invalidated: bool = False,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if job_id:
            clauses.append("job_id = ?")
            params.append(job_id)
        if case_id:
            clauses.append("case_id = ?")
            params.append(case_id)
        if not include_invalidated:
            clauses.append("status != 'INVALIDATED'")
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = (
            f"SELECT * FROM recruiting_contacts {where} "
            f"ORDER BY discovered_at DESC LIMIT ?"
        )
        params.append(limit)
        with self.connection() as conn:
            rows = conn.execute(sql, params).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            data = dict(row)
            try:
                data["payload_json"] = json.loads(data.get("payload_json") or "{}")
            except json.JSONDecodeError:
                data["payload_json"] = {}
            out.append(data)
        return out

    def invalidate_recruiting_contacts(
        self,
        *,
        job_id: str | None = None,
        case_id: str | None = None,
        cache_key: str | None = None,
    ) -> int:
        clauses: list[str] = ["status != 'INVALIDATED'"]
        params: list[Any] = []
        if job_id:
            clauses.append("job_id = ?")
            params.append(job_id)
        if case_id:
            clauses.append("case_id = ?")
            params.append(case_id)
        if cache_key:
            clauses.append("cache_key = ?")
            params.append(cache_key)
        if not (job_id or case_id or cache_key):
            return 0
        now = utc_now_iso()
        sql = (
            f"UPDATE recruiting_contacts SET status = 'INVALIDATED', "
            f"invalidated_at = ? WHERE {' AND '.join(clauses)}"
        )
        with self.connection() as conn:
            cur = conn.execute(sql, [now, *params])
            return int(cur.rowcount or 0)

    def delete_recruiting_contacts(
        self,
        *,
        job_id: str | None = None,
        case_id: str | None = None,
        contact_id: str | None = None,
    ) -> int:
        clauses: list[str] = []
        params: list[Any] = []
        if contact_id:
            clauses.append("id = ?")
            params.append(contact_id)
        if job_id:
            clauses.append("job_id = ?")
            params.append(job_id)
        if case_id:
            clauses.append("case_id = ?")
            params.append(case_id)
        if not clauses:
            return 0
        sql = f"DELETE FROM recruiting_contacts WHERE {' AND '.join(clauses)}"
        with self.connection() as conn:
            cur = conn.execute(sql, params)
            return int(cur.rowcount or 0)

