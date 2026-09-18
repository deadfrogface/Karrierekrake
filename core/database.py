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
from core.lifecycle import ApplicationCase, CaseEvent, CaseEventType, CaseStatus, can_transition

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
    url_key TEXT DEFAULT ''
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

CREATE INDEX IF NOT EXISTS idx_cases_status ON application_cases(status);
CREATE INDEX IF NOT EXISTS idx_cases_company_title ON application_cases(company_key, title_key);
CREATE INDEX IF NOT EXISTS idx_cases_url_key ON application_cases(url_key);
CREATE INDEX IF NOT EXISTS idx_cases_job ON application_cases(job_id);
CREATE INDEX IF NOT EXISTS idx_case_events_case ON case_events(case_id);
CREATE INDEX IF NOT EXISTS idx_email_case ON email_messages(case_id);
CREATE INDEX IF NOT EXISTS idx_email_assoc ON email_messages(association_status);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON lifecycle_tasks(status);
"""


class Database:
    def __init__(self, path: Path, *, recover: bool = False) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
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

    def has_applied(self, job: Job) -> bool:
        """Hard safety: never apply twice (id, normalized URL, or company+title).

        Twin URL / company+title matching scans prior attempt statuses, not only
        APPLIED — FAILED/NEEDS_REVIEW/CAPTCHA/APPLYING must also block re-apply.
        """
        prior_statuses = (
            JobStatus.APPLIED.value,
            JobStatus.FAILED.value,
            JobStatus.NEEDS_REVIEW.value,
            JobStatus.CAPTCHA.value,
            JobStatus.APPLYING.value,
        )
        url_keys = {_url_identity(u) for u in (job.url, job.application_url) if u}
        url_keys.discard("")
        company_key = _company_key(job.company)
        title_key = _title_key(job.title)
        placeholders = ",".join("?" for _ in prior_statuses)
        with self.connection() as conn:
            row = conn.execute(
                "SELECT id FROM jobs WHERE id = ? AND status = ?",
                (job.id, JobStatus.APPLIED.value),
            ).fetchone()
            if row:
                return True
            row = conn.execute(
                "SELECT id FROM applications WHERE job_id = ? AND status = ?",
                (job.id, JobStatus.APPLIED.value),
            ).fetchone()
            if row:
                return True
            # Any applications row for this job_id counts as already handled.
            row = conn.execute(
                "SELECT id FROM applications WHERE job_id = ? LIMIT 1",
                (job.id,),
            ).fetchone()
            if row:
                return True
            rows = conn.execute(
                f"""
                SELECT id, url, application_url, company, title FROM jobs
                WHERE status IN ({placeholders})
                """,
                prior_statuses,
            ).fetchall()
            for r in rows:
                for candidate in (r["url"], r["application_url"]):
                    key = _url_identity(candidate or "")
                    if key and key in url_keys:
                        return True
                if company_key and title_key:
                    if _company_key(r["company"] or "") == company_key and _title_key(
                        r["title"] or ""
                    ) == title_key:
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
    ) -> ApplicationCase | None:
        case = self.get_case(case_id)
        if case is None:
            return None
        if not can_transition(case.status, new_status, force=force):
            return case
        old = case.status
        case.status = new_status
        case.updated_at = utc_now_iso()
        self.upsert_case(case)
        self.add_case_event(
            CaseEvent(
                case_id=case_id,
                event_type=CaseEventType.STATUS_CHANGED.value,
                payload_json=json.dumps(
                    {"from": old, "to": new_status, **(payload or {})},
                    ensure_ascii=False,
                ),
                confidence=confidence,
            )
        )
        return case

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
        """Create or refresh a case when an application succeeds / is tracked."""
        existing = self.find_case_for_job(
            job_id=job.id or "",
            url_keys={_url_identity(u) for u in (job.url, job.application_url) if u} - {""},
            company_key=_company_key(job.company),
            title_key=_title_key(job.title),
            statuses=None,
        )
        if existing:
            case = ApplicationCase.from_dict(existing)
            if can_transition(case.status, status):
                case.status = status
            case.job_id = case.job_id or job.id
            case.updated_at = utc_now_iso()
            return self.upsert_case(case)
        case = ApplicationCase(
            job_id=job.id,
            company=job.company,
            position=job.title,
            status=status,
            source=job.source,
            url=job.url,
            application_url=job.application_url,
            applied_at=utc_now_iso() if status != CaseStatus.TO_APPLY.value else "",
            company_key=_company_key(job.company),
            title_key=_title_key(job.title),
            url_key=_url_identity(job.application_url or job.url),
        )
        case = self.upsert_case(case)
        self.add_case_event(
            CaseEvent(
                case_id=case.id,
                event_type=CaseEventType.CREATED.value,
                payload_json=json.dumps({"status": status}, ensure_ascii=False),
            )
        )
        return case

    def save_email_message(self, row: dict[str, Any]) -> str:
        mid = row.get("id") or str(uuid.uuid4())
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO email_messages (
                    id, gmail_id, thread_id, subject, sender, body_text,
                    category, confidence, case_id, association_status,
                    received_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(gmail_id) DO UPDATE SET
                    subject=excluded.subject,
                    body_text=excluded.body_text,
                    category=excluded.category,
                    confidence=excluded.confidence,
                    case_id=excluded.case_id,
                    association_status=excluded.association_status
                """,
                (
                    mid,
                    row.get("gmail_id") or mid,
                    row.get("thread_id") or "",
                    row.get("subject") or "",
                    row.get("sender") or "",
                    row.get("body_text") or "",
                    row.get("category") or "",
                    float(row.get("confidence") or 0),
                    row.get("case_id") or "",
                    row.get("association_status") or "unlinked",
                    row.get("received_at") or "",
                    row.get("created_at") or utc_now_iso(),
                ),
            )
        return mid

    def list_ambiguous_emails(self, *, limit: int = 100) -> list[dict[str, Any]]:
        with self.connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM email_messages
                WHERE association_status = 'ambiguous'
                ORDER BY created_at DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def resolve_email_association(self, email_id: str, case_id: str) -> None:
        with self.connection() as conn:
            conn.execute(
                """
                UPDATE email_messages
                SET case_id = ?, association_status = 'linked'
                WHERE id = ? OR gmail_id = ?
                """,
                (case_id, email_id, email_id),
            )
        self.add_case_event(
            CaseEvent(
                case_id=case_id,
                event_type=CaseEventType.EMAIL_LINKED.value,
                payload_json=json.dumps({"email_id": email_id, "manual": True}),
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
