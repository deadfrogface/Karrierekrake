"""V2 Jobs page — filter/sort separation and 60/40 shell."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtWidgets import QApplication

from core.database import Database
from core.models import Job
from desktop.i18n import TRANSLATIONS, i18n, tr
from desktop.pages.jobs import JobsPage
from desktop.services import ConfigService
from desktop.services.schedule_service import ScheduleService


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def config_service(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    from desktop import paths as paths_mod

    def fake_dirs():
        root = tmp_path / "Karrierekrake"
        dirs = {
            "root": root,
            "config": root / "config",
            "data": root / "data",
            "logs": root / "logs",
            "browser_profile": root / "browser_profile",
            "browsers": root / "browsers",
            "cvs": root / "cvs",
            "cache": root / "cache",
            "cover_letters": root / "cover_letters",
        }
        for p in dirs.values():
            p.mkdir(parents=True, exist_ok=True)
        return dirs

    monkeypatch.setattr(paths_mod, "ensure_app_dirs", fake_dirs)
    monkeypatch.setattr("desktop.services.ensure_app_dirs", fake_dirs)
    return ConfigService()


def _seed(db: Database, *, score: int, distance: float | None, title: str, remote: str = "hybrid") -> None:
    job = Job(
        id=f"j-{title}",
        title=title,
        company="Acme",
        city="Berlin",
        source="test",
        source_job_id=title,
        url="https://example.com/job",
        match_score=score,
        distance_km=distance,
        remote_type=remote,
        status="new",
        discovered_at="2026-01-01T10:00:00",
    )
    db.upsert_job(job)


def test_jobs_age_days_hidden(qapp, config_service):
    page = JobsPage(config_service)
    assert hasattr(page, "age_days")
    assert page.age_days.isHidden()


def test_jobs_sort_does_not_discard_rows(qapp, config_service, monkeypatch):
    monkeypatch.setattr(ScheduleService, "sync_from_config", lambda self: (True, "ok"))
    i18n.set_language("de")
    cfg = config_service.load()
    db = Database(cfg.db_path)
    _seed(db, score=95, distance=5.0, title="A")
    _seed(db, score=80, distance=50.0, title="B")
    _seed(db, score=88, distance=None, title="C", remote="remote")
    page = JobsPage(config_service)
    page.min_match.setValue(75)
    page.max_dist.setValue(500)
    page.refresh()
    assert page.table.rowCount() == 3
    before = page.table.rowCount()
    page.sort.setCurrentIndex(page.sort.findData("match_asc"))
    assert page.table.rowCount() == before == 3
    assert page.table.item(0, 0).text() == "B"
    page.sort.setCurrentIndex(page.sort.findData("distance_near"))
    assert page.table.rowCount() == 3
    assert page.table.item(0, 0).text() == "A"


def test_jobs_search_intent_separated_from_filters(qapp, config_service):
    i18n.set_language("de")
    page = JobsPage(config_service)
    assert page.search_intent_btn.text() == tr("jobs.open_search_intent")
    assert "Suchparameter" in page.search_intent_btn.text()
    assert page.lbl_filters.text() == tr("jobs.section_result_filters")
    assert "sort_match_desc" in TRANSLATIONS["de"] or "jobs.sort_match_desc" in TRANSLATIONS["de"]
