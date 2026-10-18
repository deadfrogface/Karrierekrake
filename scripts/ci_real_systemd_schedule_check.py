"""CI-only: ScheduleService install + remove() against a REAL ``systemctl --user``.

Runs only on a disposable CI runner (``GITHUB_ACTIONS=true`` and
``KK_REAL_SYSTEMD_CHECK=1``); it acts on the real user manager of the runner's
HOME and touches only the Karrierekrake units (``karrierekrake-autorun.*``).

For each mode (``on_login``: service only; ``once_daily``: service + timer) it
installs the schedule via ``ScheduleService.sync_from_config()``, then removes
it via ``sync_from_config()`` with ``automation_paused=True`` (-> ``remove()``)
and asserts ``ok=True`` and that no Karrierekrake unit file, ``*.wants``
symlink, enabled or loaded unit remains. ``systemctl --user list-unit-files``
and ``list-units --all`` for ``karrierekrake*`` are printed before/after.

The app job is never run: a CI-only subclass replaces the scheduled command
with ``/bin/true`` (ExecStart is a no-op), and the unit file is checked for it
before anything else happens.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

NOOP_COMMAND = ["/bin/true"]
PATTERN = "karrierekrake*"
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


def unit_dir() -> Path:
    from desktop.services import native_schedule as ns

    return ns.paths()[0].parent


def leftovers(runner: Runner) -> list[str]:
    """Every trace of a Karrierekrake unit: files, *.wants symlinks, unit lists."""
    found: list[str] = []
    base = unit_dir()
    if base.exists():
        for path in sorted(base.rglob(PATTERN)):
            kind = "symlink" if path.is_symlink() else "file"
            found.append(f"{kind}: {path}")
    for args in (("list-unit-files", PATTERN), ("list-units", "--all", PATTERN)):
        rc, out = runner(["systemctl", "--user", "--no-pager", "--no-legend", "--plain", *args])
        lines = [line for line in out.splitlines() if line.strip().startswith("karrierekrake")]
        found += [f"{args[0]}: {line.strip()}" for line in lines]
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


def check_mode(runner: Runner, mode: str, root: Path) -> list[str]:
    from desktop.services import native_schedule as ns

    errors: list[str] = []
    service_file, timer_file = ns.paths()
    service_unit, timer_unit = f"{ns.UNIT}.service", f"{ns.UNIT}.timer"
    svc_cls = _service_class()
    print(f"===== mode={mode}")
    snapshot(runner, f"{mode}: before install")

    ok, msg = svc_cls(_config(root, mode, paused=False)).sync_from_config()
    print(f"install: ok={ok} msg={msg!r}")
    if not ok:
        errors.append(f"{mode}: install failed: {msg}")
    text = service_file.read_text(encoding="utf-8") if service_file.exists() else ""
    if 'ExecStart="/bin/true"' not in text:
        errors.append(f"{mode}: service ExecStart is not the /bin/true no-op")
    if mode == "on_login":
        wants = service_file.parent / "default.target.wants" / service_unit
        expected_unit = service_unit
        if timer_file.exists():
            errors.append(f"{mode}: unexpected timer file {timer_file}")
    else:
        wants = service_file.parent / "timers.target.wants" / timer_unit
        expected_unit = timer_unit
        if not timer_file.exists():
            errors.append(f"{mode}: timer file missing {timer_file}")
    print(f"enable symlink {wants}: exists={wants.is_symlink()}")
    if not wants.is_symlink():
        errors.append(f"{mode}: enable symlink missing: {wants}")
    rc, _ = systemctl(runner, "is-enabled", expected_unit)
    if rc != 0:
        errors.append(f"{mode}: {expected_unit} not enabled after install (rc={rc})")
    snapshot(runner, f"{mode}: after install")

    ok, msg = svc_cls(_config(root, mode, paused=True)).sync_from_config()
    print(f"remove(): ok={ok} msg={msg!r}")
    if ok is not True:
        errors.append(f"{mode}: remove() returned ok={ok!r}: {msg}")
    snapshot(runner, f"{mode}: after remove")
    rest = leftovers(runner)
    for item in rest:
        print(f"LEFTOVER {item}")
    errors += [f"{mode}: leftover {item}" for item in rest]

    ok, msg = svc_cls(_config(root, mode, paused=True)).sync_from_config()
    print(f"second remove(): ok={ok} msg={msg!r}")
    if ok is not True:
        errors.append(f"{mode}: second remove() returned ok={ok!r}: {msg}")
    return errors


def run_checks(runner: Runner, root: Path) -> int:
    pre = leftovers(runner)
    if pre:
        for item in pre:
            print(f"PRE-EXISTING {item}")
        print("::error::Karrierekrake units exist before the check; refusing to touch them")
        return 1
    errors: list[str] = []
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
