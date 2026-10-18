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
        self.states: list[tuple[int, str]] = [(0, "running\n")]  # is-system-running answers (last repeats)
        self.failed: set[str] = set()
        # units the manager keeps listing: unit -> remaining list-units calls (None = forever)
        self.stale_units: dict[str, int | None] = {}

    def _wants(self, unit: str) -> list[Path]:
        file = self.unit_dir / unit
        targets = [line.split("=", 1)[1].strip() for line in file.read_text().splitlines() if line.startswith("WantedBy=")]
        return [self.unit_dir / f"{t}.wants" / unit for t in targets]

    def __call__(self, command, *args, **kwargs):
        command = list(command)
        if command[:2] == ["ls", "-la"]:
            directory = Path(command[2])
            if not directory.is_dir():
                return subprocess.CompletedProcess(command, 2, "", f"ls: cannot access '{directory}': No such file or directory\n")
            return subprocess.CompletedProcess(command, 0, "".join(f"{e}\n" for e in sorted(p.name for p in directory.iterdir())), "")
        assert command[:2] == ["systemctl", "--user"], f"unexpected real process: {command}"
        self.calls.append(command)
        flags = {c for c in command[2:] if c.startswith("--")}
        verb, *rest = [c for c in command[2:] if not c.startswith("--")]
        rc, out = 0, ""
        if verb == "daemon-reload":
            pass
        elif verb == "is-system-running":
            rc, out = self.states.pop(0) if len(self.states) > 1 else self.states[0]
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
        elif verb == "list-units" and "--failed" in flags:
            out = "".join(f"{u} loaded failed failed\n" for u in sorted(self.failed))
        elif verb == "list-units":
            units = sorted(self.active | set(self.stale_units))
            out = "".join(f"{u} loaded active waiting\n" for u in units if fnmatch.fnmatch(u, rest[0]))
            for unit, left in list(self.stale_units.items()):
                if left is not None:
                    if left <= 1:
                        del self.stale_units[unit]
                    else:
                        self.stale_units[unit] = left - 1
        elif verb == "show":
            unit = rest[-1]
            state = "active" if unit in self.active or unit in self.stale_units else "inactive"
            out = f"LoadState=loaded\nActiveState={state}\n"
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
    # virtual clock for the list-units settle window: sleep advances time, never blocks
    now = [0.0]
    fake.slept = []
    monkeypatch.setattr(check, "_clock", lambda: now[0])

    def fake_sleep(seconds):
        fake.slept.append(seconds)
        now[0] += seconds

    monkeypatch.setattr(check, "_sleep", fake_sleep)
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
    assert out.count("\ninstall: install ok=True") == 2 and out.count("re-install: install ok=True") == 2
    assert out.count("pause (sync_from_config, automation_paused=True): ok=True msg='Automatischer Lauf deaktiviert.'") == 2
    assert out.count("remove() after pause: ok=True msg='Kein geplanter Task vorhanden.'") == 2
    assert out.count("remove() on installed units: ok=True msg='Automatischer Lauf deaktiviert.'") == 2
    assert "is-system-running: state='running' rc=0" in out
    assert out.count("$ ls -la ") == 12  # 2 wants dirs x 3 removals x 2 modes
    assert "LEFTOVER" not in out
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
    assert "on_login: pause (sync_from_config, automation_paused=True) returned ok=False" in capsys.readouterr().out


def test_refuses_when_karrierekrake_units_pre_exist(fake_systemd, capsys):
    fake_systemd.unit_dir.mkdir(parents=True)
    (fake_systemd.unit_dir / f"{ns.UNIT}.service").write_text("[Unit]\n", encoding="utf-8")
    assert check.main([]) == 1
    assert "PRE-EXISTING" in capsys.readouterr().out
    assert all(c[2:4] != ["enable"] for c in fake_systemd.calls)


def _run(fake, tmp_path, timeout_s=0.0):
    return check.run_checks(check.real_runner, tmp_path / "work", sleep=lambda _s: None, timeout_s=timeout_s)


@pytest.mark.parametrize(
    "answer",
    [
        (1, "offline\n"),
        (1, "Failed to connect to bus: No such file or directory\n"),
        (1, "stopping\n"),
        (1, "starting\n"),  # still starting when the timeout is reached
        (1, "maintenance\n"),
        (1, ""),
    ],
)
def test_gate_fails_when_user_manager_not_up(fake_systemd, tmp_path, capsys, answer):
    fake_systemd.states = [answer]
    assert _run(fake_systemd, tmp_path) == 1
    out = capsys.readouterr().out
    assert "user manager not up" in out and "RESULT: FAIL" in out
    # nothing was installed or removed
    assert all(c[2] == "is-system-running" for c in fake_systemd.calls)


def test_gate_polls_starting_until_running(fake_systemd, tmp_path, capsys):
    fake_systemd.states = [(1, "Failed to connect to bus: No such file or directory\n"), (1, "starting\n"), (0, "running\n")]
    assert _run(fake_systemd, tmp_path, timeout_s=10.0) == 0
    assert "RESULT: PASS" in capsys.readouterr().out


def test_gate_accepts_degraded_with_unrelated_failed_unit(fake_systemd, tmp_path, capsys):
    fake_systemd.states = [(1, "degraded\n")]
    fake_systemd.failed = {"pipewire.service"}
    assert _run(fake_systemd, tmp_path) == 0
    out = capsys.readouterr().out
    assert "is-system-running: state='degraded' rc=1" in out
    assert "list-units --failed" in out and "pipewire.service" in out
    assert "RESULT: PASS" in out


def test_gate_fails_when_degraded_by_failed_karrierekrake_unit(fake_systemd, tmp_path, capsys):
    fake_systemd.states = [(1, "degraded\n")]
    fake_systemd.failed = {"pipewire.service", f"{ns.UNIT}.service"}
    assert _run(fake_systemd, tmp_path) == 1
    out = capsys.readouterr().out
    assert "degraded with failed Karrierekrake unit" in out and "RESULT: FAIL" in out
    assert all(c[2:4] != ["enable"] for c in fake_systemd.calls)


@pytest.mark.parametrize("wants", ["default.target.wants", "timers.target.wants"])
def test_fails_when_dangling_wants_symlink_remains_after_remove(fake_systemd, tmp_path, monkeypatch, capsys, wants):
    """A karrierekrake* entry left in a *.wants dir (even dangling) after pause/remove fails the check."""
    real_remove = ns.remove

    def remove_leaving_symlink():
        result = real_remove()
        directory = fake_systemd.unit_dir / wants
        directory.mkdir(parents=True, exist_ok=True)
        link = directory / f"{ns.UNIT}.stale"
        if not link.is_symlink():
            link.symlink_to(fake_systemd.unit_dir / "does-not-exist")
        return result

    monkeypatch.setattr(ns, "remove", remove_leaving_symlink)
    assert check.main([]) == 1
    out = capsys.readouterr().out
    assert f"leftover after pause (sync_from_config, automation_paused=True): {wants}:" in out
    assert "RESULT: FAIL" in out


def test_fails_when_list_units_still_shows_karrierekrake_after_remove(fake_systemd, monkeypatch, capsys):
    """The manager keeps listing the timer (e.g. never unloaded): list-units --all must fail the check."""

    def keep_listed(command, *a, **k):
        result = fake_systemd(command, *a, **k)
        if list(command)[2:4] == ["enable", "--now"]:
            fake_systemd.stale_units[f"{ns.UNIT}.timer"] = None
        return result

    monkeypatch.setattr(subprocess, "run", keep_listed)
    assert check.main([]) == 1
    out = capsys.readouterr().out
    assert f"list-units: {ns.UNIT}.timer (LoadState=loaded ActiveState=active)" in out
    assert f"$ systemctl --user show -p LoadState -p ActiveState {ns.UNIT}.timer" in out
    assert "still listed by list-units --all after 5 s" in out
    assert "on_login: leftover" not in out  # on_login itself was clean
    assert "RESULT: FAIL" in out


def test_fails_when_list_unit_files_still_shows_karrierekrake_after_remove(fake_systemd, monkeypatch, capsys):
    """remove() that reports ok but leaves the unit file must fail (list-unit-files + file check)."""

    def remove_without_deleting():
        return True, "Automatischer Lauf deaktiviert."

    monkeypatch.setattr(ns, "remove", remove_without_deleting)
    assert check.main([]) == 1
    out = capsys.readouterr().out
    assert f"list-unit-files: {ns.UNIT}.service" in out
    assert "RESULT: FAIL" in out
    assert fake_systemd.slept == []  # immediate failure, no settle window


def test_list_units_leftover_that_disappears_within_settle_window_passes(fake_systemd, monkeypatch, capsys):
    """Still listed for a few polls after remove() (< 5 s): tolerated, check passes."""

    def briefly_listed(command, *a, **k):
        result = fake_systemd(command, *a, **k)
        if list(command)[2:3] == ["daemon-reload"] and not any(fake_systemd.unit_dir.glob("karrierekrake*")):
            fake_systemd.stale_units[f"{ns.UNIT}.service"] = 3  # listed in the next 3 list-units calls
        return result

    monkeypatch.setattr(subprocess, "run", briefly_listed)
    assert check.main([]) == 0
    out = capsys.readouterr().out
    assert "RESULT: PASS" in out
    assert fake_systemd.slept and sum(fake_systemd.slept) < check.LIST_UNITS_SETTLE_S


def test_list_units_leftover_longer_than_settle_window_fails_with_states(fake_systemd, monkeypatch, capsys):
    def listed_forever_after_remove(command, *a, **k):
        result = fake_systemd(command, *a, **k)
        if list(command)[2:3] == ["daemon-reload"] and not any(fake_systemd.unit_dir.glob("karrierekrake*")):
            fake_systemd.stale_units[f"{ns.UNIT}.service"] = None
        return result

    monkeypatch.setattr(subprocess, "run", listed_forever_after_remove)
    assert check.main([]) == 1
    out = capsys.readouterr().out
    assert f"leftover after pause (sync_from_config, automation_paused=True): list-units: {ns.UNIT}.service (LoadState=loaded ActiveState=active)" in out
    assert f"$ systemctl --user show -p LoadState -p ActiveState {ns.UNIT}.service" in out
    assert "RESULT: FAIL" in out
    # waited the full window (virtual clock), then failed
    assert sum(fake_systemd.slept[:10]) >= check.LIST_UNITS_SETTLE_S


def test_wants_symlink_leftover_fails_immediately_without_settle_window(fake_systemd, monkeypatch, capsys):
    real_remove = ns.remove

    def remove_leaving_symlink():
        result = real_remove()
        directory = fake_systemd.unit_dir / "default.target.wants"
        directory.mkdir(parents=True, exist_ok=True)
        link = directory / f"{ns.UNIT}.service"
        if not link.is_symlink():
            link.symlink_to(fake_systemd.unit_dir / "gone")
        return result

    monkeypatch.setattr(ns, "remove", remove_leaving_symlink)
    assert check.main([]) == 1
    assert "RESULT: FAIL" in capsys.readouterr().out
    assert fake_systemd.slept == []
