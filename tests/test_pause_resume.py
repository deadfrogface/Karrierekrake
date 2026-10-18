"""Pause/resume automation toggle, persistence, and dashboard button labels."""

from __future__ import annotations

import os
import subprocess

import pytest

from desktop.i18n import i18n, tr
from desktop.services import ConfigService
from desktop.services.schedule_service import ScheduleService


@pytest.fixture(autouse=True)
def _no_real_processes(monkeypatch):
    """No test in this file may start a real process (scheduler commands act by name)."""

    def refuse(*args, **kwargs):
        raise AssertionError(f"real process started: {args!r}")

    monkeypatch.setattr(subprocess, "Popen", refuse)


@pytest.fixture
def config_service(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    # Ensure path helpers see the temp AppData root.
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


def test_toggle_active_paused_and_persistence(config_service, monkeypatch):
    monkeypatch.setattr(ScheduleService, "sync_from_config", lambda self: (True, "ok"))
    cfg = config_service.load()
    assert cfg.settings.automation_paused is False

    cfg.settings.automation_paused = True
    config_service.save(cfg)
    again = config_service.load()
    assert again.settings.automation_paused is True

    again.settings.automation_paused = False
    config_service.save(again)
    assert config_service.load().settings.automation_paused is False


def test_scheduler_sees_paused(config_service, monkeypatch):
    removed = {"called": False}

    def fake_remove(self):
        removed["called"] = True
        return True, "deaktiviert"

    monkeypatch.setattr(ScheduleService, "remove_task", fake_remove)
    cfg = config_service.load()
    cfg.settings.run_automatically = True
    cfg.settings.automation_paused = True
    config_service.save(cfg)
    ok, msg = ScheduleService(config_service.load()).sync_from_config()
    assert ok is True
    assert removed["called"] is True


def test_dashboard_pause_button_labels(config_service, monkeypatch):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6.QtWidgets")
    from PySide6.QtWidgets import QApplication

    from desktop.pages.dashboard import DashboardPage

    monkeypatch.setattr(ScheduleService, "sync_from_config", lambda self: (True, "ok"))
    app = QApplication.instance() or QApplication([])
    i18n.set_language("de")
    page = DashboardPage(config_service)

    cfg = config_service.load()
    cfg.settings.automation_paused = False
    config_service.save(cfg)
    page.refresh()
    assert page.btn_pause.text() == tr("btn.pause_automation")
    assert page.btn_pause.text() == "Automation pausieren"

    cfg.settings.automation_paused = True
    config_service.save(cfg)
    page.refresh()
    assert page.btn_pause.text() == tr("btn.resume_automation")
    assert page.btn_pause.text() == "Automation fortsetzen"

    i18n.set_language("en")
    page.refresh()
    assert page.btn_pause.text() == "Resume automation"

    # Toggle helper used by MainWindow
    from desktop.main_window import MainWindow

    # Avoid tray / geometry side effects: only exercise set_automation_paused path via service
    cfg = config_service.load()
    was = bool(cfg.settings.automation_paused)
    cfg.settings.automation_paused = not was
    config_service.save(cfg)
    assert config_service.load().settings.automation_paused is (not was)
    _ = app  # keep QApplication alive
    _ = MainWindow  # import smoke
