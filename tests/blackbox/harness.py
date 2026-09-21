"""Packaged EXE launcher + pywinauto UIA attach (NEXT-06).

Final acceptance MUST NOT import Karrierekrake modules.
"""

from __future__ import annotations

import os
import platform
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tests.blackbox.evidence import capture_screenshot, dump_uia_tree, on_failure
from tests.blackbox.visible import VisibleExpectation, assert_visible


def is_windows() -> bool:
    return platform.system() == "Windows"


def exe_path_from_env() -> Path | None:
    raw = os.environ.get("KARRIEREKRAKE_ACCEPTANCE_EXE", "").strip()
    if not raw:
        return None
    p = Path(raw)
    return p if p.is_file() else None


def run_live_requested() -> bool:
    return os.environ.get("KARRIEREKRAKE_RUN_BLACKBOX", "").strip().lower() in {
        "1",
        "true",
        "yes",
    } or os.environ.get("KARRIEREKRAKE_RUN_LIVE", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


@dataclass
class BlackboxEnvStatus:
    os_name: str
    is_windows: bool
    run_live: bool
    exe_path: str
    exe_exists: bool
    pywinauto_available: bool
    blockers: list[str] = field(default_factory=list)

    @property
    def can_run(self) -> bool:
        return (
            self.is_windows
            and self.run_live
            and self.exe_exists
            and self.pywinauto_available
            and not self.blockers
        )


def assess_environment() -> BlackboxEnvStatus:
    exe = exe_path_from_env()
    try:
        import pywinauto  # noqa: F401

        pwa = True
    except Exception:
        pwa = False
    blockers: list[str] = []
    if not is_windows():
        blockers.append(f"Host OS is {platform.system()} — black-box requires Windows")
    if not run_live_requested():
        blockers.append("KARRIEREKRAKE_RUN_BLACKBOX (or RUN_LIVE) not set")
    if exe is None:
        blockers.append("KARRIEREKRAKE_ACCEPTANCE_EXE missing or not a file")
    if not pwa:
        blockers.append("pywinauto not installed")
    return BlackboxEnvStatus(
        os_name=platform.system(),
        is_windows=is_windows(),
        run_live=run_live_requested(),
        exe_path=str(exe) if exe else "",
        exe_exists=bool(exe),
        pywinauto_available=pwa,
        blockers=blockers,
    )


@dataclass
class ExeSession:
    """Attached packaged EXE session (UIA)."""

    app: Any = None
    proc: subprocess.Popen | None = None
    status: BlackboxEnvStatus | None = None
    checkpoints: list[str] = field(default_factory=list)
    failures: list[dict[str, str]] = field(default_factory=list)

    def checkpoint(self, step: str) -> None:
        self.checkpoints.append(step)
        capture_screenshot(self.app, step)

    def visible_text(self) -> str:
        if self.app is None:
            return ""
        try:
            win = self.app.top_window()
            texts: list[str] = [win.window_text()]
            for ctrl in win.descendants():
                try:
                    t = ctrl.window_text()
                    if t:
                        texts.append(t)
                except Exception:
                    continue
            return "\n".join(texts)
        except Exception:
            return ""

    def assert_visible(self, expectation: VisibleExpectation) -> None:
        def _fail(msg: str) -> None:
            self.failures.append(on_failure(self.app, expectation.label, msg))

        assert_visible(self.visible_text(), expectation, on_fail=_fail)

    def click_by_title(self, title: str, *, timeout: float = 10.0) -> None:
        if self.app is None:
            raise RuntimeError("no app")
        from pywinauto.timings import wait_until_passes

        def _click() -> None:
            win = self.app.top_window()
            win.child_window(title=title, control_type="Button").click_input()

        wait_until_passes(timeout, 0.4, _click)

    def click_by_automation_id(self, auto_id: str, *, timeout: float = 10.0) -> None:
        if self.app is None:
            raise RuntimeError("no app")
        from pywinauto.timings import wait_until_passes

        def _click() -> None:
            win = self.app.top_window()
            win.child_window(auto_id=auto_id).click_input()

        wait_until_passes(timeout, 0.4, _click)

    def close(self, *, kill: bool = False) -> None:
        try:
            if self.app is not None and not kill:
                self.app.kill()
            elif self.proc is not None:
                self.proc.terminate()
                try:
                    self.proc.wait(timeout=5)
                except Exception:
                    self.proc.kill()
        except Exception:
            if self.proc is not None:
                try:
                    self.proc.kill()
                except Exception:
                    pass


def launch_exe(*, fresh_profile: bool = True) -> ExeSession:
    """Start packaged EXE and attach via UIA backend."""
    status = assess_environment()
    session = ExeSession(status=status)
    if not status.can_run:
        return session

    from pywinauto import Application

    env = os.environ.copy()
    if fresh_profile:
        # Isolated AppData for acceptance — never touch developer profile.
        iso = Path(os.environ.get("TEMP", ".")) / f"kk_blackbox_{int(time.time())}"
        iso.mkdir(parents=True, exist_ok=True)
        env["LOCALAPPDATA"] = str(iso)
        env["KARRIEREKRAKE_BLACKBOX"] = "1"
    # Safety: never allow real ATS submit during acceptance unless explicitly opened.
    env.setdefault("KARRIEREKRAKE_FORCE_DRY_RUN", "1")

    exe = status.exe_path
    proc = subprocess.Popen([exe], env=env, cwd=str(Path(exe).parent))
    session.proc = proc
    time.sleep(2.5)
    app = Application(backend="uia").connect(process=proc.pid, timeout=60)
    session.app = app
    session.checkpoint("launch")
    return session
