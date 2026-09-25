"""V2 Settings side-nav IA smoke tests."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtWidgets import QApplication

from desktop.i18n import TRANSLATIONS, i18n, tr
from desktop.pages.settings import SettingsPage, _SETTINGS_NAV_KEYS


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
    monkeypatch.setattr(
        "desktop.services.schedule_service.ScheduleService.sync_from_config",
        lambda self: (True, "ok"),
    )
    from desktop.services import ConfigService

    return ConfigService()


def test_settings_nav_i18n_keys():
    for key in _SETTINGS_NAV_KEYS:
        assert key in TRANSLATIONS["de"]
        assert key in TRANSLATIONS["en"]
    for key in ("settings.safety_limits", "settings.danger_zone"):
        assert key in TRANSLATIONS["de"]
        assert key in TRANSLATIONS["en"]
    assert set(TRANSLATIONS["de"]) == set(TRANSLATIONS["en"])


def test_settings_side_nav_has_six_sections(qapp, config_service):
    i18n.set_language("de")
    page = SettingsPage(config_service)
    assert page.nav.count() == 6
    assert page.stack.count() == 6
    assert page.nav.item(1).text() == tr("settings.nav.automation")
    # Demo default: Automation selected
    assert page.nav.currentRow() == 1
    assert page.stack.currentIndex() == 1


def test_settings_nav_switches_stack(qapp, config_service):
    page = SettingsPage(config_service)
    page.nav.setCurrentRow(0)
    assert page.stack.currentIndex() == 0
    page.nav.setCurrentRow(4)
    assert page.stack.currentIndex() == 4


def test_settings_controls_still_present(qapp, config_service):
    page = SettingsPage(config_service)
    page.load_from_config()
    assert page.jobs_per_search.count() == 10
    assert page.search_mode.count() == 2
    assert page.mode_review is not None
    assert page.privacy_export_btn is not None
    assert page.guenther_box is not None
    assert not hasattr(page, "guenther_enabled")
    assert page.safety_toggle is not None
    assert page.danger_toggle is not None
    # Progressive disclosure starts collapsed
    assert page.apply_box.isHidden()
    assert page.danger_box.isHidden()
    page.safety_toggle.setChecked(True)
    assert not page.apply_box.isHidden()
