#!/usr/bin/env python3
"""Ablation A–D on Phase-2 development fixture (Phi quality loop).

A = OLD pipeline baseline (reuse Phase-2 raw metrics; optional re-run with mode=old)
B = plan_draft
C = critic1
D = full (up to 2 quality revisions)

Does NOT create a new blind fixture. Does NOT weaken safety gates.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "benchmark/guenther_final_model_shootout_fixture.json"
PHASE2_RAW = (
    ROOT
    / "benchmark/guenther_final_model_shootout_raw/phase1/phi4-mini/phase2_new_fixture_covers"
)
OUT_DIR = ROOT / "benchmark/guenther_quality_loop_raw"
RESULTS = ROOT / "benchmark/guenther_quality_loop_results.json"
ABLATION = ROOT / "benchmark/guenther_quality_loop_ablation.json"


def _rss_mb() -> float:
    try:
        with open("/proc/self/status", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) / 1024.0
    except OSError:
        return 0.0
    return 0.0


def score_cover_case(case: dict, body: str, subject: str) -> tuple[float, list[str]]:
    """Use identical scorer as Phase-2 shootout for fair before/after comparison."""
    import sys

    scripts = Path(__file__).resolve().parent
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    from run_model_tournament import score_cover as _score_cover

    return _score_cover(case, body, subject)


def classify_edit(final_ok: bool, score: float, expect_hard: bool) -> str:
    if not final_ok:
        return "UNUSABLE" if expect_hard else "MATERIAL_EDIT_REQUIRED"
    if score >= 8.0:
        return "READY_AS_IS"
    if score >= 7.0:
        return "MINOR_STYLE_EDIT_OPTIONAL"
    if score >= 5.0:
        return "MATERIAL_EDIT_REQUIRED"
    return "UNUSABLE"


def load_baseline_a() -> dict:
    rows = []
    for p in sorted(PHASE2_RAW.glob("*.json")):
        rows.append(json.loads(p.read_text(encoding="utf-8")))
    return summarize(rows, mode="old", source="phase2_reuse")


def summarize(rows: list[dict], *, mode: str, source: str) -> dict:
    eligible = [r for r in rows if not r.get("expect_hard_block")]
    elig_n = len(eligible)
    ok_n = sum(1 for r in eligible if r.get("final_ok"))
    unnec = elig_n - ok_n
    ready = sum(1 for r in eligible if r.get("edit_class") == "READY_AS_IS")
    scores = [float(r.get("score") or 0) for r in rows]
    accepted = [float(r.get("score") or 0) for r in rows if r.get("final_ok")]
    lats = [float(r.get("latency_s") or 0) for r in rows]
    calls = [int(r.get("model_calls") or 0) for r in rows if r.get("model_calls") is not None]
    return {
        "mode": mode,
        "source": source,
        "n": len(rows),
        "eligible_safe_n": elig_n,
        "eligible_safe_automation_pct": round(100.0 * ok_n / max(1, elig_n), 2),
        "unnecessary_fail_closed_pct": round(100.0 * unnec / max(1, elig_n), 2),
        "ready_as_is_pct": round(100.0 * ready / max(1, elig_n), 2),
        "cover_raw_avg": round(sum(scores) / max(1, len(scores)), 3),
        "cover_accepted_avg": round(sum(accepted) / max(1, len(accepted)), 3) if accepted else 0.0,
        "safety_failures_accepted": sum(
            1
            for r in rows
            if r.get("final_ok")
            and any(
                (r.get("hard_flags") or {}).get(k)
                for k in (
                    "false_credential",
                    "unsupported_material",
                    "wrong_company",
                    "placeholder",
                )
            )
        ),
        "avg_latency_s": round(sum(lats) / max(1, len(lats)), 3) if lats else None,
        "median_latency_s": round(statistics.median(lats), 3) if lats else None,
        "p95_latency_s": round(sorted(lats)[int(0.95 * (len(lats) - 1))], 3) if lats else None,
        "avg_model_calls": round(sum(calls) / max(1, len(calls)), 3) if calls else None,
        "p50_model_calls": statistics.median(calls) if calls else None,
        "p95_model_calls": sorted(calls)[int(0.95 * (len(calls) - 1))] if calls else None,
        "peak_rss_mb": max((float(r.get("peak_rss_mb") or 0) for r in rows), default=0.0),
    }


def run_mode(mode: str, *, limit: int | None, resume: bool) -> dict:
    from guenther.service import GuentherService

    os.environ.setdefault("KARRIEREKRAKE_MODELS_DIR", "/tmp/karrierekrake-models")
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    covers = list(fixture.get("covers") or [])
    if limit:
        covers = covers[:limit]
    out = OUT_DIR / f"ablation_{mode}"
    out.mkdir(parents=True, exist_ok=True)
    svc = GuentherService(
        enabled=True,
        model="phi4-mini",
        architecture="phi_all",
        allow_heuristic_when_no_llm=False,
        quality_loop_mode=mode,
    )
    rows = []
    for i, c in enumerate(covers, 1):
        dest = out / f"{c['id']}.json"
        if resume and dest.exists():
            rows.append(json.loads(dest.read_text(encoding="utf-8")))
            print(f"[{mode}] resume {i}/{len(covers)} {c['id']}", flush=True)
            continue
        t0 = time.perf_counter()
        env = svc.suggest_writing(
            profile_text=c.get("profile") or "",
            job_text=c.get("job") or "",
            target_company=c.get("target_company"),
            forbid_role_reversal=bool(c.get("forbid_role_reversal")),
            forbid_wrong_role=list(c.get("forbid_wrong_role") or []),
            quality_loop_mode=mode,
            target_role=c.get("role"),
        )
        lat = time.perf_counter() - t0
        body = str((env.suggestion or {}).get("body") or "")
        subj = str((env.suggestion or {}).get("subject") or "")
        sc, notes = score_cover_case(c, body, subj)
        final_ok = bool(env.ok)
        expect_hard = c.get("expect_class") == "EXPECTED_HARD_BLOCK" or bool(
            c.get("expect_hard_block")
        )
        edit = classify_edit(final_ok, sc, expect_hard)
        meta = (env.repair_history or {})
        row = {
            "id": c["id"],
            "final_ok": final_ok,
            "score": sc,
            "edit_class": edit,
            "notes": notes,
            "latency_s": round(lat, 3),
            "model_calls": meta.get("model_calls"),
            "final_state": meta.get("final_state"),
            "final_errors": [e.get("code") for e in (env.validator_errors or [])],
            "expect_hard_block": expect_hard,
            "body": body,
            "subject": subj,
            "peak_rss_mb": _rss_mb(),
            "hard_flags": {},
            "quality_loop": {
                k: meta.get(k)
                for k in (
                    "mode",
                    "early_exit",
                    "plan_repair_count",
                    "safety_repair_count",
                    "quality_revision_count",
                    "transitions",
                    "timings_s",
                    "cot_stored",
                )
            },
        }
        dest.write_text(json.dumps(row, ensure_ascii=False, indent=2), encoding="utf-8")
        rows.append(row)
        print(
            f"[{mode}] {i}/{len(covers)} {c['id']} ok={final_ok} score={sc} "
            f"calls={row['model_calls']} lat={row['latency_s']}",
            flush=True,
        )
    return summarize(rows, mode=mode, source="live")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--modes", default="plan_draft,critic1,full")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--skip-live", action="store_true")
    args = ap.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    ablation = {"A_old_phase2_reuse": load_baseline_a()}
    if not args.skip_live:
        for mode in [m.strip() for m in args.modes.split(",") if m.strip()]:
            ablation[{
                "plan_draft": "B_plan_draft",
                "critic1": "C_critic1",
                "full": "D_full",
                "old": "A_old_live",
            }.get(mode, mode)] = run_mode(
                mode, limit=args.limit or None, resume=args.resume
            )

    # Revision-2 worth keeping?
    c = ablation.get("C_critic1") or {}
    d = ablation.get("D_full") or {}
    rev2_keep = False
    if c and d:
        ready_gain = (d.get("ready_as_is_pct") or 0) - (c.get("ready_as_is_pct") or 0)
        auto_gain = (d.get("eligible_safe_automation_pct") or 0) - (
            c.get("eligible_safe_automation_pct") or 0
        )
        rev2_keep = ready_gain >= 2.0 or auto_gain >= 1.0

    a = ablation["A_old_phase2_reuse"]
    best = d or c or ablation.get("B_plan_draft") or a
    dev_target = (
        (best.get("eligible_safe_automation_pct") or 0) >= 95
        and (best.get("ready_as_is_pct") or 0) >= 90
        and (best.get("cover_raw_avg") or 0) >= 8.0
        and (best.get("safety_failures_accepted") or 0) == 0
    )

    payload = {
        "purpose": "Günther quality-loop ablation on Phase-2 development fixture",
        "primary_model": "phi4-mini",
        "ablation": ablation,
        "revision_2_worth_keeping": rev2_keep,
        "development_target_reached": dev_target,
        "baseline_phase2": {
            "automation": 85.11,
            "unnecessary_fail_closed": 14.89,
            "cover_raw": 7.665,
            "ready_as_is": 76.6,
        },
    }
    ABLATION.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    RESULTS.write_text(
        json.dumps(
            {
                **payload,
                "critic_calibration": __import__(
                    "guenther.intelligence.quality_loop", fromlist=["run_calibration"]
                ).run_calibration(),
                "max_model_calls": 8,
                "max_plan_repairs": 1,
                "max_safety_repairs": 1,
                "max_quality_revisions": 2 if rev2_keep else 1,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
