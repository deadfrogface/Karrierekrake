#!/usr/bin/env python3
"""True cold-start + 30-route BRouter remeasure (Agent-VM only).

Kills any existing RouteServer, starts Java fresh, times:
  - process spawn → port open
  - port open → first successful route
  - full 30-pair wall + per-route + process-group peak RSS
  - disk footprint of jar+segments+profiles

Never labels results as laptop evidence.
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import time
from pathlib import Path

import core.road_route_brouter as br
from scripts.run_road_distance_bakeoff import brouter_route, haversine_km, proc_tree_rss_kb, run_engine

ROOT = Path(__file__).resolve().parents[1]
PAIRS = ROOT / "artifacts" / "road_distance_bakeoff" / "PAIRS_30.json"
OUT_DIR = ROOT / "artifacts" / "road_distance_bakeoff"
RUNTIME = Path(os.environ.get("KARRIEREKRAKE_BROUTER_DIR", "/tmp/kk_brouter_runtime"))


def _kill_port(port: int) -> None:
    try:
        out = subprocess.check_output(["bash", "-lc", f"lsof -t -iTCP:{port} -sTCP:LISTEN || true"], text=True)
    except Exception:
        out = ""
    for pid in out.split():
        try:
            os.kill(int(pid), signal.SIGTERM)
        except OSError:
            pass
    time.sleep(1.0)
    try:
        out = subprocess.check_output(["bash", "-lc", f"lsof -t -iTCP:{port} -sTCP:LISTEN || true"], text=True)
    except Exception:
        out = ""
    for pid in out.split():
        try:
            os.kill(int(pid), signal.SIGKILL)
        except OSError:
            pass


def disk_bytes(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file():
        return path.stat().st_size
    total = 0
    for p in path.rglob("*"):
        if p.is_file():
            try:
                total += p.stat().st_size
            except OSError:
                pass
    return total


def main() -> int:
    os.environ["KARRIEREKRAKE_BROUTER_DIR"] = str(RUNTIME)
    br.reset_brouter_runtime_for_tests()
    _kill_port(br.DEFAULT_PORT)

    pairs = json.loads(PAIRS.read_text(encoding="utf-8"))["pairs"]
    first = pairs[0]
    lat1, lon1 = first["from_ll"]
    lat2, lon2 = first["to_ll"]

    t_install0 = time.perf_counter()
    dirs = br.ensure_brouter_install(root=RUNTIME, segment_names=br.DEFAULT_SEGMENTS)
    install_s = time.perf_counter() - t_install0

    server = br.BRouterServer(
        jar=dirs["jar"],
        segment_dir=dirs["segments"],
        profile_dir=dirs["profiles"],
        custom_profile_dir=dirs["custom_profiles"],
        java_bin=br.find_java_bin(),
    )
    t_java0 = time.perf_counter()
    server.start(wait_s=60.0)
    java_ready_s = time.perf_counter() - t_java0
    pid = server.pid
    assert pid

    t_route0 = time.perf_counter()
    first_res = br.route_driving_km(lat1, lon1, lat2, lon2, base_url=server.base_url)
    first_route_s = time.perf_counter() - t_route0
    cold_total_s = java_ready_s + first_route_s

    # Full 30 after warm first
    report = run_engine("brouter", brouter_route, server.base_url, pairs, pid)
    # Re-run with module snap path for fairness on island pairs
    snap_results = []
    peak = 0
    t_all = time.perf_counter()
    for p in pairs:
        r = br.route_driving_km(
            p["from_ll"][0],
            p["from_ll"][1],
            p["to_ll"][0],
            p["to_ll"][1],
            base_url=server.base_url,
        )
        peak = max(peak, proc_tree_rss_kb(pid))
        air = haversine_km(p["from_ll"][0], p["from_ll"][1], p["to_ll"][0], p["to_ll"][1])
        road = r.distance_km
        detour = round(road / air, 3) if road and air > 0 else None
        snap_results.append(
            {
                "id": p["id"],
                "cat": p["cat"],
                "from": p["from"],
                "to": p["to"],
                "airline_km": round(air, 3),
                "road_km": road,
                "detour_ratio": detour,
                "ok": r.ok,
                "elapsed_s": r.elapsed_s,
                "error": r.error,
                "snap_offset_m": r.snap_offset_m,
            }
        )
        print(p["id"], "ok", r.ok, "km", road, "snap_m", r.snap_offset_m, flush=True)
    wall = time.perf_counter() - t_all
    ok_n = sum(1 for x in snap_results if x["ok"])

    footprint = {
        "jar_bytes": disk_bytes(dirs["jar"]),
        "segments_bytes": disk_bytes(dirs["segments"]),
        "profiles_bytes": disk_bytes(dirs["profiles"]),
        "total_runtime_bytes": disk_bytes(dirs["root"]),
        "total_runtime_gib": round(disk_bytes(dirs["root"]) / (1024**3), 3),
    }

    out = {
        "comparison_type": "AGENT_VM_NOT_LAPTOP",
        "hardware_note": "Agent-VM — not i3 Job Object / not Windows EXE laptop proof",
        "cold_start": {
            "install_or_ensure_s": round(install_s, 3),
            "java_spawn_to_port_open_s": round(java_ready_s, 3),
            "first_route_s": round(first_route_s, 3),
            "cold_total_java_plus_first_route_s": round(cold_total_s, 3),
            "first_route_ok": first_res.ok,
            "first_route_km": first_res.distance_km,
            "note": "True cold: RouteServer process killed before measurement",
        },
        "warm_30": {
            "n": len(snap_results),
            "ok": ok_n,
            "missing": len(snap_results) - ok_n,
            "wall_s": round(wall, 3),
            "mean_route_s": round(
                sum(x["elapsed_s"] or 0 for x in snap_results) / max(1, len(snap_results)), 3
            ),
            "peak_rss_mb_process_group": round(peak / 1024.0, 1),
            "results": snap_results,
        },
        "disk": footprint,
        "bakeoff_harness_without_snap_ok": report.get("ok"),
        "production_distance_filter": "airline_prefilter_then_brouter_road_km",
        "windows_exe_status": "NOT_RUN_ON_AGENT_VM — auto-start wired in code; laptop/EXE proof pending",
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / "BROUTER_REMEASURE_30.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # Also refresh BROUTER_RESULTS.json from snap-aware run
    (OUT_DIR / "BROUTER_RESULTS.json").write_text(
        json.dumps(
            {
                "engine": "brouter",
                "n": len(snap_results),
                "ok": ok_n,
                "missing": len(snap_results) - ok_n,
                "wall_s": round(wall, 3),
                "mean_route_s": out["warm_30"]["mean_route_s"],
                "peak_rss_mb_process_group": out["warm_30"]["peak_rss_mb_process_group"],
                "server_pid": pid,
                "hardware_note": out["hardware_note"],
                "cold_start_s": out["cold_start"]["cold_total_java_plus_first_route_s"],
                "cold_start_detail": out["cold_start"],
                "results": snap_results,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print("WROTE", path, "ok", ok_n, "/", len(snap_results), flush=True)
    server.stop()
    return 0 if ok_n == len(snap_results) else 2


if __name__ == "__main__":
    raise SystemExit(main())
