"""End-to-end pipeline with fake sources (no network)."""

from __future__ import annotations

from pathlib import Path

import pytest

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
from core.models import Job, JobStatus, RemoteType
from core.source_health import SourceHealthStatus
from search.base import JobSource, SearchQuery


class _FakeSource(JobSource):
    def __init__(self, source_id: str, jobs: list[Job] | None = None, *, fail: str | None = None):
        self.source_id = source_id
        self._jobs = jobs or []
        self._fail = fail

    def search(self, queries: list[SearchQuery]) -> list[Job]:
        if self._fail:
            raise RuntimeError(self._fail)
        return list(self._jobs)


def _job(
    *,
    sid: str,
    source: str,
    title: str,
    company: str,
    remote: str = RemoteType.ONSITE.value,
    distance: float | None = 5.0,
    salary: float | None = 45000,
    salary_text: str = "",
    url: str = "",
    app_url: str = "",
) -> Job:
    return Job(
        id=f"{source}-{sid}",
        source=source,
        source_job_id=sid,
        title=title,
        company=company,
        description="Sachbearbeiter Verwaltung Excel Deutsch",
        city="Berlin",
        remote_type=remote,
        distance_km=distance,
        salary_min=salary,
        salary_text=salary_text or (f"{int(salary)} EUR / Jahr" if salary else ""),
        url=url or f"https://example.com/{source}/{sid}",
        application_url=app_url or f"https://boards.greenhouse.io/acme/jobs/{sid}",
        employment_type="Vollzeit",
    )


@pytest.fixture
def pipeline_cfg(tmp_path: Path) -> AppConfig:
    db_path = tmp_path / "data" / "jobs.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return AppConfig(
        root=tmp_path,
        profile=ProfileConfig(
            location=LocationConfig(
                home_address="Testweg 1, 10115 Berlin",
                home_latitude=52.52,
                home_longitude=13.405,
                max_distance_km=20.0,
                allow_remote_germany=True,
                allow_hybrid=True,
            ),
            jobs=JobsConfig(desired_titles=["Sachbearbeiter"]),
            employment=EmploymentConfig(
                full_time=True,
                remote=True,
                hybrid=True,
                onsite=True,
                minimum_salary=36000,
            ),
            qualifications=QualificationsConfig(skills=["Excel", "Verwaltung"]),
            filters=FiltersConfig(desired_keywords=["Verwaltung"]),
        ),
        settings=SettingsConfig(
            mode="search_only",
            dry_run=True,
            published_within_days=30,
            database_path=str(db_path),
            logs_dir=str(tmp_path / "logs"),
            enabled_sources=["good", "dup", "empty", "timeout", "far", "lowpay", "company_sites"],
            minimum_match_for_auto_apply=50,
        ),
    )


def test_pipeline_integration_counts(pipeline_cfg: AppConfig, monkeypatch, tmp_path: Path):
    # Job.source is the portal id on the allowlist. Adapter source_id stays "good".
    good = _job(sid="1", source="indeed", title="Sachbearbeiter", company="Acme GmbH")
    # Same vacancy via another board → duplicate
    dup = _job(
        sid="1b",
        source="dup",
        title="Sachbearbeiter",
        company="Acme GmbH",
        url=good.url,
        app_url=good.application_url,
    )
    far = _job(
        sid="2",
        source="far",
        title="Sachbearbeiter",
        company="FarAway AG",
        distance=80.0,
        url="https://example.com/far/2",
    )
    lowpay = _job(
        sid="3",
        source="lowpay",
        title="Sachbearbeiter",
        company="Cheap Ltd",
        salary=25000,
        salary_text="25.000 EUR / Jahr",
        remote=RemoteType.REMOTE.value,
        distance=500.0,
        url="https://example.com/low/3",
    )
    remote_ok = _job(
        sid="4",
        source="indeed",
        title="Sachbearbeiter Remote",
        company="RemoteCo",
        remote=RemoteType.REMOTE.value,
        distance=400.0,
        salary=50000,
        url="https://example.com/good/4",
        app_url="https://jobs.lever.co/remoteco/4",
    )

    sources = [
        _FakeSource("good", [good, remote_ok]),
        _FakeSource("dup", [dup]),
        _FakeSource("empty", []),
        _FakeSource("timeout", fail="Timeout after 120s"),
        _FakeSource("far", [far]),
        _FakeSource("lowpay", [lowpay]),
        _FakeSource("company_sites", []),
    ]

    monkeypatch.setattr("app.main.build_sources", lambda enabled: sources)
    # Skip network geocoding — jobs already carry distances.
    monkeypatch.setattr(
        "app.main.enrich_job_locations",
        lambda jobs, location, progress_callback=None, should_stop=None: jobs,
    )

    stats = run_pipeline(config=pipeline_cfg, mode="search_only")

    # Exact accounting expectations:
    # raw: good(2) + dup(1) + far(1) + lowpay(1) + empty(0) + timeout(0) + company_sites(0) = 5
    assert stats["raw_results"] == 5
    assert stats["total"] == 5
    # One hard-URL duplicate
    assert stats["duplicates"] == 1
    # Far onsite over radius ignored
    assert stats["distance_removed"] >= 1
    # Pipeline continues after timeout source
    assert any("timeout" in e.lower() for e in stats["source_errors"])
    assert stats["source_results"]["timeout"]["status"] == SourceHealthStatus.TIMEOUT.value
    assert stats["source_results"]["empty"]["status"] == SourceHealthStatus.OK_EMPTY.value
    assert stats["source_results"]["company_sites"]["status"] == SourceHealthStatus.OK_EMPTY.value
    # New jobs upserted (primary non-dup)
    assert stats["new"] >= 2
    assert stats["matches"] >= 1
    # Required stats keys
    for key in (
        "raw_results",
        "duplicates",
        "distance_removed",
        "new",
        "matches",
        "applied",
        "needs_review",
        "run_id",
        "source_errors",
        "source_results",
        "ats_supported",
        "ats_unknown",
        "cancelled",
    ):
        assert key in stats

    from core.database import Database

    db = Database(pipeline_cfg.db_path)
    ignored = db.list_jobs(statuses=[JobStatus.IGNORED.value], hide_duplicates=False)
    assert len(ignored) >= 2
    assert stats["new"] == 3
    assert stats["matches"] == 2
    assert stats["duplicates"] == 1
    assert stats["distance_removed"] == 1
