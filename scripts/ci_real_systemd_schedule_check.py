"""CI-only: ScheduleService install / pause / remove() against a REAL ``systemctl --user``.

Runs only on a disposable CI runner (``GITHUB_ACTIONS=true`` and
``KK_REAL_SYSTEMD_CHECK=1``); it acts on the real user manager of the runner's
HOME and touches only the Karrierekrake units (``karrierekrake-autorun.*``).

1. Manager gate: polls ``systemctl --user is-system-running`` (output and exit
   code printed). ``running`` passes; ``degraded`` passes only if
   ``systemctl --user list-units --failed`` shows no Karrierekrake unit (the
   list is printed). ``starting``/``initializing`` are polled until the timeout;
   ``offline``, ``stopping``, ``maintenance``, no bus or anything else at the
   timeout fails the check.
2. For each mode (``on_login``: service only; ``once_daily``: service + timer):
   a) install via ``ScheduleService.sync_from_config()``;
   b) pause exactly like the app (``settings.automation_paused = True`` then
      ``ScheduleService(cfg).sync_from_config()``, see
      ``MainWindow.set_automation_paused`` / ``SettingsPage``), which ends in
      ``ScheduleService.remove_task()`` -> ``native_schedule.remove()``;
   c) ``remove()`` (``ScheduleService.remove_task()``) on the paused state;
   d) install again and e) ``remove()`` directly on the installed units.
   Return values and every ``systemctl`` exit code are printed, plus
   ``list-unit-files``/``list-units --all 'karrierekrake*'`` after each step and
   ``ls -la`` of ``default.target.wants``/``timers.target.wants`` after each
   removal. After every pause/remove the check FAILS immediately if a
   Karrierekrake unit file, a ``karrierekrake*`` entry in either ``*.wants``
   directory or a Karrierekrake unit in ``list-unit-files`` remains; a unit in
   ``list-units --all`` fails if it is still listed after 5 s of polling (its
   LoadState/ActiveState is logged).

The app job is never run: a CI-only subclass replaces the scheduled command
with ``/bin/true`` (ExecStart is a no-op), and the unit file is checked for it.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

NOOP_COMMAND = ["/bin/true"]
PATTERN = "karrierekrake*"
WANTS_DIRS = ("default.target.wants", "timers.target.wants")
ACCEPTED_STATES = ("running", "degraded")
TRANSIENT_STATES = ("starting", "initializing")
Runner = Callable[[list[str]], "tuple[int, str]"]


def real_runner(command: list[str]) -> tuple[int, str]:
    proc = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False)
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def systemctl(runner: Runner, *args: str) -> tuple[int, str]:
    command = ["systemctl", "--user", *args]
    rc, out = runner(command)
    print(f"$ {' '.join(command)}  -> rc={rc}")
    for line in out.rstrip().splitlines():
        print(f"    {line}")
    return rc, out


def snapshot(runner: Runner, label: str) -> None:
    print(f"--- {label}")
    systemctl(runner, "--no-pager", "list-unit-files", PATTERN)
    systemctl(runner, "--no-pager", "list-units", "--all", PATTERN)


def wait_for_manager(runner: Runner, timeout_s: float = 30.0, sleep: Callable[[float], None] = time.sleep) -> list[str]:
    """Gate: the user manager must be ``running`` or ``degraded`` (without failed Karrierekrake units)."""
    deadline = time.monotonic() + timeout_s
    state = ""
    while True:
        rc, out = systemctl(runner, "is-system-running")
        state = out.strip().splitlines()[-1].strip() if out.strip() else ""
        print(f"is-system-running: state={state!r} rc={rc}")
        if state in ACCEPTED_STATES:
            break
        if time.monotonic() >= deadline:
            return [f"user manager not up after {timeout_s:.0f} s: is-system-running state={state!r} rc={rc}"]
        sleep(1.0)
    if state == "degraded":
        # Some unrelated user unit failed; acceptable unless it is one of ours.
        _, failed = systemctl(runner, "--no-pager", "--no-legend", "--plain", "list-units", "--failed")
        ours = [line.strip() for line in failed.splitlines() if "karrierekrake" in line]
        if ours:
            return [f"degraded with failed Karrierekrake unit(s): {ours}"]
    return []


def unit_dir() -> Path:
    from desktop.services import native_schedule as ns

    return ns.paths()[0].parent


def show_wants_dirs(runner: Runner) -> None:
    """Extra log only; the assertion is in leftovers()."""
    for name in WANTS_DIRS:
        command = ["ls", "-la", str(unit_dir() / name)]
        rc, out = runner(command)
        print(f"$ {' '.join(command)}  -> rc={rc}")
        for line in out.rstrip().splitlines():
            print(f"    {line}")


LIST_UNITS_SETTLE_S = 5.0
_clock = time.monotonic  # patched by the offline tests
_sleep = time.sleep


def _listed_units(runner: Runner) -> list[str]:
    _, out = runner(["systemctl", "--user", "--no-pager", "--no-legend", "--plain", "list-units", "--all", PATTERN])
    return [line.split()[0] for line in out.splitlines() if "karrierekrake" in line and line.split()]


def leftovers(runner: Runner) -> list[str]:
    """Every trace of a Karrierekrake unit.

    Unit files, ``*.wants`` entries and ``list-unit-files`` fail immediately (no
    tolerance). Only ``list-units --all`` gets up to LIST_UNITS_SETTLE_S after
    the daemon-reload of remove(): the manager may still list a just-unloaded
    unit briefly. Units still listed after that fail, with LoadState/ActiveState.
    """
    found: list[str] = []
    base = unit_dir()
    if base.exists():
        for path in sorted(base.glob(PATTERN)):
            found.append(f"{'symlink' if path.is_symlink() else 'file'}: {path}")
    for name in WANTS_DIRS:
        directory = base / name
        if directory.is_dir():
            # os.listdir also sees dangling symlinks
            for entry in sorted(os.listdir(directory)):
                if entry.startswith("karrierekrake"):
                    found.append(f"{name}: {directory / entry}")
    _, out = runner(["systemctl", "--user", "--no-pager", "--no-legend", "--plain", "list-unit-files", PATTERN])
    found += [f"list-unit-files: {line.strip()}" for line in out.splitlines() if "karrierekrake" in line]
    listed = _listed_units(runner)
    if found:
        # immediate failure: no waiting when files/symlinks/unit files remain
        return found + [f"list-units: {unit}" for unit in listed]
    deadline = _clock() + LIST_UNITS_SETTLE_S
    while listed and _clock() < deadline:
        _sleep(0.5)
        listed = _listed_units(runner)
    if listed:
        print(f"still listed by list-units --all after {LIST_UNITS_SETTLE_S:.0f} s: {listed}")
    for unit in listed:
        _, state = systemctl(runner, "show", "-p", "LoadState", "-p", "ActiveState", unit)
        found.append(f"list-units: {unit} ({' '.join(state.split())})")
    return found


def _config(root: Path, mode: str, paused: bool):
    from core.config import empty_app_config

    cfg = empty_app_config(root=root / f"profile-{mode}")
    cfg.settings.run_automatically = True
    cfg.settings.automation_paused = paused
    cfg.settings.schedule_mode = mode
    cfg.settings.schedule_times = ["03:17"]
    return cfg


def _service_class():
    from desktop.services.schedule_service import ScheduleService

    class NoOpScheduleService(ScheduleService):
        """CI only: schedule /bin/true instead of the app's ``--once`` run."""

        def _python_command(self) -> list[str]:
            return list(NOOP_COMMAND)

    return NoOpScheduleService


def _install(runner: Runner, mode: str, root: Path, label: str) -> list[str]:
    from desktop.services import native_schedule as ns

    errors: list[str] = []
    service_file, timer_file = ns.paths()
    service_unit, timer_unit = f"{ns.UNIT}.service", f"{ns.UNIT}.timer"
    ok, msg = _service_class()(_config(root, mode, paused=False)).sync_from_config()
    print(f"{label}: install ok={ok} msg={msg!r}")
    if ok is not True:
        errors.append(f"{mode}: {label}: install failed: {msg}")
    text = service_file.read_text(encoding="utf-8") if service_file.exists() else ""
    if 'ExecStart="/bin/true"' not in text:
        errors.append(f"{mode}: {label}: service ExecStart is not the /bin/true no-op")
    if mode == "on_login":
        wants, expected_unit = service_file.parent / "default.target.wants" / service_unit, service_unit
        if timer_file.exists():
            errors.append(f"{mode}: {label}: unexpected timer file {timer_file}")
    else:
        wants, expected_unit = service_file.parent / "timers.target.wants" / timer_unit, timer_unit
        if not timer_file.exists():
            errors.append(f"{mode}: {label}: timer file missing {timer_file}")
    print(f"enable symlink {wants}: exists={wants.is_symlink()}")
    if not wants.is_symlink():
        errors.append(f"{mode}: {label}: enable symlink missing: {wants}")
    rc, _ = systemctl(runner, "is-enabled", expected_unit)
    if rc != 0:
        errors.append(f"{mode}: {label}: {expected_unit} not enabled after install (rc={rc})")
    snapshot(runner, f"{mode}: after {label}")
    return errors


def _removed(runner: Runner, mode: str, label: str, ok, msg) -> list[str]:
    print(f"{label}: ok={ok} msg={msg!r}")
    errors = [] if ok is True else [f"{mode}: {label} returned ok={ok!r}: {msg}"]
    snapshot(runner, f"{mode}: after {label}")
    show_wants_dirs(runner)
    rest = leftovers(runner)
    for item in rest:
        print(f"LEFTOVER after {label}: {item}")
    return errors + [f"{mode}: leftover after {label}: {item}" for item in rest]


def check_mode(runner: Runner, mode: str, root: Path) -> list[str]:
    svc_cls = _service_class()
    print(f"===== mode={mode}")
    snapshot(runner, f"{mode}: before install")
    errors = _install(runner, mode, root, "install")

    # Pause exactly like the app: automation_paused=True, then sync_from_config().
    cfg = _config(root, mode, paused=False)
    cfg.settings.automation_paused = True
    ok, msg = svc_cls(cfg).sync_from_config()
    errors += _removed(runner, mode, "pause (sync_from_config, automation_paused=True)", ok, msg)

    ok, msg = svc_cls(_config(root, mode, paused=True)).remove_task()
    errors += _removed(runner, mode, "remove() after pause", ok, msg)

    errors += _install(runner, mode, root, "re-install")
    ok, msg = svc_cls(_config(root, mode, paused=False)).remove_task()
    errors += _removed(runner, mode, "remove() on installed units", ok, msg)
    return errors


def run_checks(runner: Runner, root: Path, sleep: Callable[[float], None] = time.sleep, timeout_s: float = 30.0) -> int:
    errors = wait_for_manager(runner, timeout_s=timeout_s, sleep=sleep)
    if not errors:
        pre = leftovers(runner)
        if pre:
            for item in pre:
                print(f"PRE-EXISTING {item}")
            errors.append("Karrierekrake units exist before the check; refusing to touch them")
    if not errors:
        for mode in ("on_login", "once_daily"):
            errors += check_mode(runner, mode, root)
    for error in errors:
        print(f"::error::{error}")
    print("RESULT:", "FAIL" if errors else "PASS")
    return 1 if errors else 0


def main(argv: list[str] | None = None) -> int:
    if os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("KK_REAL_SYSTEMD_CHECK") != "1":
        print("refusing: real systemd check runs only on CI (GITHUB_ACTIONS=true, KK_REAL_SYSTEMD_CHECK=1)")
        return 2
    if sys.platform != "linux":
        print(f"refusing: Linux only (sys.platform={sys.platform})")
        return 2
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg and Path(xdg).expanduser() != Path.home() / ".config":
        # The user manager reads ~/.config/systemd/user; ns.paths() must match it.
        print(f"refusing: XDG_CONFIG_HOME={xdg!r} differs from ~/.config")
        return 2
    print(f"HOME={Path.home()} unit dir={unit_dir()}")
    with tempfile.TemporaryDirectory(prefix="kk-real-systemd-") as tmp:
        return run_checks(real_runner, Path(tmp))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
