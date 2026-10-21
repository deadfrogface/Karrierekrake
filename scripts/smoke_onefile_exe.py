"""Packaged onefile EXE smoke: launch, wait for window, WM_CLOSE, ensure exit."""

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
# Onefile cold extract can take a long time on first run.
WINDOW_TIMEOUT_S = 90.0
EXIT_TIMEOUT_S = 20.0


def _process_tree_pids(root_pid: int) -> list[int]:
    """Onefile bootloader keeps a parent; GUI runs in a child with the same image name."""
    pids = [root_pid]
    try:
        import subprocess as _sp

        out = _sp.check_output(
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
    # Fallback: all Karrierekrake.exe PIDs
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


def _terminate_tree(root_pid: int) -> None:
    for pid in reversed(_process_tree_pids(root_pid)):
        subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)


def main() -> int:
    if sys.platform != "win32":
        print("SKIP: Windows only")
        return 0
    if not EXE.exists():
        print(f"FAIL: {EXE} missing")
        return 1

    subprocess.run(["taskkill", "/F", "/IM", "Karrierekrake.exe"], capture_output=True)
    time.sleep(0.5)

    with tempfile.TemporaryDirectory(prefix="jhs_smoke_", ignore_cleanup_errors=True) as tmp:
        env = os.environ.copy()
        env["LOCALAPPDATA"] = tmp
        appdata = Path(tmp) / "Karrierekrake"
        (appdata / "config").mkdir(parents=True, exist_ok=True)
        (appdata / "meta.json").write_text(
            '{"first_run_completed": true, "shutdown_fix_v1": true}\n',
            encoding="utf-8",
        )
        (appdata / "config" / "settings.yaml").write_text(
            "minimize_to_tray: false\nmode: search_only\ndry_run: true\ntheme: system\nlanguage: de\n",
            encoding="utf-8",
        )
        (appdata / "config" / "application_profile.yaml").write_text(
            "first_name: ''\nlast_name: ''\ncountry: DE\nanswers: {}\nfield_origins: {}\n",
            encoding="utf-8",
        )
        (appdata / "config" / "profile.yaml").write_text(
            "location:\n  home_address: ''\n  max_distance_km: 20\n  country: DE\n",
            encoding="utf-8",
        )

        t0 = time.perf_counter()
        proc = subprocess.Popen([str(EXE)], env=env, cwd=str(EXE.parent))
        print(f"Started pid={proc.pid}")
        hwnd = 0
        while time.perf_counter() - t0 < WINDOW_TIMEOUT_S:
            hwnd = _find_main_hwnd(proc.pid)
            if hwnd:
                break
            if proc.poll() is not None:
                print("FAIL: process exited before window", proc.returncode)
                return 1
            time.sleep(0.4)
        if not hwnd:
            _terminate_tree(proc.pid)
            print("FAIL: main window not found")
            return 1
        startup_s = time.perf_counter() - t0
        print(f"WINDOW_OK startup_s={startup_s:.2f}")

        # Working set: prefer largest Karrierekrake process (child GUI)
        ram_mb = 0.0
        for pid in _process_tree_pids(proc.pid):
            try:
                out = subprocess.check_output(
                    ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                    text=True,
                    errors="ignore",
                )
                # "name","pid","session","session#","mem"
                parts = [p.strip().strip('"') for p in out.split(",")]
                if len(parts) >= 5:
                    mem = parts[4].replace(".", "").replace(",", "").replace(" K", "").replace("k", "")
                    # German tasklist uses "156.815 K" style
                    digits = "".join(ch for ch in parts[4] if ch.isdigit())
                    if digits:
                        ram_mb = max(ram_mb, int(digits) / 1024.0)
            except Exception:
                pass
        print(f"RAM_MB={ram_mb:.1f}")

        ctypes.windll.user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
        t_close = time.perf_counter()
        deadline = time.perf_counter() + EXIT_TIMEOUT_S
        while time.perf_counter() < deadline:
            listing = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq Karrierekrake.exe"],
                capture_output=True,
            ).stdout or b""
            if b"Karrierekrake.exe" not in listing:
                break
            time.sleep(0.25)
        else:
            _terminate_tree(proc.pid)
            print("FAIL: did not exit after WM_CLOSE")
            return 1
        shutdown_s = time.perf_counter() - t_close
        try:
            proc.wait(timeout=2)
        except Exception:
            pass
        leftover = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq Karrierekrake.exe"],
            capture_output=True,
        ).stdout or b""
        if b"Karrierekrake.exe" in leftover:
            print("WARN: leftover process")
            _terminate_tree(proc.pid)
            return 1
        print(f"EXIT_OK shutdown_s={shutdown_s:.2f}")
        print("SMOKE_OK")
        print(f"EXE_SIZE_MB={EXE.stat().st_size / (1024 * 1024):.1f}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
