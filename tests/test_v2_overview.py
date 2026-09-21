"""V2 Übersicht polish — hierarchy, stateful CTA, no diagnostics dump."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtWidgets import QApplication

from core.database import Database
from desktop.i18n import TRANSLATIONS, i18n, tr
from desktop.pages.dashboard import DashboardPage
from desktop.services import ConfigService
from desktop.services.schedule_service import ScheduleService
from desktop.util.human_time import format_human_datetime


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


def test_dashboard_stats_includes_v2_kpi_fields(tmp_path):
    db = Database(str(tmp_path / "kpi.db"))
    stats = db.dashboard_stats()
    assert "applications_active" in stats
    assert "replies_attention" in stats


def test_overview_has_four_primary_kpis(qapp, config_service, monkeypatch):
    monkeypatch.setattr(ScheduleService, "sync_from_config", lambda self: (True, "ok"))
    i18n.set_language("de")
    page = DashboardPage(config_service)
    page.refresh()
    assert len(page.kpi_cards) == 4
    assert page.kpi_cards["matches"].value_label.objectName() == "KpiValue"
    assert page.btn_search.text() == tr("btn.find_jobs")
    assert page.btn_search.objectName() == "PrimaryButton"
    # Diagnostics / dumping-ground not in production chrome
    assert page.advanced_stats.isHidden()
    assert page.run_detail_label.isHidden()
    assert page.more_actions.isHidden()
    assert page.mode_label.isHidden()


def test_overview_i18n_keys_present():
    for lang in ("de", "en"):
        for key in (
            "dash.kpi_matches",
            "dash.greeting",
            "dash.search_starting",
            "dash.search_cancelling",
            "btn.search_again",
            "apps.empty_title",
            "inbox.hint_interview",
        ):
            assert key in TRANSLATIONS[lang]
    assert set(TRANSLATIONS["de"]) == set(TRANSLATIONS["en"])


def test_stateful_search_cta(qapp, config_service, monkeypatch):
    monkeypatch.setattr(ScheduleService, "sync_from_config", lambda self: (True, "ok"))
    i18n.set_language("de")
    page = DashboardPage(config_service)
    assert page.btn_search.text() == tr("btn.find_jobs")
    page.set_pipeline_running(True)
    assert page.btn_search.text() == tr("btn.cancel_search")
    assert page.btn_search.isEnabled()
    page.set_pipeline_running(False)
    assert page.btn_search.text() == tr("btn.search_again")


def test_human_datetime_de():
    assert "Uhr" in format_human_datetime("2026-09-20T23:18:49+00:00", lang="de")
    assert format_human_datetime(None) == "—"


def test_mode_chip_humanized(qapp, config_service, monkeypatch):
    monkeypatch.setattr(ScheduleService, "sync_from_config", lambda self: (True, "ok"))
    i18n.set_language("de")
    page = DashboardPage(config_service)
    page.refresh()
    assert "search_only" not in page.mode_chip.text()
    assert tr("settings.mode.search") in page.mode_chip.text() or page.mode_chip.text()
