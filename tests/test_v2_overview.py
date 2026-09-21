"""V2 Übersicht (dashboard) — 4 primary KPIs, quieter advanced stats."""

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
    assert stats["applications_active"] == 0
    assert stats["replies_attention"] == 0


def test_overview_has_four_primary_kpis(qapp, config_service, monkeypatch):
    monkeypatch.setattr(ScheduleService, "sync_from_config", lambda self: (True, "ok"))
    i18n.set_language("de")
    page = DashboardPage(config_service)
    page.refresh()
    assert len(page.kpi_cards) == 4
    assert set(page.kpi_cards) == {"matches", "needs_review", "applications", "replies"}
    assert page.kpi_cards["matches"].caption.text() == tr("dash.kpi_matches")
    assert page.kpi_cards["replies"].caption.text() == tr("dash.kpi_replies")
    assert page.btn_search.text() == tr("btn.find_jobs")
    assert "Diagnose" in page.advanced_section.text() or "DIAGNOSE" in page.advanced_section.text()
    advanced = page.advanced_stats.text()
    assert tr("dash.captcha") in advanced
    assert tr("dash.errors") in advanced


def test_overview_i18n_keys_present():
    for lang in ("de", "en"):
        for key in (
            "dash.kpi_matches",
            "dash.kpi_applications",
            "dash.kpi_replies",
            "dash.section_queue",
            "dash.section_kpis",
            "dash.section_advanced",
            "dash.next_inbox_cta",
        ):
            assert key in TRANSLATIONS[lang]
