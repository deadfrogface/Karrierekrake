"""Batched job upserts: same rows as per-call commits, chunk rollback, cancel."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from core.database import DEFAULT_UPSERT_CHUNK_SIZE, Database
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


def test_exception_mid_chunk_rolls_back_only_open_chunk(tmp_path: Path, monkeypatch):
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
    assert ids == {f"keep-{i}" for i in range(4)}
    # The connection is usable again; the failed chunk did not stick.
    db.upsert_job(_job(99, id="after"))
    assert db.get_job("after") is not None
    assert db.get_job("drop-0") is None


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
