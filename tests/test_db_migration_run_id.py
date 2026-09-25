"""Regression: legacy jobs.db without run_id must migrate on Database().

Pre-run_id databases crash if SCHEMA creates idx_jobs_run_id before ALTER TABLE.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from core.database import Database
from core.models import Job

# Minimal pre-run_id schema (matches shipped DBs before 5eecb14).
LEGACY_JOBS_SCHEMA = """
CREATE TABLE jobs (
    id TEXT PRIMARY KEY,
    source TEXT,
    source_job_id TEXT,
    title TEXT,
    company TEXT,
    description TEXT,
    city TEXT,
    postal_code TEXT,
    address TEXT,
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
    updated_at TEXT
);
CREATE TABLE applications (
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
    error_message TEXT
);
CREATE TABLE geocode_cache (
    query TEXT PRIMARY KEY,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    display_name TEXT,
    cached_at TEXT
);
CREATE TABLE source_status (
    source TEXT PRIMARY KEY,
    status TEXT,
    message TEXT,
    checked_at TEXT,
    jobs_found INTEGER DEFAULT 0
);
"""


def _make_legacy_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.executescript(LEGACY_JOBS_SCHEMA)
        conn.execute(
            "INSERT INTO jobs (id, source, source_job_id, title, company, status, discovered_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("legacy-job-1", "bundesagentur", "ba-1", "Sachbearbeiter", "Alt GmbH", "new", "2026-01-01T00:00:00+00:00"),
        )
        conn.commit()
        cols = {r[1] for r in conn.execute("PRAGMA table_info(jobs)")}
        assert "run_id" not in cols
    finally:
        conn.close()


def _job_columns(path: Path) -> set[str]:
    conn = sqlite3.connect(path)
    try:
        return {r[1] for r in conn.execute("PRAGMA table_info(jobs)")}
    finally:
        conn.close()


def _indexes(path: Path) -> set[str]:
    conn = sqlite3.connect(path)
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='jobs'"
        ).fetchall()
        return {r[0] for r in rows}
    finally:
        conn.close()


def test_legacy_db_migrates_run_id_and_keeps_rows(tmp_path: Path):
    db_path = tmp_path / "legacy_jobs.db"
    _make_legacy_db(db_path)

    # Must not raise OperationalError: no such column: run_id
    db = Database(db_path)

    cols = _job_columns(db_path)
    assert "run_id" in cols
    assert "idx_jobs_run_id" in _indexes(db_path)

    job = db.get_job("legacy-job-1")
    assert job is not None
    assert job.title == "Sachbearbeiter"
    assert job.company == "Alt GmbH"
    assert job.run_id == "" or job.run_id is None or job.run_id == ""

    # Dashboard / run helpers must work after migration
    assert db.dashboard_stats()["total_jobs"] == 1
    rid = db.start_search_run()
    db.upsert_job(
        Job(
            id="legacy-job-1",
            source="bundesagentur",
            source_job_id="ba-1",
            title="Sachbearbeiter",
            company="Alt GmbH",
            run_id=rid,
        )
    )
    assert db.get_job("legacy-job-1").run_id == rid


def test_fresh_db_has_run_id(tmp_path: Path):
    db_path = tmp_path / "fresh.db"
    db = Database(db_path)
    assert "run_id" in _job_columns(db_path)
    assert "idx_jobs_run_id" in _indexes(db_path)
    assert db.dashboard_stats()["total_jobs"] == 0


def test_already_migrated_db_idempotent(tmp_path: Path):
    db_path = tmp_path / "migrated.db"
    Database(db_path)
    Database(db_path)  # second init must be safe
    assert "run_id" in _job_columns(db_path)
    assert "idx_jobs_run_id" in _indexes(db_path)


def test_legacy_then_double_open(tmp_path: Path):
    db_path = tmp_path / "legacy2.db"
    _make_legacy_db(db_path)
    Database(db_path)
    Database(db_path)
    job = Database(db_path).get_job("legacy-job-1")
    assert job is not None
    assert job.title == "Sachbearbeiter"


def test_legacy_applied_row_survives_open_without_new_tables(tmp_path: Path):
    """Bestandsdatenbank: has_applied sieht alte applied-Zeilen, kein Zusatzschema."""
    db_path = tmp_path / "legacy_applied.db"
    _make_legacy_db(db_path)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "UPDATE jobs SET status = ?, url = ?, title = ?, company = ? WHERE id = ?",
            (
                "applied",
                "https://de.indeed.com/viewjob?jk=LegacyJK&from=serp",
                "Sachbearbeiter (m/w/d)",
                "Alt GmbH",
                "legacy-job-1",
            ),
        )
        conn.commit()
        tables_before = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
    finally:
        conn.close()

    db = Database(db_path)
    twin = Job(
        id="other",
        title="sachbearbeiter",
        company="Alt",
        url="https://de.indeed.com/viewjob?jk=legacyjk&utm_source=share",
    )
    assert db.has_applied(twin) is True
    Database(db_path)
    assert Database(db_path).has_applied(twin) is True
    conn = sqlite3.connect(db_path)
    try:
        tables_after = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
    finally:
        conn.close()
    assert "applied_gen" not in tables_after
    assert tables_before <= tables_after
