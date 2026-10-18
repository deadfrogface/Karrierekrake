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
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg-data"))  # timer stamp dir, never the real home
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


STOP_TIMER = ["systemctl", "--user", "stop", f"{ns.UNIT}.timer"]
STOP_SERVICE = ["systemctl", "--user", "stop", f"{ns.UNIT}.service"]
DISABLE_TIMER = ["systemctl", "--user", "disable", f"{ns.UNIT}.timer"]
DISABLE_SERVICE = ["systemctl", "--user", "disable", f"{ns.UNIT}.service"]
RELOAD = ["systemctl", "--user", "daemon-reload"]
CLEAN_TIMER = ["systemctl", "--user", "clean", "--what=state", f"{ns.UNIT}.timer"]  # once_daily: Persistent=true


def test_linux_enable_timeout_after_load_unloads_on_rollback_and_pause(tmp_path, linux, monkeypatch):
    """enable --now loaded the timer, then hit the 20 s timeout: rollback and pause must unload."""
    calls: list[tuple[list[str], bool]] = []
    monkeypatch.setattr(ns, "run", _recording_run(calls, linux, lambda c: c[:3] == ["systemctl", "--user", "enable"]))

    ok, msg = ScheduleService(_cfg(tmp_path, paused=False)).sync_from_config()
    assert ok is False and "Zeitplaner nicht verfügbar" in msg
    assert not any(file.exists() for file in linux)
    commands = [c for c, _ in calls]
    assert commands == [
        STOP_TIMER,  # remove() before writing: nothing on disk, stop by name only
        STOP_SERVICE,
        RELOAD,
        ["systemctl", "--user", "enable", "--now", f"{ns.UNIT}.timer"],  # timed out after load
        STOP_TIMER,  # rollback stops by name ...
        STOP_SERVICE,
        CLEAN_TIMER,  # ... cleans the persistent timer state ...
        DISABLE_TIMER,  # ... and disables both existing units
        DISABLE_SERVICE,
        RELOAD,
    ]
    assert all(existed for _, existed in calls[4:9])  # while the unit files still existed

    calls.clear()
    ok, msg = ScheduleService(_cfg(tmp_path, paused=True)).sync_from_config()
    assert (ok, msg) == (True, "Kein geplanter Task vorhanden.")
    assert [c for c, _ in calls] == [STOP_TIMER, STOP_SERVICE]  # by name, no disable without files


def _systemd_like_run(calls, files):
    """Mocked run(): like real systemd, ``stop`` of an unloaded unit and ``disable``
    of a unit without a file fail; records (command, service file exists, timer file exists)."""
    loaded: set[str] = set()

    def fake_run(command):
        calls.append((list(command), files[0].exists(), files[1].exists()))
        verb, units = command[2], [c for c in command[3:] if not c.startswith("--")]
        if verb == "stop":
            for unit in units:
                if unit not in loaded:
                    raise RuntimeError(f"Failed to stop {unit}: Unit {unit} not loaded.")
                loaded.discard(unit)
        elif verb == "disable":
            for unit in units:
                file = files[1] if unit.endswith(".timer") else files[0]
                if not file.exists():
                    raise RuntimeError(f"Failed to disable unit: Unit file {unit} does not exist.")
        elif verb == "enable" and "--now" in command:
            loaded.update(units)

    fake_run.loaded = loaded
    return fake_run


def test_linux_on_login_enable_timeout_rolls_back_without_timer_and_pause_ok(tmp_path, linux, monkeypatch):
    """on_login writes only the service: rollback disables the existing service (no
    default.target.wants symlink left) and never disables the absent timer."""
    calls: list[tuple[list[str], bool, bool]] = []
    base = _systemd_like_run(calls, linux)

    def fake_run(command):
        base(command)
        if command[:3] == ["systemctl", "--user", "enable"]:
            raise subprocess.TimeoutExpired(command, 20)

    monkeypatch.setattr(ns, "run", fake_run)
    ok, msg = ScheduleService(_cfg(tmp_path, paused=False, mode="on_login")).sync_from_config()
    assert ok is False and "Zeitplaner nicht verfügbar" in msg
    assert not any(file.exists() for file in linux)
    assert [c for c, *_ in calls] == [
        STOP_TIMER,
        STOP_SERVICE,
        RELOAD,
        ["systemctl", "--user", "enable", f"{ns.UNIT}.service"],  # timed out (symlink may exist)
        STOP_TIMER,
        STOP_SERVICE,
        DISABLE_SERVICE,  # only the existing unit, before the file is deleted
        RELOAD,
    ]
    assert calls[6][1:] == (True, False)  # service file present, timer file never written
    assert DISABLE_TIMER not in [c for c, *_ in calls]

    calls.clear()
    ok, msg = ScheduleService(_cfg(tmp_path, paused=True, mode="on_login")).sync_from_config()
    assert (ok, msg) == (True, "Kein geplanter Task vorhanden.")
    assert [c for c, *_ in calls] == [STOP_TIMER, STOP_SERVICE]


def test_linux_on_login_remove_with_only_service_file_is_ok(tmp_path, linux, monkeypatch):
    """Installed on_login (service file only): remove() stops both by name, disables only
    the service and reports success although the timer cannot be stopped/disabled."""
    calls: list[tuple[list[str], bool, bool]] = []
    monkeypatch.setattr(ns, "run", _systemd_like_run(calls, linux))
    ok, msg = ScheduleService(_cfg(tmp_path, paused=False, mode="on_login")).sync_from_config()
    assert (ok, msg) == (True, "Automatischer Lauf aktiviert (im angemeldeten Benutzerkonto).")
    assert linux[0].exists() and not linux[1].exists()
    assert "WantedBy=default.target" in linux[0].read_text(encoding="utf-8")

    calls.clear()
    ok, msg = ns.remove()
    assert (ok, msg) == (True, "Automatischer Lauf deaktiviert.")
    assert [c for c, *_ in calls] == [STOP_TIMER, STOP_SERVICE, DISABLE_SERVICE, RELOAD]
    assert calls[2][1] is True  # disabled while the service file still existed
    assert not any(file.exists() for file in linux)


def test_linux_loaded_timer_without_files_remove_stops_both_by_name(tmp_path, linux, monkeypatch):
    """Timer still loaded but its files are already gone: stop both units by name, no disable."""
    calls: list[tuple[list[str], bool, bool]] = []
    fake = _systemd_like_run(calls, linux)
    fake.loaded.update({f"{ns.UNIT}.timer", f"{ns.UNIT}.service"})
    monkeypatch.setattr(ns, "run", fake)
    assert not any(file.exists() for file in linux)
    assert ns.remove() == (True, "Kein geplanter Task vorhanden.")
    assert [c for c, *_ in calls] == [STOP_TIMER, STOP_SERVICE]
    assert fake.loaded == set()


def test_linux_timer_mode_remove_disables_both_existing_units(tmp_path, linux, monkeypatch):
    calls: list[tuple[list[str], bool, bool]] = []
    fake = _systemd_like_run(calls, linux)
    monkeypatch.setattr(ns, "run", fake)
    ok, _ = ScheduleService(_cfg(tmp_path, paused=False)).sync_from_config()
    assert ok is True
    assert all(file.exists() for file in linux)
    calls.clear()
    assert ns.remove() == (True, "Automatischer Lauf deaktiviert.")
    assert [c for c, *_ in calls] == [STOP_TIMER, STOP_SERVICE, CLEAN_TIMER, DISABLE_TIMER, DISABLE_SERVICE, RELOAD]
    assert calls[2][1:] == (True, True)  # clean while both unit files (and the loaded timer) still exist
    assert fake.loaded == set()
    assert not any(file.exists() for file in linux)


def test_linux_remove_reports_failure_when_existing_unit_cannot_be_disabled(tmp_path, linux, monkeypatch):
    linux[0].parent.mkdir(parents=True)
    linux[0].write_text("[Unit]\n", encoding="utf-8")

    def fake_run(command):
        if command[2] == "disable":
            raise RuntimeError("Failed to connect to bus")

    monkeypatch.setattr(ns, "run", fake_run)
    ok, msg = ns.remove()
    assert ok is False and "Failed to connect to bus" in msg


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
