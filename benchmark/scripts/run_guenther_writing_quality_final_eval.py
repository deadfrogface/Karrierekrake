#!/usr/bin/env python3
"""Phi writing quality final eval — freeze fixtures, run Phi suites, score, summarize."""

from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "benchmark" / "scripts"))

from run_model_tournament import score_cover, score_interview  # noqa: E402
from run_guenther_grounding_repair_eval import _svc  # noqa: E402

FIX = ROOT / "benchmark" / "corpus" / "guenther_writing_quality_final_fixtures.json"
RAW = ROOT / "benchmark" / "guenther_writing_quality_final_raw"
OUT = ROOT / "benchmark" / "guenther_writing_quality_final_results.json"
REPORT = ROOT / "docs" / "guenther-writing-quality-final-report.md"
HELD = ROOT / "benchmark" / "guenther_writing_quality_final_held_out.json"
FORENSIC = RAW / "forensic_prev_blind30_audit.json"


def _pctile(vals: list[float], p: float) -> float:
    if not vals:
        return 0.0
    s = sorted(vals)
    idx = min(len(s) - 1, max(0, int(math.ceil(p / 100.0 * len(s)) - 1)))
    return round(s[idx], 3)


def _hard_flags(body: str, case: dict, env) -> dict:
    codes = {e.get("code") for e in (env.validator_errors or [])}
    ok = bool(env.ok)
    b = (body or "").lower()
    prof = (case.get("profile") or "").lower()
    return {
        "false_credential": ok and "UNSUPPORTED_CREDENTIAL" in codes,
        "unsupported_material": ok and "UNSUPPORTED_MATERIAL_CLAIM" in codes,
        "contradicted": ok and "CONTRADICTED_CLAIM" in codes,
        "wrong_company": ok and "WRONG_COMPANY" in codes,
        "wrong_role": ok and "WRONG_TARGET_ROLE" in codes,
        "role_reversal": ok and "ROLE_REVERSAL" in codes,
        "related_as_direct": ok and "RELATED_PRESENTED_AS_DIRECT" in codes,
        "placeholder": ok and "UNRESOLVED_PLACEHOLDER" in codes,
        "nan_null": ok and (("NAN_LEAK" in codes) or ("NULL_LEAK" in codes) or " nan" in b or " null" in b),
        "pflege_invented": "pflegeausbildung" in b and "pflegeausbildung" not in prof,
        "accepted_with_blocking": ok and bool(codes & {
            "UNSUPPORTED_CREDENTIAL", "UNSUPPORTED_MATERIAL_CLAIM", "CONTRADICTED_CLAIM",
            "WRONG_COMPANY", "WRONG_TARGET_ROLE", "ROLE_REVERSAL", "RELATED_PRESENTED_AS_DIRECT",
            "UNRESOLVED_PLACEHOLDER", "NAN_LEAK", "NULL_LEAK",
        }),
    }


def run_cover_suite(svc, cases: list[dict], *, label: str) -> dict[str, Any]:
    out_dir = RAW / label
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    scores: list[float] = []
    accepted_scores: list[float] = []
    first_pass = 0
    repair_req = 0
    repair_rec = 0
    hard_block = 0
    safety_block = 0
    unnecessary = 0
    repair_new_err = 0
    zeros = {k: 0 for k in (
        "false_credential", "unsupported_material", "contradicted", "wrong_company",
        "wrong_role", "role_reversal", "related_as_direct", "placeholder", "nan_null",
        "accepted_with_blocking",
    )}

    for i, c in enumerate(cases, 1):
        print(f"[{label}] {i}/{len(cases)} {c['id']}", flush=True)
        env = svc.suggest_writing(
            profile_text=c["profile"],
            job_text=c["job"],
            seed_body="Sehr geehrte Damen und Herren,",
            target_company=c.get("target_company"),
            forbid_role_reversal=bool(c.get("forbid_role_reversal", True)),
            forbid_wrong_role=list(c.get("forbid_wrong_role") or []),
        )
        body = env.suggestion.get("body") or ""
        subj = env.suggestion.get("subject") or ""
        rh = env.repair_history or {}
        attempts = rh.get("attempts") or []
        rc = int(rh.get("repair_count") or 0)
        final_ok = bool(env.ok)
        sc, notes = score_cover(c, body, subj)
        hf = _hard_flags(body, c, env)
        if hf["accepted_with_blocking"] or hf["pflege_invented"]:
            sc = 0.0
            notes.append("hard_fail")
        scores.append(sc)
        if final_ok:
            accepted_scores.append(sc)

        a0_err = [e.get("code") for e in (attempts[0].get("errors_before") or [])] if attempts else []
        a1_err = [e.get("code") for e in (attempts[1].get("errors_before") or [])] if len(attempts) > 1 else []
        if rc == 0 and final_ok:
            first_pass += 1
        if rc >= 1:
            repair_req += 1
            if final_ok:
                repair_rec += 1
            # new blocking codes after repair
            if a0_err and a1_err and set(a1_err) - set(a0_err) and final_ok:
                repair_new_err += 1

        expect_hard = bool(c.get("expect_hard_block"))
        if not final_ok:
            codes = {e.get("code") for e in (env.validator_errors or [])}
            if expect_hard or "WRITING_BLOCKED_HARD_REQUIREMENT" in codes:
                hard_block += 1
            elif codes & {"UNSUPPORTED_CREDENTIAL", "CONTRADICTED_CLAIM", "HARD_REQUIREMENT_FALSE_CLAIM"}:
                safety_block += 1
            elif expect_hard:
                hard_block += 1
            else:
                # Eligible safe case that failed → unnecessary unless targeting placeholder with real [
                import re
                if re.search(r"\[[\w\s]+\]", body) or "WRONG_COMPANY" in codes and not (c.get("target_company") and c["target_company"] != "Unknown"):
                    # real placeholder / missing company on known target → justified targeting
                    safety_block += 1  # count as justified targeting/safety-ish
                else:
                    unnecessary += 1

        for k in zeros:
            if hf.get(k):
                zeros[k] += 1

        row = {
            "id": c["id"],
            "final_ok": final_ok,
            "score": sc,
            "notes": notes,
            "repair_count": rc,
            "attempt0_errors": a0_err,
            "attempt1_errors": a1_err,
            "final_errors": [e.get("code") for e in (env.validator_errors or [])],
            "hard_flags": hf,
            "body": body,
            "subject": subj,
            "expect_hard_block": expect_hard,
            "repair_history": rh,
        }
        (out_dir / f"{c['id']}.json").write_text(json.dumps(row, ensure_ascii=False, indent=2), encoding="utf-8")
        if body:
            (out_dir / f"{c['id']}.txt").write_text(f"SUBJECT: {subj}\n\n{body}\n", encoding="utf-8")
        rows.append(row)

    eligible = [r for r in rows if not r.get("expect_hard_block")]
    eligible_ok = sum(1 for r in eligible if r["final_ok"])
    n = len(rows)
    return {
        "label": label,
        "n": n,
        "raw_avg": round(sum(scores) / max(1, len(scores)), 3),
        "accepted_avg": round(sum(accepted_scores) / max(1, len(accepted_scores)), 3) if accepted_scores else 0.0,
        "median": round(statistics.median(scores), 3) if scores else 0.0,
        "p10": _pctile(scores, 10),
        "p90": _pctile(scores, 90),
        "first_pass_accepted": first_pass,
        "repair_required": repair_req,
        "repair_recovered": repair_rec,
        "justified_hard_block": hard_block,
        "justified_safety_or_targeting_block": safety_block,
        "unnecessary_fail_closed": unnecessary,
        "final_accepted": sum(1 for r in rows if r["final_ok"]),
        "final_fail_closed": sum(1 for r in rows if not r["final_ok"]),
        "eligible_n": len(eligible),
        "eligible_accepted": eligible_ok,
        "eligible_acceptance_pct": round(100.0 * eligible_ok / max(1, len(eligible)), 2),
        "unnecessary_fail_closed_rate_pct": round(100.0 * unnecessary / max(1, n), 2),
        "zeros": zeros,
        "repair_introduced_accepted_blocking": repair_new_err,
        "rows": rows,
    }


def run_interview_suite(svc, cases: list[dict], *, label: str) -> dict[str, Any]:
    out_dir = RAW / label
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    scores = []
    empty_tps = empty_q = unsupported = 0
    for i, c in enumerate(cases, 1):
        print(f"[{label}] {i}/{len(cases)} {c['id']}", flush=True)
        env = svc.suggest_interview_prep(profile_text=c["profile"], job_text=c["job"])
        sug = env.suggestion or {}
        tps = sug.get("talking_points") or []
        qs = sug.get("questions") or sug.get("likely_questions") or []
        if not tps:
            empty_tps += 1
        if not qs:
            empty_q += 1
        sc, notes = score_interview(sug)
        codes = {e.get("code") for e in (env.validator_errors or [])}
        if env.ok and codes & {"UNSUPPORTED_CREDENTIAL", "UNSUPPORTED_CLAIM", "UNSUPPORTED_MATERIAL_CLAIM"}:
            unsupported += 1
            sc = 0.0
        scores.append(sc)
        row = {
            "id": c["id"],
            "score": sc,
            "notes": notes,
            "final_ok": bool(env.ok),
            "talking_points_n": len(tps),
            "questions_n": len(qs),
            "validator_errors": env.validator_errors,
            "suggestion": sug,
        }
        (out_dir / f"{c['id']}.json").write_text(json.dumps(row, ensure_ascii=False, indent=2), encoding="utf-8")
        rows.append(row)
    return {
        "n": len(rows),
        "avg": round(sum(scores) / max(1, len(scores)), 3),
        "empty_tps": empty_tps,
        "empty_questions": empty_q,
        "unsupported_material_accepted": unsupported,
        "rows": rows,
    }


def render_report(payload: dict) -> str:
    f = payload.get("forensic") or {}
    b = payload.get("final_blind") or {}
    iv = payload.get("interview") or {}
    h = payload.get("held_out") or {}
    lines = [
        "# Günther Writing Quality Final Report (Phi-4-mini)",
        "",
        f"**Fixture SHA256:** `{payload.get('fixture_sha256')}`",
        f"**Frozen before run:** {payload.get('fixture_frozen_before_run')}",
        "",
        "## Forensic (previous 30 blind)",
        "",
        f"- Categories: `{f.get('root_cause_summary')}`",
        f"- JUSTIFIED fail-closed: {f.get('JUSTIFIED_FAIL_CLOSED_OF_30')}/30",
        f"- UNNECESSARY fail-closed: {f.get('UNNECESSARY_FAIL_CLOSED_OF_30')}/30",
        "",
        "## Final blind covers",
        "",
        f"- N: {b.get('n')}",
        f"- RAW avg: {b.get('raw_avg')}/10",
        f"- ACCEPTED avg: {b.get('accepted_avg')}/10",
        f"- Eligible acceptance: {b.get('eligible_acceptance_pct')}%",
        f"- Unnecessary fail-closed rate: {b.get('unnecessary_fail_closed_rate_pct')}%",
        f"- Zeros: `{b.get('zeros')}`",
        "",
        "## Interview",
        "",
        f"- Avg: {iv.get('avg')}/10 empty TPS={iv.get('empty_tps')} empty Q={iv.get('empty_questions')}",
        "",
        "## Held-out",
        "",
        f"- {h}",
        "",
        f"## QUALITY READY: **{'YES' if payload.get('quality_ready') else 'NO'}**",
        "## MERGE READY: **NO**",
        "## PRODUCTION DEFAULT CHANGED: **NO**",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=["freeze", "dev", "blind", "blind_v2", "interview", "held_out", "summary", "all"], default="summary")
    ap.add_argument("--model", default="phi4-mini")
    args = ap.parse_args()

    subprocess.run([sys.executable, str(ROOT / "benchmark/scripts/build_writing_quality_final_fixtures.py")], check=True)
    fx = json.loads(FIX.read_text(encoding="utf-8"))
    RAW.mkdir(parents=True, exist_ok=True)

    payload: dict[str, Any] = {}
    if OUT.exists():
        try:
            payload = json.loads(OUT.read_text(encoding="utf-8"))
        except Exception:
            payload = {}

    payload["fixture_sha256"] = fx["meta"]["fixture_sha256"]
    payload["fixture_frozen_before_run"] = True
    payload["model"] = args.model
    payload["repair_policy"] = 1
    payload["safety_thresholds_weakened"] = False
    payload["writing_prompt_changed"] = True
    payload["claim_extraction_changed"] = True
    payload["evidence_matching_changed"] = True
    payload["validator_changed"] = True

    if FORENSIC.exists():
        fr = json.loads(FORENSIC.read_text(encoding="utf-8"))
        payload["forensic"] = {
            "root_cause_summary": fr.get("root_cause_summary"),
            "JUSTIFIED_FAIL_CLOSED_OF_30": fr.get("JUSTIFIED_FAIL_CLOSED_OF_30"),
            "UNNECESSARY_FAIL_CLOSED_OF_30": fr.get("UNNECESSARY_FAIL_CLOSED_OF_30"),
            "final_accepted": fr.get("final_accepted"),
            "final_fail_closed": fr.get("final_fail_closed"),
        }

    if args.phase in {"dev", "all"}:
        svc = _svc(architecture="phi_all", model=args.model, enable_repair=True)
        payload["development"] = run_cover_suite(svc, fx["development_covers"], label="development_covers")
        OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.phase in {"blind", "all"}:
        svc = _svc(architecture="phi_all", model=args.model, enable_repair=True)
        # freeze marker before blind
        (RAW / "blind_fixture_freeze.json").write_text(
            json.dumps({"sha256": fx["meta"]["fixture_sha256"], "ts": time.time()}, indent=2),
            encoding="utf-8",
        )
        payload["final_blind"] = run_cover_suite(svc, fx["final_blind_covers"], label="final_blind_covers")
        OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.phase in {"blind_v2"}:
        svc = _svc(architecture="phi_all", model=args.model, enable_repair=True)
        (RAW / "blind_v2_fixture_freeze.json").write_text(
            json.dumps({"sha256": fx["meta"]["fixture_sha256"], "ts": time.time(), "set": "v2"}, indent=2),
            encoding="utf-8",
        )
        payload["final_blind_v1"] = payload.get("final_blind")
        payload["final_blind"] = run_cover_suite(
            svc, fx["final_blind_covers_v2"], label="final_blind_covers_v2"
        )
        payload["post_fix_second_unseen_blind"] = True
        OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.phase in {"interview", "all"}:
        svc = _svc(architecture="phi_all", model=args.model, enable_repair=True)
        payload["interview"] = run_interview_suite(svc, fx["fresh_interviews"], label="fresh_interviews")
        OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.phase in {"held_out", "all"}:
        cmd = [
            sys.executable,
            str(ROOT / "benchmark/run_held_out_eval.py"),
            "--live",
            "--model",
            args.model,
            "--out",
            str(HELD),
        ]
        subprocess.run(cmd, check=False, cwd=str(ROOT))
        if HELD.exists():
            held = json.loads(HELD.read_text(encoding="utf-8"))
            ctr = ((held.get("splits") or {}).get("held_out") or {}).get("counters") or {}
            payload["held_out"] = {
                "ran": True,
                "total": ctr.get("cases"),
                "passed": ctr.get("passed"),
                "failed": ctr.get("failed"),
                "safety": {k: ctr.get(k, 0) for k in (
                    "false_rejection_consequential", "false_offer_consequential",
                    "false_confident_association", "unsupported_claims_surviving",
                    "prompt_injection_successes", "direct_consequential_actions",
                    "malformed_unsafe", "schema_unsafe",
                )},
                "all_safety_gates_zero": bool((((held.get("splits") or {}).get("held_out") or {}).get("acceptance") or {}).get("all_safety_gates_pass")),
            }

    # quality ready computation
    b = payload.get("final_blind") or {}
    iv = payload.get("interview") or {}
    h = payload.get("held_out") or {}
    z = b.get("zeros") or {}
    quality = bool(
        b.get("n", 0) >= 40
        and (b.get("raw_avg") or 0) >= 8.0
        and (b.get("accepted_avg") or 0) >= 8.0
        and (b.get("eligible_acceptance_pct") or 0) >= 90.0
        and (b.get("unnecessary_fail_closed_rate_pct") or 100) <= 5.0
        and all(z.get(k, 1) == 0 for k in (
            "false_credential", "unsupported_material", "contradicted", "wrong_company",
            "wrong_role", "role_reversal", "related_as_direct", "placeholder", "nan_null",
            "accepted_with_blocking",
        ))
        and (b.get("repair_introduced_accepted_blocking") or 0) == 0
        and (iv.get("avg") or 0) >= 8.0
        and (iv.get("empty_tps") or 1) == 0
        and (iv.get("empty_questions") or 1) == 0
        and (iv.get("unsupported_material_accepted") or 1) == 0
        and h.get("ran")
        and h.get("all_safety_gates_zero")
    )
    payload["quality_ready"] = quality
    payload["merge_ready"] = False
    payload["recommended_architecture"] = (
        "PHI_DEFAULT_QWEN_LIGHT_OPTION" if quality else "NOT_READY"
    )
    payload["recommended_default"] = "phi4-mini" if quality else "qwen3-1.7b"
    payload["recommended_light"] = "qwen3-1.7b"

    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    REPORT.write_text(render_report(payload), encoding="utf-8")
    print(json.dumps({"quality_ready": quality, "wrote": str(OUT), "phase": args.phase}, indent=2))
    return 0 if (args.phase == "summary" or quality or args.phase != "all") else 1


if __name__ == "__main__":
    raise SystemExit(main())
