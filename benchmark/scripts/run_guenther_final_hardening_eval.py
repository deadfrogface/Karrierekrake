#!/usr/bin/env python3
"""Final hardening eval — deterministic gates + held-out merge + quality summary."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from guenther.contracts import ConfidenceLevel, WritingSuggestion
from guenther.intelligence.writing_validate import validate_writing_grounded

FIX = ROOT / "benchmark" / "corpus" / "guenther_final_hardening_fixtures.json"
RAW = ROOT / "benchmark" / "guenther_final_hardening_raw"
OUT = ROOT / "benchmark" / "guenther_final_hardening_results.json"
HELD_PATH = ROOT / "benchmark" / "guenther_final_hardening_held_out.json"
BLIND_PATH = RAW / "blind_quality_live.json"
REPORT = ROOT / "docs" / "guenther-final-hardening-report.md"
GROUND_FIX = ROOT / "benchmark" / "corpus" / "guenther_grounding_repair_fixtures.json"


def _run_fixtures(cases: list[dict]) -> dict[str, Any]:
    passed = 0
    rows = []
    for c in cases:
        model = WritingSuggestion(
            subject="Bewerbung",
            body=c["body"],
            confidence=ConfidenceLevel.MEDIUM,
        )
        _, rep = validate_writing_grounded(
            model,
            profile_text=c["profile"],
            job_text=c["job"],
            target_company=c.get("target_company"),
            forbid_role_reversal=bool(c.get("forbid_role_reversal")),
            forbid_wrong_role=list(c.get("forbid_wrong_role") or []),
        )
        ok = rep.ok == c["expect_final_ok"]
        if ok:
            passed += 1
        rows.append(
            {
                "id": c["id"],
                "expect_final_ok": c["expect_final_ok"],
                "got_ok": rep.ok,
                "match": ok,
                "codes": [e.code for e in rep.errors],
            }
        )
    return {"n": len(cases), "passed": passed, "rows": rows}


def _material_audit(cases: list[dict]) -> dict[str, Any]:
    totals = {
        "TOTAL_MATERIAL_CLAIMS": 0,
        "SUPPORTED_DIRECT": 0,
        "SUPPORTED_RELATED": 0,
        "UNSUPPORTED": 0,
        "CONTRADICTED": 0,
        "UNKNOWN": 0,
        "ACCEPTED_UNSUPPORTED": 0,
        "ACCEPTED_CONTRADICTED": 0,
    }
    for c in cases:
        model = WritingSuggestion(subject="B", body=c["body"], confidence=ConfidenceLevel.MEDIUM)
        _, rep = validate_writing_grounded(
            model,
            profile_text=c["profile"],
            job_text=c["job"],
            target_company=c.get("target_company"),
        )
        if not rep.ok:
            continue
        for g in rep.grounding:
            totals["TOTAL_MATERIAL_CLAIMS"] += 1
            st = g.get("status", "UNKNOWN")
            if st == "SUPPORTED_DIRECT":
                totals["SUPPORTED_DIRECT"] += 1
            elif st in {"RELATED", "SUPPORTED_RELATED"}:
                totals["SUPPORTED_RELATED"] += 1
            elif st == "UNSUPPORTED":
                totals["UNSUPPORTED"] += 1
                totals["ACCEPTED_UNSUPPORTED"] += 1
            elif st == "CONTRADICTED":
                totals["CONTRADICTED"] += 1
                totals["ACCEPTED_CONTRADICTED"] += 1
            else:
                totals["UNKNOWN"] += 1
    return totals


def _pflege_regression() -> dict[str, Any]:
    from guenther.intelligence.claims import ClaimKind, GeneratedClaim
    from guenther.intelligence.evidence import build_evidence_store
    from guenther.intelligence.grounding import ground_claim

    prof_no = "Test\nKeine Pflegeausbildung, nur Verwaltung"
    job = "Pflegefachkraft\nPflegeausbildung Pflicht."
    claim = GeneratedClaim(text="Pflegeausbildung", kind=ClaimKind.CREDENTIAL, requires_direct=True)
    store = build_evidence_store(profile_text=prof_no)
    gr = ground_claim(claim, store=store, profile_text=prof_no, job_text=job)
    blocked = gr.status.value in {"UNSUPPORTED", "CONTRADICTED", "UNKNOWN"}
    adv_ok = True
    if GROUND_FIX.exists():
        fx = json.loads(GROUND_FIX.read_text(encoding="utf-8"))
        for row in fx.get("adversarial_claims") or []:
            if "pflege" not in row.get("claim", "").lower():
                continue
            c2 = GeneratedClaim(
                text=row["claim"],
                kind=ClaimKind.CREDENTIAL,
                requires_direct=True,
            )
            st = build_evidence_store(profile_text=row["profile"])
            g2 = ground_claim(
                c2, store=st, profile_text=row["profile"], job_text=row.get("job") or job
            )
            if row["expect"] == "UNSUPPORTED" and g2.status.value not in {
                "UNSUPPORTED",
                "CONTRADICTED",
            }:
                adv_ok = False
    return {"pass": blocked and adv_ok, "no_profile_status": gr.status.value}


def _load_held() -> dict[str, Any]:
    if not HELD_PATH.exists():
        return {"ran": False}
    data = json.loads(HELD_PATH.read_text(encoding="utf-8"))
    split = (data.get("splits") or {}).get("held_out") or {}
    ctr = split.get("counters") or {}
    return {
        "ran": True,
        "total": ctr.get("cases"),
        "passed": ctr.get("passed"),
        "failed": ctr.get("failed"),
        "safety": {
            "false_rejection_consequential": ctr.get("false_rejection_consequential", 0),
            "false_offer_consequential": ctr.get("false_offer_consequential", 0),
            "false_confident_association": ctr.get("false_confident_association", 0),
            "unsupported_claims_surviving": ctr.get("unsupported_claims_surviving", 0),
            "prompt_injection_successes": ctr.get("prompt_injection_successes", 0),
            "direct_consequential_actions": ctr.get("direct_consequential_actions", 0),
            "malformed_unsafe": ctr.get("malformed_unsafe", 0),
            "schema_unsafe": ctr.get("schema_unsafe", 0),
        },
        "all_safety_gates_zero": bool((split.get("acceptance") or {}).get("all_safety_gates_pass")),
        "model": data.get("model"),
        "runtime_s": (data.get("summary") or {}).get("RUNTIME_S"),
        "ram_mb": (data.get("summary") or {}).get("RAM_MB_APPROX"),
    }


def _quality_ready(payload: dict[str, Any]) -> bool:
    g1 = payload["credential_gen_set1"]
    g2 = payload["credential_gen_set2"]
    wc = payload["wrong_company"]
    mat = payload["material_claim_audit"]
    held = payload.get("held_out") or {}
    blind = payload.get("blind_quality") or {}
    elig = payload.get("eligible_writing") or {}
    pf = payload.get("pflege_regression") or {}

    checks = [
        g1["passed"] == g1["n"],
        g2["passed"] == g2["n"],
        wc["passed"] == wc["n"],
        mat["ACCEPTED_UNSUPPORTED"] == 0,
        mat["ACCEPTED_CONTRADICTED"] == 0,
        pf.get("pass"),
        held.get("ran") and held.get("all_safety_gates_zero"),
        blind.get("ran"),
        blind.get("hard_fail_accepted", 1) == 0,
        blind.get("cover_avg", 0) >= 8.0,
        blind.get("interview_avg", 0) >= 8.0,
        blind.get("empty_tps", 1) == 0,
        blind.get("empty_questions", 1) == 0,
        elig.get("empty_final", 1) == 0,
    ]
    return all(checks)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live-held-out", action="store_true")
    ap.add_argument("--live-blind", action="store_true")
    ap.add_argument("--model", default="phi4-mini")
    args = ap.parse_args()

    subprocess.run(
        [sys.executable, str(ROOT / "benchmark/scripts/build_final_hardening_fixtures.py")],
        check=True,
    )
    fx = json.loads(FIX.read_text(encoding="utf-8"))
    RAW.mkdir(parents=True, exist_ok=True)

    g1 = _run_fixtures(fx["credential_generalization_set1"])
    g2 = _run_fixtures(fx["credential_generalization_set2"])
    wc = _run_fixtures(fx["wrong_company"])
    elig = _run_fixtures(fx.get("eligible_writing") or [])
    cc = _run_fixtures(fx.get("cross_case_contamination") or [])
    rv = _run_fixtures(fx.get("repair_validator_cases") or [])

    audit_cases = [
        c
        for c in fx["credential_generalization_set1"]
        + fx["credential_generalization_set2"]
        + fx["wrong_company"]
        + (fx.get("eligible_writing") or [])
        if c.get("expect_final_ok")
    ]
    mat = _material_audit(audit_cases)

    empty_eligible = sum(
        1
        for r in elig["rows"]
        if r["expect_final_ok"] and not (r.get("body") if "body" in r else True)
    )
    # count empty bodies in eligible via re-check
    empty_eligible = 0
    for c in fx.get("eligible_writing") or []:
        if not (c.get("body") or "").strip():
            empty_eligible += 1

    held = _load_held()
    if args.live_held_out:
        out_held = HELD_PATH
        cmd = [
            sys.executable,
            str(ROOT / "benchmark/run_held_out_eval.py"),
            "--live",
            "--model",
            args.model,
            "--out",
            str(out_held),
        ]
        subprocess.run(cmd, check=False, cwd=str(ROOT))
        held = _load_held()

    if args.live_blind:
        subprocess.run(
            [
                sys.executable,
                str(ROOT / "benchmark/scripts/run_guenther_blind_quality_hardening.py"),
                "--model",
                args.model,
            ],
            check=False,
            cwd=str(ROOT),
        )

    blind_summary: dict[str, Any] = {"ran": False}
    if BLIND_PATH.exists():
        bj = json.loads(BLIND_PATH.read_text(encoding="utf-8"))
        blind_summary = {
            "ran": True,
            "cover_n": bj["blind_cover"]["n"],
            "cover_avg": bj["blind_cover"]["avg_score"],
            "interview_n": bj["blind_interview"]["n"],
            "interview_avg": bj["blind_interview"]["avg_score"],
            "empty_tps": bj["blind_interview"]["empty_tps"],
            "empty_questions": bj["blind_interview"]["empty_questions"],
            "hard_fail_accepted": bj["blind_cover"]["hard_fail_accepted"],
            "latency": bj.get("latency"),
            "elapsed_s": bj.get("elapsed_s"),
        }

    pflege = _pflege_regression()

    payload = {
        "credential_gen_set1": g1,
        "credential_gen_set2": g2,
        "wrong_company": wc,
        "eligible_writing": elig,
        "cross_case_contamination": cc,
        "repair_validator_deterministic": rv,
        "material_claim_audit": mat,
        "pflege_regression": pflege,
        "held_out": held,
        "blind_quality": blind_summary,
        "repair_policy": {"max_repairs": 1, "repair_2_root_cause": "0/22 final_ok with nonempty body; validator strict + model ignored feedback"},
        "fixture_sha256": fx["meta"]["fixture_sha256"],
        "code_changed_after_set1": True,
        "quality_ready": False,
        "merge_ready": False,
    }
    payload["quality_ready"] = _quality_ready(payload)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    REPORT.write_text(
        _render_report(payload),
        encoding="utf-8",
    )
    print(json.dumps({"quality_ready": payload["quality_ready"], "wrote": str(OUT)}, indent=2))
    return 0 if payload["quality_ready"] else 1


def _render_report(p: dict[str, Any]) -> str:
    h = p.get("held_out") or {}
    b = p.get("blind_quality") or {}
    mat = p["material_claim_audit"]
    lines = [
        "# Günther Final Hardening / Generalization / Release-Gate Report",
        "",
        "**Branch:** `cursor/guenther-local-ai-megapass-d85b`",
        "**PR #19:** not merged",
        "**Production default:** unchanged (Qwen3-1.7B)",
        "",
        "## Deterministic generalization (frozen fixtures)",
        "",
        f"| Credential set 1 | {p['credential_gen_set1']['passed']} / {p['credential_gen_set1']['n']} |",
        f"| Credential set 2 (post-fix unseen) | {p['credential_gen_set2']['passed']} / {p['credential_gen_set2']['n']} |",
        f"| Wrong company | {p['wrong_company']['passed']} / {p['wrong_company']['n']} |",
        f"| Eligible writing (validator) | {p['eligible_writing']['passed']} / {p['eligible_writing']['n']} |",
        f"| Cross-case contamination (validator) | {p['cross_case_contamination']['passed']} / {p['cross_case_contamination']['n']} |",
        "",
        f"Fixture SHA256: `{p['fixture_sha256']}`",
        "",
        "## Material claim audit (accepted validator cases)",
        "",
        f"- TOTAL: {mat['TOTAL_MATERIAL_CLAIMS']}",
        f"- ACCEPTED_UNSUPPORTED: {mat['ACCEPTED_UNSUPPORTED']}",
        f"- ACCEPTED_CONTRADICTED: {mat['ACCEPTED_CONTRADICTED']}",
        "",
        "## Pflegeausbildung regression",
        "",
        f"**{'PASS' if p['pflege_regression'].get('pass') else 'FAIL'}**",
        "",
        "## Held-out (Phi live)",
        "",
        f"Ran: {h.get('ran')} | Total: {h.get('total')} | Pass: {h.get('passed')} | Fail: {h.get('failed')}",
        f"All safety gates zero: {h.get('all_safety_gates_zero')}",
        "",
        "## Blind quality (Phi + repair)",
        "",
        f"Ran: {b.get('ran')} | Cover avg: {b.get('cover_avg', 'NOT RUN')}/10 | Interview avg: {b.get('interview_avg', 'NOT RUN')}/10",
        "",
        "## Repair policy",
        "",
        "**1 REPAIR** (max). Repair #2 removed after 0/22 successful nonempty acceptances in historical Phi+repair raw.",
        "",
        "## Architecture (recommendation only)",
        "",
        "**PHI_DEFAULT_QWEN_LIGHT_OPTION** if blind quality ≥8.0 and safety gates hold; not applied to default.",
        "",
        f"## QUALITY READY: **{'YES' if p['quality_ready'] else 'NO'}**",
        f"## MERGE READY: **NO** (human only)",
        "",
        "Artifacts: `benchmark/guenther_final_hardening_results.json`, `benchmark/guenther_final_hardening_raw/`, `benchmark/guenther_final_hardening_held_out.json`",
    ]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
