"""Batched job upserts: same rows as per-call commits, savepoints, cancel."""

from __future__ import annotations

import copy
import sqlite3
import threading
import time
from pathlib import Path

import pytest

from core.database import BUSY_TIMEOUT_S, DEFAULT_UPSERT_CHUNK_SIZE, Database
from core.known_jobs import should_suppress_as_new
from core.models import Job, JobStatus


def _job(i: int, **overrides) -> Job:
    data = dict(
        id=f"job-{i:04d}",
        source="board",
        source_job_id=str(i),
        title=f"Sachbearbeiter {i}",
        company=f"Müller {i} GmbH",
        description=f"Excel Verwaltung {i}",
        city="Berlin",
        postal_code="10115",
        country_code="DE",
        distance_km=float(i % 30),
        remote_type="onsite" if i % 2 == 0 else "remote",
        employment_type="Vollzeit",
        salary_min=30000 + i,
        salary_text=f"{30000 + i} EUR",
        url=f"https://example.test/jobs/{i}",
        application_url=f"https://boards.greenhouse.io/acme/jobs/{i}",
        match_score=i % 101,
        match_reasons=[f"grund {i}", "äöü"],
        rejection_reasons=["zu weit"] if i % 5 == 0 else [],
        alt_sources=["dup-source"] if i % 7 == 0 else [],
        status=JobStatus.NEW.value,
        duplicate_of=None,
        run_id="run-compare",
        ranking_version="rank-v1",
        discovered_at="2026-09-01T12:00:00+00:00",
        latitude=52.52,
        longitude=13.405,
    )
    data.update(overrides)
    return Job(**data)


def _rows(db: Database) -> list[tuple]:
    with db.connection() as conn:
        return [
            tuple(row)
            for row in conn.execute("SELECT * FROM jobs ORDER BY id").fetchall()
        ]


def _count(db: Database) -> int:
    with db.connection() as conn:
        return int(conn.execute("SELECT COUNT(*) AS c FROM jobs").fetchone()["c"])


def test_upsert_jobs_matches_single_upserts_row_for_row(tmp_path: Path, monkeypatch):
    """1000 writes, including status protection inside one chunk and across a commit."""
    monkeypatch.setattr(
        "core.database.utc_now_iso", lambda: "2026-01-15T00:00:00+00:00"
    )
    single = Database(tmp_path / "single.db")
    batched = Database(tmp_path / "batch.db")
    seeds = [
        _job(9001, id="protect-applied", status=JobStatus.APPLIED.value, source_job_id="pa"),
        _job(9002, id="protect-failed", status=JobStatus.FAILED.value, source_job_id="pf"),
        _job(9003, id="protect-applying", status=JobStatus.APPLYING.value, source_job_id="pg"),
    ]
    sequence = [_job(i) for i in range(1000)]
    sequence[10] = _job(10, id="intra", status=JobStatus.APPLYING.value, source_job_id="intra")
    sequence[11] = _job(11, id="intra", status=JobStatus.NEW.value, source_job_id="intra-b")
    sequence[20] = _job(20, id="protect-applied", status=JobStatus.NEW.value, source_job_id="pa")
    sequence[21] = _job(
        21, id="protect-failed", status=JobStatus.IGNORED.value, source_job_id="pf"
    )
    sequence[22] = _job(
        22,
        id="protect-applying",
        status=JobStatus.INTERESTING.value,
        source_job_id="pg",
    )
    # Default chunk is 500, so index 499 commits before index 500 is written.
    assert DEFAULT_UPSERT_CHUNK_SIZE == 500
    sequence[499] = _job(499, id="cross", status=JobStatus.APPLYING.value, source_job_id="cross")
    sequence[500] = _job(500, id="cross", status=JobStatus.NEW.value, source_job_id="cross-b")

    for db in (single, batched):
        for job in copy.deepcopy(seeds):
            db.upsert_job(job)
    for job in copy.deepcopy(sequence):
        single.upsert_job(job)
    written = batched.upsert_jobs(copy.deepcopy(sequence))
    assert written == 1000

    assert _rows(single) == _rows(batched)
    for db in (single, batched):
        assert db.get_job("protect-applied").status == JobStatus.APPLIED.value
        assert db.get_job("protect-failed").status == JobStatus.FAILED.value
        assert db.get_job("protect-applying").status == JobStatus.APPLYING.value
        assert db.get_job("intra").status == JobStatus.APPLYING.value
        assert db.get_job("cross").status == JobStatus.APPLYING.value


def test_exception_mid_chunk_keeps_successful_jobs(tmp_path: Path, monkeypatch):
    """A raise leaves the block: jobs already upserted stay, like per-call commits."""
    db = Database(tmp_path / "t.db")
    first = [_job(i, id=f"keep-{i}") for i in range(4)]
    db.upsert_jobs(first, chunk_size=10)
    assert _count(db) == 4

    second = [_job(i, id=f"drop-{i}") for i in range(5)]
    real = Database.upsert_job
    calls = {"n": 0}

    def boom(self, job):
        calls["n"] += 1
        if calls["n"] == 3:
            raise RuntimeError("mid-chunk")
        return real(self, job)

    monkeypatch.setattr(Database, "upsert_job", boom)
    with pytest.raises(RuntimeError, match="mid-chunk"):
        db.upsert_jobs(second, chunk_size=10)

    ids = {row[0] for row in _rows(db)}
    assert {f"keep-{i}" for i in range(4)} <= ids
    assert "drop-0" in ids
    assert "drop-1" in ids
    assert "drop-2" not in ids
    assert "drop-3" not in ids
    assert "drop-4" not in ids
    db.upsert_job(_job(99, id="after"))
    assert db.get_job("after") is not None


def _poison_write(self, job: Job) -> None:
    if job.id == "poison":
        with self.connection() as conn:
            conn.execute(
                "INSERT INTO jobs (id, title, status) VALUES (?, ?, ?)",
                ("poison-scratch", "scratch", "new"),
            )
            raise RuntimeError("poison")
    _WRITE_JOB(self, job)


_WRITE_JOB = Database._write_job


def _write_continuing(db: Database, jobs: list[Job]) -> list[str]:
    errors: list[str] = []
    for job in jobs:
        try:
            db.upsert_job(job)
        except RuntimeError as exc:
            errors.append(str(exc))
    return errors


def test_poisoned_job_in_block_matches_single_upsert(tmp_path: Path, monkeypatch):
    """One poisoned job mid-block: every other row matches the single-upsert path."""
    monkeypatch.setattr(
        "core.database.utc_now_iso", lambda: "2026-01-15T00:00:00+00:00"
    )
    monkeypatch.setattr(Database, "_write_job", _poison_write)
    jobs = [_job(i) for i in range(30)]
    jobs[14] = _job(14, id="poison", source_job_id="poison")
    single = Database(tmp_path / "single.db")
    batched = Database(tmp_path / "batch.db")
    single_errors = _write_continuing(single, copy.deepcopy(jobs))
    with batched.batch(chunk_size=10):
        batch_errors = _write_continuing(batched, copy.deepcopy(jobs))
    assert single_errors == ["poison"]
    assert batch_errors == ["poison"]
    assert _rows(single) == _rows(batched)
    assert single.get_job("poison") is None
    assert single.get_job("poison-scratch") is None
    assert batched.get_job("poison") is None
    assert batched.get_job("poison-scratch") is None
    for i in range(30):
        if i == 14:
            continue
        assert single.get_job(f"job-{i:04d}") is not None
    assert _count(single) == 29


def test_batch_does_not_demote_applied(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "core.database.utc_now_iso", lambda: "2026-01-15T00:00:00+00:00"
    )
    db = Database(tmp_path / "t.db")
    db.upsert_job(_job(1, id="keep-applied", status=JobStatus.APPLIED.value))
    incoming = _job(
        1,
        id="keep-applied",
        status=JobStatus.NEW.value,
        title="Andere Stelle",
        source_job_id="demote",
    )
    with db.batch(chunk_size=10):
        db.upsert_job(_job(2, id="sibling"))
        db.upsert_job(incoming)
        db.upsert_job(_job(3, id="after-applied"))
    stored = db.get_job("keep-applied")
    assert stored is not None
    assert stored.status == JobStatus.APPLIED.value
    assert incoming.status == JobStatus.APPLIED.value
    assert db.get_job("sibling") is not None
    assert db.get_job("after-applied") is not None


def test_second_connection_writes_during_batch_without_lock_error(tmp_path: Path):
    """A UI-style status mark waits out the chunk lock and does not see 'database is locked'."""
    assert BUSY_TIMEOUT_S >= 1.0
    path = tmp_path / "t.db"
    setup = Database(path)
    setup.upsert_job(_job(0, id="ui-mark", status=JobStatus.NEW.value))
    marker_db = Database(path)
    started = threading.Event()
    finished = threading.Event()
    errors: list[BaseException] = []
    marked: dict[str, object] = {}

    def writer() -> None:
        db = Database(path)
        jobs = [_job(i) for i in range(1, 21)]
        try:
            with db.batch(chunk_size=1000):
                db.upsert_job(jobs[0])
                started.set()
                time.sleep(0.3)
                for job in jobs[1:]:
                    db.upsert_job(job)
        except BaseException as exc:
            errors.append(exc)
        finally:
            finished.set()

    def marker() -> None:
        if not started.wait(5):
            errors.append(TimeoutError("batch did not start"))
            return
        marked["during"] = not finished.is_set()
        try:
            marker_db.update_job_status("ui-mark", JobStatus.APPLIED.value)
        except BaseException as exc:
            errors.append(exc)

    threads = [
        threading.Thread(target=writer),
        threading.Thread(target=marker),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(10)
        assert not thread.is_alive()
    assert errors == []
    assert marked["during"] is True
    assert marker_db.get_job("ui-mark").status == JobStatus.APPLIED.value
    assert _count(Database(path)) == 21


def test_update_job_status_lock_raises_and_keeps_status(
    tmp_path: Path, monkeypatch
):
    path = tmp_path / "t.db"
    db = Database(path)
    db.upsert_job(_job(1, id="mark", status=JobStatus.NEW.value))
    monkeypatch.setattr("core.database.BUSY_TIMEOUT_S", 0.2)
    holder = sqlite3.connect(path)
    try:
        holder.execute("BEGIN IMMEDIATE")
        with pytest.raises(sqlite3.OperationalError, match="locked"):
            db.update_job_status("mark", JobStatus.APPLIED.value)
    finally:
        holder.rollback()
        holder.close()
    assert db.get_job("mark").status == JobStatus.NEW.value


def test_stop_after_chunk_keeps_committed_jobs(tmp_path: Path):
    path = tmp_path / "t.db"
    db = Database(path)
    jobs = [_job(i) for i in range(25)]

    def should_stop() -> bool:
        reader = Database(path)
        return _count(reader) >= 10

    written = db.upsert_jobs(jobs, chunk_size=10, should_stop=should_stop)
    assert written == 10
    assert _count(db) == 10
    assert _count(Database(path)) == 10
    kept = {row[0] for row in _rows(db)}
    assert kept == {f"job-{i:04d}" for i in range(10)}


def test_connections_use_wal_and_busy_timeout(tmp_path: Path):
    db = Database(tmp_path / "t.db")
    with db.connection() as conn:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        sync = conn.execute("PRAGMA synchronous").fetchone()[0]
        timeout_ms = conn.execute("PRAGMA busy_timeout").fetchone()[0]
    assert mode == "wal"
    assert sync == 1  # NORMAL
    assert timeout_ms == int(BUSY_TIMEOUT_S * 1000)


def test_single_upsert_still_commits_immediately(tmp_path: Path):
    path = tmp_path / "t.db"
    db = Database(path)
    db.upsert_job(_job(1))
    assert Database(path).get_job("job-0001") is not None


def test_transaction_and_batch_rollback_and_commit(tmp_path: Path):
    path = tmp_path / "t.db"
    db = Database(path)
    with pytest.raises(RuntimeError, match="nope"):
        with db.transaction():
            db.upsert_job(_job(1, id="rolled"))
            raise RuntimeError("nope")
    assert db.get_job("rolled") is None
    assert db._txn_conn is None

    with db.batch():
        db.upsert_job(_job(2, id="kept"))
    assert Database(path).get_job("kept") is not None


def test_open_chunk_visibility_same_connection_versus_other(tmp_path: Path):
    """Status protection reads the chunk connection.

    ``find_existing_by_source``, ``has_applied`` and ``should_suppress_as_new``
    each open their own connection. An uncommitted chunk is invisible to them
    and visible to ``get_job`` on the writing connection. The search pipeline
    calls those three helpers only while scoring, before any persist chunk
    is open (see ``test_pipeline_reads_are_outside_upsert_transaction``).
    """
    path = tmp_path / "t.db"
    db = Database(path)
    other = Database(path)
    job = _job(1, id="vis", title="Sachbearbeiter", company="Acme GmbH")
    with db.transaction():
        db.upsert_job(job)
        assert db.get_job("vis") is not None
        assert other.get_job("vis") is None
        assert other.find_existing_by_source(job.source, job.source_job_id) is None
        assert other.has_applied(job) is False
        suppress, _reason = should_suppress_as_new(other, job)
        assert suppress is False
    assert other.find_existing_by_source(job.source, job.source_job_id) is not None


def test_pipeline_reads_are_outside_upsert_transaction(tmp_path: Path, monkeypatch):
    from app.main import run_pipeline
    from core.config import (
        AppConfig,
        EmploymentConfig,
        FiltersConfig,
        JobsConfig,
        LocationConfig,
        ProfileConfig,
        QualificationsConfig,
        SettingsConfig,
    )
    from search.base import JobSource

    db_path = tmp_path / "data" / "jobs.db"
    db_path.parent.mkdir(parents=True)
    (tmp_path / "logs").mkdir()
    address = "Testweg 1, 10115 Berlin"
    cfg = AppConfig(
        root=tmp_path,
        profile=ProfileConfig(
            location=LocationConfig(
                home_address=address,
                home_geocoded_address=address,
                home_latitude=52.52,
                home_longitude=13.405,
                max_distance_km=20.0,
                allow_remote_germany=True,
                allow_hybrid=True,
            ),
            jobs=JobsConfig(desired_titles=["Sachbearbeiter"]),
            employment=EmploymentConfig(
                full_time=True, remote=True, hybrid=True, onsite=True, minimum_salary=36000
            ),
            qualifications=QualificationsConfig(skills=["Excel", "Verwaltung"]),
            filters=FiltersConfig(desired_keywords=["Verwaltung"]),
        ),
        settings=SettingsConfig(
            mode="search_only",
            dry_run=True,
            database_path=str(db_path),
            logs_dir=str(tmp_path / "logs"),
            enabled_sources=["good"],
            minimum_match_for_auto_apply=50,
        ),
    )
    jobs = [
        _job(
            i,
            id=f"good-{i}",
            source="good",
            source_job_id=str(i),
            title="Sachbearbeiter",
            company=f"Firma {i} GmbH",
            description="Sachbearbeiter Verwaltung Excel Deutsch",
            distance_km=5.0,
            salary_min=45000,
            salary_text="45000 EUR / Jahr",
            url=f"https://example.com/good/{i}",
            application_url=f"https://boards.greenhouse.io/acme/jobs/{i}",
        )
        for i in range(3)
    ]

    class _Src(JobSource):
        source_id = "good"

        def search(self, queries):
            return list(jobs)

    monkeypatch.setattr("app.main.build_sources", lambda enabled: [_Src()])
    monkeypatch.setattr(
        "app.main.enrich_job_locations",
        lambda jobs_in, location, progress_callback=None, should_stop=None: jobs_in,
    )

    read_inside: list[bool] = []
    for name in ("find_existing_by_source", "has_applied", "find_case_for_job"):
        real = getattr(Database, name)

        def wrapped(self, *args, _real=real, **kwargs):
            read_inside.append(self._txn_conn is not None)
            return _real(self, *args, **kwargs)

        monkeypatch.setattr(Database, name, wrapped)

    real_upsert = Database.upsert_job
    upsert_inside: list[bool] = []

    def wrapped_upsert(self, job):
        upsert_inside.append(self._txn_conn is not None)
        return real_upsert(self, job)

    monkeypatch.setattr(Database, "upsert_job", wrapped_upsert)

    stats = run_pipeline(config=cfg, mode="search_only")
    assert stats["cancelled"] is False
    assert read_inside, "pipeline did not read existing jobs"
    assert all(flag is False for flag in read_inside)
    assert upsert_inside, "pipeline did not upsert"
    assert all(flag is True for flag in upsert_inside)
    assert _count(Database(db_path)) >= 3


def test_pipeline_stop_after_chunk_keeps_committed_jobs(tmp_path: Path, monkeypatch):
    from app.main import run_pipeline
    from core.config import (
        AppConfig,
        EmploymentConfig,
        FiltersConfig,
        JobsConfig,
        LocationConfig,
        ProfileConfig,
        QualificationsConfig,
        SettingsConfig,
    )
    from search.base import JobSource

    monkeypatch.setattr("core.database.DEFAULT_UPSERT_CHUNK_SIZE", 2)
    db_path = tmp_path / "data" / "jobs.db"
    db_path.parent.mkdir(parents=True)
    (tmp_path / "logs").mkdir()
    address = "Testweg 1, 10115 Berlin"
    cfg = AppConfig(
        root=tmp_path,
        profile=ProfileConfig(
            location=LocationConfig(
                home_address=address,
                home_geocoded_address=address,
                home_latitude=52.52,
                home_longitude=13.405,
                max_distance_km=20.0,
                allow_remote_germany=True,
                allow_hybrid=True,
            ),
            jobs=JobsConfig(desired_titles=["Sachbearbeiter"]),
            employment=EmploymentConfig(
                full_time=True, remote=True, hybrid=True, onsite=True, minimum_salary=36000
            ),
            qualifications=QualificationsConfig(skills=["Excel", "Verwaltung"]),
            filters=FiltersConfig(desired_keywords=["Verwaltung"]),
        ),
        settings=SettingsConfig(
            mode="search_only",
            dry_run=True,
            database_path=str(db_path),
            logs_dir=str(tmp_path / "logs"),
            enabled_sources=["good"],
            minimum_match_for_auto_apply=50,
        ),
    )
    jobs = [
        _job(
            i,
            id=f"good-{i}",
            source="good",
            source_job_id=str(i),
            title="Sachbearbeiter",
            company=f"Firma {i} GmbH",
            description="Sachbearbeiter Verwaltung Excel Deutsch",
            distance_km=5.0,
            salary_min=45000,
            salary_text="45000 EUR / Jahr",
            url=f"https://example.com/good/{i}",
            application_url=f"https://boards.greenhouse.io/acme/jobs/{i}",
        )
        for i in range(6)
    ]

    class _Src(JobSource):
        source_id = "good"

        def search(self, queries):
            return list(jobs)

    monkeypatch.setattr("app.main.build_sources", lambda enabled: [_Src()])
    monkeypatch.setattr(
        "app.main.enrich_job_locations",
        lambda jobs_in, location, progress_callback=None, should_stop=None: jobs_in,
    )

    def should_stop() -> bool:
        if not db_path.exists():
            return False
        return _count(Database(db_path)) >= 2

    stats = run_pipeline(config=cfg, mode="search_only", should_stop=should_stop)
    assert stats["cancelled"] is True
    assert _count(Database(db_path)) == 2
    with Database(db_path).connection() as conn:
        run = conn.execute("SELECT status, stats_json FROM search_runs").fetchone()
    assert run["status"] == "cancelled"
