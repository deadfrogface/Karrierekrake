#!/usr/bin/env python3
"""Local BRouter vs GraphHopper bakeoff harness (Agent-VM measurements).

Does NOT call public demo APIs. Process-group peak RSS via /proc.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import resource
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def proc_tree_rss_kb(pid: int) -> int:
    """Sum RSS of pid + descendants from /proc (kB)."""
    try:
        children = Path(f"/proc/{pid}/task")
        pids = {pid}
        # BFS via /proc/*/status PPid
        for p in Path("/proc").iterdir():
            if not p.name.isdigit():
                continue
            try:
                st = (p / "status").read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            ppid = None
            for line in st.splitlines():
                if line.startswith("PPid:"):
                    ppid = int(line.split()[1])
                    break
            if ppid in pids:
                pids.add(int(p.name))
        # iterate until fixed point
        changed = True
        while changed:
            changed = False
            for p in Path("/proc").iterdir():
                if not p.name.isdigit():
                    continue
                ip = int(p.name)
                if ip in pids:
                    continue
                try:
                    st = (p / "status").read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue
                for line in st.splitlines():
                    if line.startswith("PPid:"):
                        if int(line.split()[1]) in pids:
                            pids.add(ip)
                            changed = True
                        break
        total = 0
        for ip in pids:
            try:
                st = Path(f"/proc/{ip}/status").read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for line in st.splitlines():
                if line.startswith("VmRSS:"):
                    total += int(line.split()[1])
                    break
        return total
    except Exception:
        return 0


def http_get(url: str, timeout: float = 120.0) -> tuple[int, bytes]:
    req = urllib.request.Request(url, headers={"User-Agent": "Karrierekrake-Bakeoff/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read() if e.fp else b""
    except Exception as e:
        return 0, str(e).encode()


def brouter_route(base: str, lat1, lon1, lat2, lon2, profile: str = "car-fast") -> dict:
    # BRouter lonlats = lon,lat|lon,lat
    lonlats = f"{lon1},{lat1}|{lon2},{lat2}"
    q = urllib.parse.urlencode(
        {
            "lonlats": lonlats,
            "profile": profile,
            "alternativeidx": "0",
            "format": "geojson",
        }
    )
    url = f"{base.rstrip('/')}/brouter?{q}"
    t0 = time.perf_counter()
    code, body = http_get(url, timeout=180)
    elapsed = time.perf_counter() - t0
    out = {"ok": False, "http": code, "elapsed_s": round(elapsed, 3), "engine": "brouter", "url_path": "/brouter"}
    if code != 200:
        out["error"] = body[:500].decode("utf-8", errors="replace")
        return out
    try:
        gj = json.loads(body)
    except json.JSONDecodeError:
        out["error"] = "invalid_json"
        out["raw"] = body[:300].decode("utf-8", errors="replace")
        return out
    props = {}
    if gj.get("features"):
        props = gj["features"][0].get("properties") or {}
    # track-length in meters often in properties
    dist_m = None
    for key in ("track-length", "distance", "TrackLength"):
        if key in props:
            try:
                dist_m = float(props[key])
                break
            except (TypeError, ValueError):
                pass
    if dist_m is None and "messages" in props:
        # sometimes messages contain distance
        pass
    out.update(
        {
            "ok": dist_m is not None and dist_m > 0,
            "distance_km": round(dist_m / 1000.0, 3) if dist_m else None,
            "props_keys": sorted(list(props.keys()))[:20],
            "props_sample": {k: props.get(k) for k in list(props)[:12]},
        }
    )
    return out


def graphhopper_route(base: str, lat1, lon1, lat2, lon2, profile: str = "car") -> dict:
    # point=lat,lon
    q = urllib.parse.urlencode(
        [
            ("point", f"{lat1},{lon1}"),
            ("point", f"{lat2},{lon2}"),
            ("profile", profile),
            ("locale", "de"),
            ("calc_points", "false"),
            ("instructions", "false"),
        ]
    )
    url = f"{base.rstrip('/')}/route?{q}"
    t0 = time.perf_counter()
    code, body = http_get(url, timeout=180)
    elapsed = time.perf_counter() - t0
    out = {"ok": False, "http": code, "elapsed_s": round(elapsed, 3), "engine": "graphhopper"}
    if code != 200:
        out["error"] = body[:500].decode("utf-8", errors="replace")
        return out
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        out["error"] = "invalid_json"
        return out
    paths = data.get("paths") or []
    if not paths:
        out["error"] = "no_paths"
        return out
    dist_m = float(paths[0].get("distance") or 0)
    out.update({"ok": dist_m > 0, "distance_km": round(dist_m / 1000.0, 3), "time_ms": paths[0].get("time")})
    return out


def run_engine(name: str, route_fn, base: str, pairs: list, server_pid: int | None) -> dict:
    peak_kb = proc_tree_rss_kb(server_pid) if server_pid else 0
    results = []
    t_all = time.perf_counter()
    for p in pairs:
        lat1, lon1 = p["from_ll"]
        lat2, lon2 = p["to_ll"]
        air = haversine_km(lat1, lon1, lat2, lon2)
        row = route_fn(base, lat1, lon1, lat2, lon2)
        if server_pid:
            peak_kb = max(peak_kb, proc_tree_rss_kb(server_pid))
        road = row.get("distance_km")
        detour = None
        obvious_detour = False
        if road and air > 0.2:
            detour = round(road / air, 3)
            # heuristic: >2.5x airline on short city, >1.8x on long — flag for review
            if air < 15 and detour > 2.8:
                obvious_detour = True
            elif air >= 15 and detour > 1.85:
                obvious_detour = True
        results.append(
            {
                "id": p["id"],
                "cat": p["cat"],
                "from": p["from"],
                "to": p["to"],
                "airline_km": round(air, 3),
                "road_km": road,
                "detour_ratio": detour,
                "obvious_detour_flag": obvious_detour,
                "ok": bool(row.get("ok")),
                "elapsed_s": row.get("elapsed_s"),
                "http": row.get("http"),
                "error": row.get("error"),
            }
        )
        print(name, p["id"], "ok", row.get("ok"), "km", road, "s", row.get("elapsed_s"), flush=True)
    wall = time.perf_counter() - t_all
    ok_n = sum(1 for r in results if r["ok"])
    return {
        "engine": name,
        "n": len(results),
        "ok": ok_n,
        "missing": len(results) - ok_n,
        "wall_s": round(wall, 3),
        "mean_route_s": round(sum(r["elapsed_s"] or 0 for r in results) / max(1, len(results)), 3),
        "peak_rss_mb_process_group": round(peak_kb / 1024.0, 1),
        "server_pid": server_pid,
        "hardware_note": "Agent-VM — not i3 Job Object",
        "results": results,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs", required=True)
    ap.add_argument("--engine", choices=["brouter", "graphhopper"], required=True)
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--server-pid", type=int, default=0)
    ap.add_argument("--out", required=True)
    ap.add_argument("--cold-start-s", type=float, default=None)
    args = ap.parse_args()
    pairs = json.loads(Path(args.pairs).read_text(encoding="utf-8"))["pairs"]
    fn = brouter_route if args.engine == "brouter" else graphhopper_route
    report = run_engine(args.engine, fn, args.base_url, pairs, args.server_pid or None)
    if args.cold_start_s is not None:
        report["cold_start_s"] = args.cold_start_s
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("WROTE", args.out, "ok", report["ok"], "/", report["n"], flush=True)
    return 0 if report["ok"] == report["n"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
