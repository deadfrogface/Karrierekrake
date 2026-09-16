#!/usr/bin/env python3
"""Live blind cover/interview quality (Phi + repair) — frozen fixtures only."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "benchmark" / "scripts"))

from run_model_tournament import score_cover, score_interview  # noqa: E402
from run_guenther_grounding_repair_eval import _svc  # noqa: E402

FIX = ROOT / "benchmark" / "corpus" / "guenther_final_hardening_fixtures.json"
OUT = ROOT / "benchmark" / "guenther_final_hardening_raw" / "blind_quality_live.json"


def _hard_fail_flags(body: str, case: dict, rep_ok: bool, errors: list) -> dict:
    codes = {e.get("code") for e in errors if isinstance(e, dict)}
    b = (body or "").lower()
    prof = (case.get("profile") or "").lower()
    return {
        "false_credential": "UNSUPPORTED_CREDENTIAL" in codes and rep_ok,
        "wrong_company": "WRONG_COMPANY" in codes and rep_ok,
        "wrong_role": "WRONG_TARGET_ROLE" in codes and rep_ok,
        "role_reversal": "ROLE_REVERSAL" in codes and rep_ok,
        "accepted_with_blocking": rep_ok and any(
            c in codes
            for c in (
                "UNSUPPORTED_CREDENTIAL",
                "UNSUPPORTED_MATERIAL_CLAIM",
                "WRONG_COMPANY",
                "WRONG_TARGET_ROLE",
                "ROLE_REVERSAL",
            )
        ),
        "pflege_invented": "pflegeausbildung" in b and "pflegeausbildung" not in prof,
        "placeholder": any(x in b for x in ("[name]", "[firma]", " nan", " null")),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="phi4-mini")
    ap.add_argument("--limit-cover", type=int, default=0)
    ap.add_argument("--limit-interview", type=int, default=0)
    args = ap.parse_args()

    fx = json.loads(FIX.read_text(encoding="utf-8"))
    covers = list(fx["blind_cover_quality"])
    interviews = list(fx["blind_interview_quality"])
    if args.limit_cover:
        covers = covers[: args.limit_cover]
    if args.limit_interview:
        interviews = interviews[: args.limit_interview]

    svc = _svc(architecture="phi_all", model=args.model, enable_repair=True)
    t0 = time.perf_counter()
    latencies: list[float] = []

    cover_rows = []
    cover_scores: list[float] = []
    for i, c in enumerate(covers, 1):
        print(f"[blind cover] {i}/{len(covers)} {c['id']}", flush=True)
        ts = time.perf_counter()
        env = svc.suggest_writing(
            profile_text=c["profile"],
            job_text=c["job"],
            seed_body="Sehr geehrte Damen und Herren,",
            target_company=c.get("target_company"),
            forbid_role_reversal=bool(c.get("forbid_role_reversal")),
            forbid_wrong_role=list(c.get("forbid_wrong_role") or []),
        )
        latencies.append(time.perf_counter() - ts)
        body = env.suggestion.get("body") or ""
        subj = env.suggestion.get("subject") or ""
        rep_ok = bool(env.ok)
        errors = env.validator_errors or []
        sc, notes = score_cover(c, body, subj)
        hf = _hard_fail_flags(body, c, rep_ok, errors)
        if hf["accepted_with_blocking"] or hf["false_credential"] or hf["pflege_invented"]:
            sc = 0.0
            notes.append("hard_fail")
        cover_scores.append(sc)
        cover_rows.append(
            {
                "id": c["id"],
                "score": sc,
                "notes": notes,
                "final_ok": rep_ok,
                "repair_count": (env.repair_history or {}).get("repair_count"),
                "hard_flags": hf,
                "body_len": len(body),
            }
        )

    iv_rows = []
    iv_scores: list[float] = []
    empty_tps = 0
    empty_q = 0
    for i, c in enumerate(interviews, 1):
        print(f"[blind interview] {i}/{len(interviews)} {c['id']}", flush=True)
        ts = time.perf_counter()
        env = svc.suggest_interview_prep(profile_text=c["profile"], job_text=c["job"])
        latencies.append(time.perf_counter() - ts)
        sug = env.suggestion or {}
        rep_ok = bool(env.ok)
        tps = sug.get("talking_points") or []
        qs = sug.get("questions") or sug.get("likely_questions") or []
        if not tps:
            empty_tps += 1
        if not qs:
            empty_q += 1
        sc, notes = score_interview(sug)
        errors = env.validator_errors or []
        if rep_ok and any(
            e.get("code") in ("UNSUPPORTED_CREDENTIAL", "UNSUPPORTED_CLAIM") for e in errors
        ):
            sc = 0.0
            notes.append("unsupported_accepted")
        iv_scores.append(sc)
        iv_rows.append(
            {
                "id": c["id"],
                "score": sc,
                "notes": notes,
                "final_ok": rep_ok,
                "talking_points_n": len(tps),
                "questions_n": len(qs),
                "repair_count": (env.repair_history or {}).get("repair_count"),
            }
        )

    elapsed = time.perf_counter() - t0
    lat_sorted = sorted(latencies) if latencies else [0.0]
    p95_i = max(0, int(len(lat_sorted) * 0.95) - 1)
    payload = {
        "model": args.model,
        "elapsed_s": round(elapsed, 2),
        "latency": {
            "avg_s": round(sum(latencies) / max(1, len(latencies)), 3),
            "median_s": round(lat_sorted[len(lat_sorted) // 2], 3),
            "p95_s": round(lat_sorted[p95_i], 3),
        },
        "blind_cover": {
            "n": len(cover_rows),
            "avg_score": round(sum(cover_scores) / max(1, len(cover_scores)), 3),
            "hard_fail_accepted": sum(1 for r in cover_rows if r["hard_flags"].get("accepted_with_blocking")),
            "rows": cover_rows,
        },
        "blind_interview": {
            "n": len(iv_rows),
            "avg_score": round(sum(iv_scores) / max(1, len(iv_scores)), 3),
            "empty_tps": empty_tps,
            "empty_questions": empty_q,
            "rows": iv_rows,
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"wrote": str(OUT), "cover_avg": payload["blind_cover"]["avg_score"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
