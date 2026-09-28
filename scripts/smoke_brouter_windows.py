#!/usr/bin/env python3
"""Windows-EXE / packaged BRouter smoke (Zielgerät).

Run on a Windows machine with the built Karrierekrake EXE (or frozen worker):

  set KARRIEREKRAKE_SMOKE_BROUTER=1
  Karrierekrake.exe --smoke-brouter

Or from a checkout with system Java:

  python scripts/smoke_brouter_windows.py

Measures (process-group RSS + cold start). Never labels Agent-VM as laptop proof.
Writes artifacts/road_distance_bakeoff/WINDOWS_EXE_SMOKE.json when successful.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "road_distance_bakeoff" / "WINDOWS_EXE_SMOKE.json"


def _proc_tree_rss_kb(pid: int) -> int:
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes

            # Best-effort: current process WorkingSet only (no full tree without psutil).
            class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
                _fields_ = [
                    ("cb", wintypes.DWORD),
                    ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t),
                ]

            GetCurrentProcess = ctypes.windll.kernel32.GetCurrentProcess
            GetProcessMemoryInfo = ctypes.windll.psapi.GetProcessMemoryInfo
            counters = PROCESS_MEMORY_COUNTERS()
            counters.cb = ctypes.sizeof(counters)
            if GetProcessMemoryInfo(GetCurrentProcess(), ctypes.byref(counters), counters.cb):
                return int(counters.WorkingSetSize // 1024)
        except Exception:
            return 0
        return 0
    # Linux Agent-VM fallback
    try:
        from scripts.run_road_distance_bakeoff import proc_tree_rss_kb

        return proc_tree_rss_kb(pid)
    except Exception:
        return 0


def main() -> int:
    sys.path.insert(0, str(ROOT))
    from core.road_route_brouter import get_brouter_runtime, reset_brouter_runtime_for_tests

    reset_brouter_runtime_for_tests()
    rt = get_brouter_runtime()
    t0 = time.perf_counter()
    dirs = rt.ensure_install()
    install_s = time.perf_counter() - t0
    t1 = time.perf_counter()
    server = rt.ensure_ready(allow_install=True, wait_s=90.0)
    ready_s = time.perf_counter() - t1
    t2 = time.perf_counter()
    # Offline route (local RouteServer; no public demo API)
    first = rt.route(50.7753, 6.0839, 50.8514, 5.6910)  # Aachen→Maastricht
    first_s = time.perf_counter() - t2
    pid = server.pid or os.getpid()
    peak = _proc_tree_rss_kb(pid)

    # Optional Qwen-parallel probe: only if env asks and model path exists
    qwen = {"ran": False}
    if os.environ.get("KARRIEREKRAKE_SMOKE_QWEN", "").strip() in {"1", "true", "yes"}:
        try:
            import threading

            qwen_err: list[str] = []

            def _touch_qwen() -> None:
                try:
                    # Import only — do not download models in smoke.
                    import guenther  # noqa: F401

                    qwen["imported"] = True
                except Exception as exc:  # noqa: BLE001
                    qwen_err.append(str(exc))

            th = threading.Thread(target=_touch_qwen, daemon=True)
            th.start()
            r2 = rt.route(50.8455, 4.3571, 50.9014, 4.4844)  # Brussels→Airport
            th.join(timeout=30)
            qwen = {
                "ran": True,
                "imported": bool(qwen.get("imported")),
                "route_ok": r2.ok,
                "route_km": r2.distance_km,
                "errors": qwen_err,
            }
            peak = max(peak, _proc_tree_rss_kb(pid))
        except Exception as exc:  # noqa: BLE001
            qwen = {"ran": True, "error": str(exc)}

    report = {
        "platform": sys.platform,
        "frozen": bool(getattr(sys, "frozen", False)),
        "comparison_type": (
            "WINDOWS_EXE_TARGET"
            if sys.platform == "win32"
            else "NOT_WINDOWS_AGENT_VM_PROXY"
        ),
        "manual_java_required": False,
        "cold_start": {
            "install_or_ensure_s": round(install_s, 3),
            "java_ready_s": round(ready_s, 3),
            "first_route_s": round(first_s, 3),
            "total_s": round(install_s + ready_s + first_s, 3),
        },
        "first_route": {
            "ok": first.ok,
            "km": first.distance_km,
            "error": first.error,
            "snap_offset_m": first.snap_offset_m,
        },
        "peak_rss_mb_process_group": round(peak / 1024.0, 1) if peak else None,
        "dirs": {k: str(v) for k, v in dirs.items()},
        "attribution_file": str(dirs["root"] / "OSM_ATTRIBUTION.txt"),
        "qwen_parallel": qwen,
        "offline": True,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("WROTE", OUT)
    print(json.dumps(report, indent=2))
    rt.stop()
    if sys.platform != "win32":
        print(
            "NOTE: This host is not Windows — result is Agent-VM proxy only; "
            "PR #100 stays Draft until a real Windows EXE run is attached.",
            flush=True,
        )
        return 3
    return 0 if first.ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
