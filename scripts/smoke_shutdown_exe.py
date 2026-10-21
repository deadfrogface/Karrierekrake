"""Packaged EXE: close via WM_CLOSE must terminate Karrierekrake.exe."""

from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXE = ROOT / "dist" / "Karrierekrake" / "Karrierekrake.exe"
WM_CLOSE = 0x0010
TIMEOUT_S = 90.0
EXIT_TIMEOUT_S = 20.0


def _process_tree_pids(root_pid: int) -> list[int]:
    """Onefile bootloader keeps a parent; GUI runs in a child process."""
    pids = [root_pid]
    try:
        out = subprocess.check_output(
            ["wmic", "process", "where", f"ParentProcessId={root_pid}", "get", "ProcessId"],
            text=True,
            errors="ignore",
        )
        for line in out.splitlines():
            line = line.strip()
            if line.isdigit():
                pids.append(int(line))
    except Exception:
        pass
    try:
        out = subprocess.check_output(
            ["tasklist", "/FI", "IMAGENAME eq Karrierekrake.exe", "/FO", "CSV", "/NH"],
            text=True,
            errors="ignore",
        )
        for line in out.splitlines():
            parts = [p.strip().strip('"') for p in line.split(",")]
            if len(parts) >= 2 and parts[1].isdigit():
                pids.append(int(parts[1]))
    except Exception:
        pass
    return list(dict.fromkeys(pids))


def _find_main_hwnd(pid: int) -> int:
    user32 = ctypes.windll.user32
    targets = set(_process_tree_pids(pid))
    titled: list[int] = []
    any_visible: list[int] = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def enum_proc(hwnd, _lparam):
        proc_id = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(proc_id))
        if proc_id.value in targets and user32.IsWindowVisible(hwnd):
            any_visible.append(int(hwnd))
            length = user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                titled.append(int(hwnd))
        return True

    user32.EnumWindows(enum_proc, 0)
    if titled:
        return titled[0]
    return any_visible[0] if any_visible else 0


def _karrierekrake_still_running() -> bool:
    listing = subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq Karrierekrake.exe"],
        capture_output=True,
    ).stdout or b""
    return b"Karrierekrake.exe" in listing


def main() -> int:
    if sys.platform != "win32":
        print("SKIP: Windows only")
        return 0
    if not EXE.exists():
        print(f"SKIP: {EXE} missing — build first")
        return 0

    subprocess.run(
        ["taskkill", "/F", "/IM", "Karrierekrake.exe"],
        capture_output=True,
        text=True,
    )
    time.sleep(0.5)

    # Isolated AppData so tray-minimize from a previous user setting cannot hide us.
    with tempfile.TemporaryDirectory(prefix="jhs_shutdown_", ignore_cleanup_errors=True) as tmp:
        env = os.environ.copy()
        env["LOCALAPPDATA"] = tmp
        # Pre-seed completed first-run so the wizard does not steal WM_CLOSE.
        appdata = Path(tmp) / "Karrierekrake"
        (appdata / "config").mkdir(parents=True, exist_ok=True)
        (appdata / "meta.json").write_text(
            '{"first_run_completed": true, "shutdown_fix_v1": true}\n',
            encoding="utf-8",
        )
        (appdata / "config" / "settings.yaml").write_text(
            "minimize_to_tray: false\nmode: search_only\ndry_run: true\n",
            encoding="utf-8",
        )
        proc = subprocess.Popen([str(EXE)], env=env, cwd=str(EXE.parent))
        print(f"Started pid={proc.pid} LOCALAPPDATA={tmp}")
        deadline = time.time() + TIMEOUT_S
        hwnd = 0
        while time.time() < deadline:
            hwnd = _find_main_hwnd(proc.pid)
            if hwnd:
                break
            if proc.poll() is not None and not _karrierekrake_still_running():
                print("FAIL: process exited before window appeared", proc.returncode)
                return 1
            time.sleep(0.25)
        if not hwnd:
            print("FAIL: main window not found")
            subprocess.run(["taskkill", "/F", "/IM", "Karrierekrake.exe"], capture_output=True)
            return 1

        print(f"Sending WM_CLOSE to hwnd={hwnd}")
        ctypes.windll.user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)

        end = time.time() + EXIT_TIMEOUT_S
        while time.time() < end:
            if not _karrierekrake_still_running():
                elapsed = EXIT_TIMEOUT_S - (end - time.time())
                print(f"OK: process exited after {elapsed:.1f}s")
                try:
                    EXE.rename(EXE.with_suffix(".exe.rename_test"))
                    EXE.with_suffix(".exe.rename_test").rename(EXE)
                    print("OK: EXE is not locked")
                except OSError as exc:
                    print(f"FAIL: EXE still locked: {exc}")
                    return 1
                return 0
            time.sleep(0.2)

        print("FAIL: process still running after timeout")
        print("hwnd still?", _find_main_hwnd(proc.pid))
        subprocess.run(["taskkill", "/F", "/IM", "Karrierekrake.exe"], capture_output=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
