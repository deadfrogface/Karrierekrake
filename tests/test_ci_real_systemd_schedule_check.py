"""Offline tests for scripts/ci_real_systemd_schedule_check.py (no real systemd).

``subprocess.run`` is replaced by a small in-memory model of ``systemctl --user``
(stop/disable/enable/is-enabled/daemon-reload/list-*), working on unit files and
``*.wants`` symlinks under ``tmp_path``. No real process is started.
"""

from __future__ import annotations

import fnmatch
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

from desktop.services import native_schedule as ns

_SPEC = importlib.util.spec_from_file_location(
    "ci_real_systemd_schedule_check",
    Path(__file__).resolve().parents[1] / "scripts" / "ci_real_systemd_schedule_check.py",
)
check = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(check)

# The model creates POSIX symlinks for systemd *.wants (not reliable on Windows
# runners); the real check itself runs only in the linux-real-systemd CI job.
pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="models POSIX symlinks of systemd *.wants")


class FakeUserSystemd:
    """Minimal ``systemctl --user`` model: real-systemd-like failures for unloaded/missing units."""

    def __init__(self, unit_dir: Path, *, disable_removes_symlinks: bool = True) -> None:
        self.unit_dir = unit_dir
        self.active: set[str] = set()
        self.calls: list[list[str]] = []
        self.disable_removes_symlinks = disable_removes_symlinks

    def _wants(self, unit: str) -> list[Path]:
        file = self.unit_dir / unit
        targets = [line.split("=", 1)[1].strip() for line in file.read_text().splitlines() if line.startswith("WantedBy=")]
        return [self.unit_dir / f"{t}.wants" / unit for t in targets]

    def __call__(self, command, *args, **kwargs):
        command = list(command)
        assert command[:2] == ["systemctl", "--user"], f"unexpected real process: {command}"
        self.calls.append(command)
        flags = {c for c in command[2:] if c.startswith("--")}
        verb, *rest = [c for c in command[2:] if not c.startswith("--")]
        rc, out = 0, ""
        if verb == "daemon-reload":
            pass
        elif verb == "stop":
            for unit in rest:
                if unit not in self.active:
                    rc, out = 5, f"Failed to stop {unit}: Unit {unit} not loaded.\n"
                self.active.discard(unit)
        elif verb in ("enable", "disable"):
            for unit in rest:
                if not (self.unit_dir / unit).exists():
                    return subprocess.CompletedProcess(command, 1, "", f"Failed to {verb} unit: Unit file {unit} does not exist.\n")
                for link in self._wants(unit):
                    if verb == "enable":
                        link.parent.mkdir(parents=True, exist_ok=True)
                        link.unlink(missing_ok=True)
                        link.symlink_to(self.unit_dir / unit)
                    elif self.disable_removes_symlinks:
                        link.unlink(missing_ok=True)
                if verb == "enable" and "--now" in flags:
                    self.active.add(unit)
        elif verb == "is-enabled":
            unit = rest[0]
            enabled = (self.unit_dir / unit).exists() and any(link.is_symlink() for link in self._wants(unit))
            rc, out = (0, "enabled\n") if enabled else (1, "disabled\n")
        elif verb == "list-unit-files":
            names = sorted(p.name for p in self.unit_dir.glob("*") if p.is_file() and fnmatch.fnmatch(p.name, rest[0]))
            out = "".join(f"{n} enabled enabled\n" for n in names)
        elif verb == "list-units":
            out = "".join(f"{u} loaded active waiting\n" for u in sorted(self.active) if fnmatch.fnmatch(u, rest[0]))
        else:
            raise AssertionError(f"unmodelled systemctl verb: {command}")
        return subprocess.CompletedProcess(command, rc, out, "")


@pytest.fixture
def fake_systemd(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("KK_REAL_SYSTEMD_CHECK", "1")
    fake = FakeUserSystemd(home / ".config" / "systemd" / "user")

    def refuse(*a, **k):
        raise AssertionError(f"real process started: {a!r}")

    monkeypatch.setattr(subprocess, "run", fake)
    monkeypatch.setattr(subprocess, "Popen", refuse)
    return fake


def test_refuses_outside_ci(monkeypatch, capsys):
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.delenv("KK_REAL_SYSTEMD_CHECK", raising=False)

    def refuse(*a, **k):
        raise AssertionError("must not run anything")

    monkeypatch.setattr(subprocess, "run", refuse)
    assert check.main([]) == 2
    assert "refusing" in capsys.readouterr().out


def test_refuses_with_foreign_xdg_config_home(fake_systemd, tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "elsewhere"))
    assert check.main([]) == 2
    assert fake_systemd.calls == []


def test_passes_and_leaves_nothing_with_fixed_native_schedule(fake_systemd, capsys):
    assert check.main([]) == 0
    out = capsys.readouterr().out
    assert "RESULT: PASS" in out
    assert "install: ok=True" in out and "remove(): ok=True" in out
    assert not list(fake_systemd.unit_dir.rglob("karrierekrake*"))
    assert fake_systemd.active == set()
    # the job never ran the app: only /bin/true was scheduled, and nothing was started for on_login
    commands = fake_systemd.calls
    assert ["systemctl", "--user", "enable", f"{ns.UNIT}.service"] in commands
    assert ["systemctl", "--user", "enable", "--now", f"{ns.UNIT}.timer"] in commands
    assert ["systemctl", "--user", "disable", f"{ns.UNIT}.timer", f"{ns.UNIT}.service"] not in commands
    # on_login never disables the absent timer
    first_timer_install = commands.index(["systemctl", "--user", "enable", "--now", f"{ns.UNIT}.timer"])
    assert ["systemctl", "--user", "disable", f"{ns.UNIT}.timer"] not in commands[:first_timer_install]


def test_service_unit_uses_noop_exec_start(fake_systemd, tmp_path):
    svc = check._service_class()(check._config(tmp_path, "on_login", paused=False))
    assert svc.sync_from_config()[0] is True
    text = ns.paths()[0].read_text(encoding="utf-8")
    assert 'ExecStart="/bin/true"' in text
    assert "app.main" not in text and "--once" not in text


def test_fails_when_a_wants_symlink_remains(tmp_path, fake_systemd, capsys):
    fake_systemd.disable_removes_symlinks = False
    assert check.main([]) == 1
    out = capsys.readouterr().out
    assert "RESULT: FAIL" in out
    assert "default.target.wants" in out


def test_fails_when_old_disable_now_call_breaks_remove(fake_systemd, monkeypatch, capsys):
    """Old native_schedule behaviour (one 'disable --now timer service') must be caught."""

    def old_unload_style_remove():
        files = ns.paths()
        if not any(f.exists() for f in files):
            return True, "Kein geplanter Task vorhanden."
        try:
            ns.run(["systemctl", "--user", "disable", "--now", f"{ns.UNIT}.timer", f"{ns.UNIT}.service"])
        except RuntimeError as exc:
            return False, f"Zeitplaner: {exc}"
        for f in files:
            f.unlink(missing_ok=True)
        return True, "Automatischer Lauf deaktiviert."

    monkeypatch.setattr(ns, "remove", old_unload_style_remove)
    assert check.main([]) == 1
    assert "on_login: remove() returned ok=False" in capsys.readouterr().out


def test_refuses_when_karrierekrake_units_pre_exist(fake_systemd, capsys):
    fake_systemd.unit_dir.mkdir(parents=True)
    (fake_systemd.unit_dir / f"{ns.UNIT}.service").write_text("[Unit]\n", encoding="utf-8")
    assert check.main([]) == 1
    assert "PRE-EXISTING" in capsys.readouterr().out
    assert all(c[2:4] != ["enable"] for c in fake_systemd.calls)
