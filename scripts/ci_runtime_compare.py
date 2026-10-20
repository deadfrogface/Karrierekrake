#!/usr/bin/env python3
"""T01.09.03: Desktop Platforms job/step medians before vs after the wheelcache change.

Reads the committed timings (docs/project/T01_09_03_CI_TIMINGS_2026-10-20.json,
fetched from the public Actions jobs API) and prints the medians per platform
and phase. ``--fetch RUN_ID ...`` refreshes the file from the API first.

Usage: python scripts/ci_runtime_compare.py [--fetch RUN_ID ...]
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TIMINGS = ROOT / "docs" / "project" / "T01_09_03_CI_TIMINGS_2026-10-20.json"
REPO = "deadfrogface/Karrierekrake"
# First Desktop Platforms run on 73fd965e (the wheelcache key change).
OPTIMIZED_FROM = "2026-10-17T00:05"


def _platform(job_name: str) -> str:
    if "ubuntu" in job_name:
        return "linux"
    if "macos-14" in job_name:
        return "mac-arm"
    if "intel" in job_name:
        return "mac-intel"
    return job_name


def _step_minutes(job: dict, prefix: str) -> float:
    return sum(s["minutes"] for s in job["steps"] if s["name"].startswith(prefix))


def medians(runs: list[dict]) -> dict[tuple[str, str], dict[str, float]]:
    rows: dict[tuple[str, str], list[tuple[float, float, float]]] = {}
    for run in runs:
        phase = "nach" if run["started"] >= OPTIMIZED_FROM else "vor"
        for job in run["jobs"]:
            smoke = _step_minutes(job, "Actual native binary smoke")
            rows.setdefault((_platform(job["name"]), phase), []).append(
                (job["minutes"], _step_minutes(job, "Install native dependencies"), smoke))
    return {key: {"n": len(v), "job": statistics.median(x[0] for x in v),
                  "install": statistics.median(x[1] for x in v),
                  "smoke": statistics.median(x[2] for x in v)} for key, v in rows.items()}


def _get(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=30) as response:
        return json.load(response)


def _ts(value: str) -> datetime:
    return datetime.fromisoformat(value)


def fetch(run_ids: list[str]) -> list[dict]:
    out = []
    for run_id in run_ids:
        run = _get(f"https://api.github.com/repos/{REPO}/actions/runs/{run_id}")
        jobs = _get(f"https://api.github.com/repos/{REPO}/actions/runs/{run_id}/jobs?per_page=50")["jobs"]
        out.append({"run_id": int(run_id), "head_sha": run["head_sha"], "started": run["run_started_at"], "jobs": [
            {"name": j["name"], "conclusion": j["conclusion"],
             "minutes": round((_ts(j["completed_at"]) - _ts(j["started_at"])).total_seconds() / 60, 2),
             "steps": [{"name": s["name"], "conclusion": s["conclusion"],
                        "minutes": round((_ts(s["completed_at"]) - _ts(s["started_at"])).total_seconds() / 60, 2)}
                       for s in j["steps"] if s.get("started_at") and s.get("completed_at")]}
            for j in jobs]})
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--fetch", nargs="+", metavar="RUN_ID")
    args = parser.parse_args(argv)
    if args.fetch:
        TIMINGS.write_text(json.dumps(fetch(args.fetch), indent=1) + "\n", encoding="utf-8")
    runs = json.loads(TIMINGS.read_text(encoding="utf-8"))
    for (platform, phase), m in sorted(medians(runs).items(), key=lambda kv: (kv[0][0], kv[0][1] != "vor")):
        print(f"{platform:9} {phase:4} n={m['n']} job={m['job']:.1f} install={m['install']:.1f} smoke={m['smoke']:.1f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
