"""Browser/apply exceptions must finish the search_run as error, not ok."""

from __future__ import annotations

from pathlib import Path

from app.main import run_pipeline
from core.config import empty_app_config
from core.database import Database
from core.models import Job, RemoteType
from search.base import JobSource, SearchQuery


class _OneJobSource(JobSource):
    source_id = "test"

    def __init__(self, job: Job) -> None:
        self._job = job

    def search(self, queries: list[SearchQuery]) -> list[Job]:
        return [self._job]


def test_browser_exception_finishes_run_as_error(tmp_path: Path, monkeypatch) -> None:
    cfg = empty_app_config(root=tmp_path)
    cfg.settings.mode = "review_before_submit"
    cfg.settings.dry_run = True
    cfg.settings.database_path = str(tmp_path / "data" / "jobs.db")
    cfg.settings.logs_dir = str(tmp_path / "logs")
    cfg.settings.browser_profile_dir = str(tmp_path / "browser")
    cfg.settings.enabled_sources = ["test"]
    cfg.settings.minimum_match_for_auto_apply = 0
    cfg.profile.jobs.desired_titles = ["Buchhalter"]
    cfg.profile.location.home_address = "Testweg 1, 10115 Berlin"
    cfg.profile.location.home_latitude = 52.52
    cfg.profile.location.home_longitude = 13.405
    cfg.profile.location.max_distance_km = 50.0
    cfg.profile.employment.full_time = True
    cfg.profile.employment.onsite = True
    cfg.profile.employment.minimum_salary = 0

    job = Job(
        id="test-1",
        source="indeed",
        source_job_id="1",
        title="Buchhalter",
        company="ACME",
        description="Buchhaltung Excel Deutsch",
        city="Berlin",
        remote_type=RemoteType.ONSITE.value,
        distance_km=5.0,
        salary_min=45000,
        url="https://example.com/jobs/1",
        application_url="https://boards.greenhouse.io/acme/jobs/1",
        employment_type="Vollzeit",
        ats_type="greenhouse",
    )

    monkeypatch.setattr(
        "app.main.build_sources",
        lambda enabled: [_OneJobSource(job)],
    )
    monkeypatch.setattr(
        "app.main.enrich_job_locations",
        lambda jobs, location, progress_callback=None, should_stop=None: jobs,
    )

    class _BoomBrowser:
        def __init__(self, *args, **kwargs) -> None:
            raise RuntimeError("browser launch failed")

    monkeypatch.setattr("app.main.BrowserManager", _BoomBrowser)

    stats = run_pipeline(cfg, mode="review_before_submit")
    assert stats.get("apply_error")
    assert "browser launch failed" in str(stats["apply_error"]).lower()

    db = Database(cfg.db_path)
    with db.connection() as conn:
        row = conn.execute(
            "SELECT status, stats_json FROM search_runs ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
    assert row is not None
    assert row[0] == "error"
    assert "browser launch failed" in (row[1] or "").lower()
