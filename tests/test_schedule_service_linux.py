"""ScheduleService on non-Windows platforms (mocked, runs on the Windows CI too).

Regression: on Linux without a reachable ``systemctl`` a failed activation left
unit files in ``~/.config/systemd/user``; every later pause/remove then returned
``ok=False`` ("Zeitplaner: ... 'systemctl'"). No real scheduler is touched here:
``sys.platform`` is patched, XDG/HOME point to ``tmp_path`` and every
subprocess call is replaced.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from core.config import empty_app_config
from desktop.services import native_schedule as ns
from desktop.services import schedule_service as ss
from desktop.services.schedule_service import ScheduleService


@pytest.fixture(autouse=True)
def _no_real_processes(monkeypatch):
    """No test in this file may start a real process (scheduler commands act by name)."""

    def refuse(*args, **kwargs):
        raise AssertionError(f"real process started: {args!r}")

    monkeypatch.setattr(subprocess, "Popen", refuse)


def _cfg(tmp_path: Path, *, paused: bool, mode: str = "once_daily"):
    cfg = empty_app_config(root=tmp_path / "profile")
    cfg.settings.run_automatically = True
    cfg.settings.automation_paused = paused
    cfg.settings.schedule_mode = mode
    cfg.settings.schedule_times = ["08:00"]
    return cfg


def _no_scheduler_binary(*args, **kwargs):
    raise FileNotFoundError(2, "No such file or directory", args[0][0])


@pytest.fixture
def linux(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.setattr(ns.subprocess, "run", _no_scheduler_binary)
    return ns.paths()


def test_linux_pause_removes_orphaned_units_without_systemctl(tmp_path, linux):
    linux[0].parent.mkdir(parents=True)
    for file in linux:
        file.write_text("[Unit]\n", encoding="utf-8")
    ok, msg = ScheduleService(_cfg(tmp_path, paused=True)).sync_from_config()
    assert ok is True
    assert "deaktiviert" in msg
    assert not any(file.exists() for file in linux)


def test_linux_failed_activation_leaves_no_files_and_pause_still_works(tmp_path, linux):
    ok, msg = ScheduleService(_cfg(tmp_path, paused=False)).sync_from_config()
    assert ok is False
    assert "Zeitplaner nicht verfügbar" in msg
    assert not any(file.exists() for file in linux)
    # Repeated save/pause must stay ok (previously failed forever).
    for _ in range(2):
        ok, msg = ScheduleService(_cfg(tmp_path, paused=True)).sync_from_config()
        assert ok is True and msg


def test_linux_enable_error_rolls_back_written_units(tmp_path, linux, monkeypatch):
    calls: list[list[str]] = []

    def fake_run(command):
        calls.append(command)
        if "enable" in command:
            raise RuntimeError("Failed to connect to bus")

    monkeypatch.setattr(ns, "run", fake_run)
    ok, msg = ScheduleService(_cfg(tmp_path, paused=False)).sync_from_config()
    assert ok is False and "Failed to connect to bus" in msg
    assert not any(file.exists() for file in linux)
    assert calls[-1] == ["systemctl", "--user", "daemon-reload"]


def test_darwin_bootstrap_error_rolls_back_plist(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(ns.os, "getuid", lambda: 501, raising=False)

    def fake_run(command):
        if command[:2] == ["launchctl", "bootstrap"]:
            raise RuntimeError("Bootstrap failed: 5")

    monkeypatch.setattr(ns, "run", fake_run)
    ok, _ = ScheduleService(_cfg(tmp_path, paused=False)).sync_from_config()
    assert ok is False
    assert not ns.paths()[0].exists()
    assert ScheduleService(_cfg(tmp_path, paused=True)).sync_from_config() == (
        True,
        "Kein geplanter Task vorhanden.",
    )


def _recording_run(calls, files, fail_on):
    """Mocked native_schedule.run: records commands and whether the files existed."""

    def fake_run(command):
        calls.append((list(command), all(file.exists() for file in files)))
        if fail_on(command):
            raise subprocess.TimeoutExpired(command, 20)

    return fake_run


def test_linux_enable_timeout_after_load_unloads_on_rollback_and_pause(tmp_path, linux, monkeypatch):
    """enable --now loaded the timer, then hit the 20 s timeout: rollback and pause must unload."""
    unload = ["systemctl", "--user", "disable", "--now", f"{ns.UNIT}.timer", f"{ns.UNIT}.service"]
    calls: list[tuple[list[str], bool]] = []
    monkeypatch.setattr(ns, "run", _recording_run(calls, linux, lambda c: c[:3] == ["systemctl", "--user", "enable"]))

    ok, msg = ScheduleService(_cfg(tmp_path, paused=False)).sync_from_config()
    assert ok is False and "Zeitplaner nicht verfügbar" in msg
    assert not any(file.exists() for file in linux)
    commands = [c for c, _ in calls]
    assert commands == [
        unload,  # remove() before writing: nothing on disk, unload by name
        ["systemctl", "--user", "daemon-reload"],
        ["systemctl", "--user", "enable", "--now", f"{ns.UNIT}.timer"],  # timed out after load
        unload,  # rollback unloads by name ...
        ["systemctl", "--user", "daemon-reload"],
    ]
    assert calls[3][1] is True  # ... while the unit files still existed

    calls.clear()
    ok, msg = ScheduleService(_cfg(tmp_path, paused=True)).sync_from_config()
    assert (ok, msg) == (True, "Kein geplanter Task vorhanden.")
    assert [c for c, _ in calls] == [unload]  # pause unloads by name even without files


def test_darwin_bootstrap_timeout_after_load_unloads_on_rollback_and_pause(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(ns.os, "getuid", lambda: 501, raising=False)
    monkeypatch.setattr(ns.subprocess, "run", _no_scheduler_binary)
    files = ns.paths()
    bootout = ["launchctl", "bootout", f"gui/501/{ns.LABEL}"]
    calls: list[tuple[list[str], bool]] = []
    monkeypatch.setattr(ns, "run", _recording_run(calls, files, lambda c: c[:2] == ["launchctl", "bootstrap"]))

    ok, _ = ScheduleService(_cfg(tmp_path, paused=False)).sync_from_config()
    assert ok is False
    assert not files[0].exists()
    assert [c for c, _ in calls] == [
        bootout,
        ["launchctl", "bootstrap", "gui/501", str(files[0])],
        bootout,
    ]
    assert calls[2][1] is True  # unloaded before the plist was deleted

    calls.clear()
    assert ScheduleService(_cfg(tmp_path, paused=True)).sync_from_config() == (
        True,
        "Kein geplanter Task vorhanden.",
    )
    assert [c for c, _ in calls] == [bootout]


@pytest.fixture
def windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")

    def must_not_be_used(*args, **kwargs):
        raise AssertionError("native_schedule used on Windows")

    monkeypatch.setattr(ns, "remove", must_not_be_used)
    monkeypatch.setattr(ns, "sync", must_not_be_used)
    calls: list[list[str]] = []

    def fake_run(args, **kwargs):
        calls.append(list(args))
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(ss.subprocess, "run", fake_run)
    return calls


def test_windows_pause_still_uses_schtasks_delete(tmp_path, windows):
    ok, msg = ScheduleService(_cfg(tmp_path, paused=True)).sync_from_config()
    assert (ok, msg) == (True, "Automatischer Lauf deaktiviert.")
    assert windows and all(c[:2] == ["schtasks", "/Delete"] for c in windows)
    assert ["schtasks", "/Delete", "/TN", ss.TASK_NAME, "/F"] in windows


def test_windows_create_daily_unchanged(tmp_path, windows):
    ok, msg = ScheduleService(_cfg(tmp_path, paused=False)).sync_from_config()
    assert (ok, msg) == (True, "Täglich um 08:00.")
    create = windows[-1]
    assert create[:4] == ["schtasks", "/Create", "/TN", ss.TASK_NAME]
    assert create[create.index("/SC") + 1] == "DAILY"
    assert create[create.index("/ST") + 1] == "08:00"
    assert "--once" in create[create.index("/TR") + 1]


def test_windows_missing_schtasks_pause_is_ok(tmp_path, windows, monkeypatch):
    monkeypatch.setattr(ss.subprocess, "run", _no_scheduler_binary)
    assert ScheduleService(_cfg(tmp_path, paused=True)).sync_from_config() == (
        True,
        "Task-Planer nicht verfügbar.",
    )
