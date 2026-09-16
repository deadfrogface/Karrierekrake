#!/usr/bin/env python3
"""Forensic audit of previous blind-cover fail-closed cases (Phi, no code changes)."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "benchmark" / "scripts"))

from run_guenther_grounding_repair_eval import _svc  # noqa: E402

FIX = ROOT / "benchmark" / "corpus" / "guenther_final_hardening_fixtures.json"
OUT_DIR = ROOT / "benchmark" / "guenther_writing_quality_final_raw" / "forensic_prev_blind30"
OUT_JSON = ROOT / "benchmark" / "guenther_writing_quality_final_raw" / "forensic_prev_blind30_audit.json"


def _classify(case: dict, env, attempt0_errors: list, attempt1_errors: list, final_ok: bool) -> str:
    """Primary category A–J for fail-closed (or ACCEPTED if ok)."""
    if final_ok:
        return "ACCEPTED"
    codes = {e.get("code") for e in (env.validator_errors or [])}
    body = (env.suggestion or {}).get("body") or ""
    prof = (case.get("profile") or "").lower()
    job = (case.get("job") or "").lower()

    # H — hard requirement
    if "WRITING_BLOCKED_HARD_REQUIREMENT" in codes or (
        "HARD_REQUIREMENT_NOT_MET" in codes and not body.strip()
    ):
        return "H"
    # I — structural
    if "SCHEMA_INVALID" in codes or "EMPTY_OUTPUT" in codes and not body.strip():
        if not body.strip():
            return "I"
    # B — targeting
    if codes & {"WRONG_COMPANY", "WRONG_TARGET_ROLE", "ROLE_REVERSAL", "UNRESOLVED_PLACEHOLDER", "NAN_LEAK", "NULL_LEAK"}:
        return "B"
    # A — true safety invent
    if codes & {"UNSUPPORTED_CREDENTIAL", "CONTRADICTED_CLAIM", "UNSUPPORTED_MATERIAL_CLAIM", "HARD_REQUIREMENT_FALSE_CLAIM"}:
        # Check if claim text looks invented vs overstrict
        for e in env.validator_errors or []:
            ct = (e.get("claim_text") or "").lower()
            if e.get("code") == "UNSUPPORTED_CREDENTIAL" and ct:
                # if credential tokens appear strongly in body but not profile → A
                if any(x in ct for x in ("ausbildung", "zertifikat", "examen", "studium", "bachelor", "master", "ihk", "lizenz")):
                    if ct.split()[0] not in prof and ct not in prof:
                        return "A"
        # Could be C/D/E — inspect claim vs profile loosely
        for e in env.validator_errors or []:
            ct = (e.get("claim_text") or "").lower()
            if e.get("code") in {"UNSUPPORTED_CREDENTIAL", "UNSUPPORTED_CLAIM", "UNSUPPORTED_MATERIAL_CLAIM"}:
                # substring of profile → E false negative
                toks = [t for t in ct.replace(",", " ").split() if len(t) >= 5]
                if toks and all(t in prof for t in toks[:2]):
                    return "E"
                # soft experience phrasing → D
                soft = ("erfahrung", "kenntnisse", "interessiere", "einarbeiten", "grundlage")
                if any(s in (body.lower()) for s in soft) and not any(
                    x in ct for x in ("zertifikat", "ausbildung abgeschlossen", "examen")
                ):
                    return "D"
        return "A"
    if "JOB_REQUIREMENT_USED_AS_EVIDENCE" in codes:
        return "A"
    if "RELATED_PRESENTED_AS_DIRECT" in codes:
        return "A"
    # F — repair failure: attempt0 had fewer/different fixable errors
    if attempt0_errors and attempt1_errors:
        c0 = {e.get("code") for e in attempt0_errors}
        c1 = {e.get("code") for e in attempt1_errors}
        if c0 & {"UNSUPPORTED_CREDENTIAL", "WRONG_COMPANY"} and c1:
            return "F"
    # G — quality only (shouldn't block)
    if not codes or codes <= {"HARD_REQUIREMENT_NOT_MET"}:
        return "G"
    return "J"


def main() -> int:
    fx = json.loads(FIX.read_text(encoding="utf-8"))
    cases = list(fx["blind_cover_quality"])
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    svc = _svc(architecture="phi_all", model="phi4-mini", enable_repair=True)
    rows = []
    t0 = time.perf_counter()

    for i, c in enumerate(cases, 1):
        print(f"[forensic] {i}/{len(cases)} {c['id']}", flush=True)
        env = svc.suggest_writing(
            profile_text=c["profile"],
            job_text=c["job"],
            seed_body="Sehr geehrte Damen und Herren,",
            target_company=c.get("target_company"),
            forbid_role_reversal=True,
            forbid_wrong_role=[],
        )
        rh = env.repair_history or {}
        attempts = rh.get("attempts") or []
        a0 = attempts[0] if attempts else {}
        a1 = attempts[1] if len(attempts) > 1 else {}
        body = (env.suggestion or {}).get("body") or ""
        subj = (env.suggestion or {}).get("subject") or ""
        final_ok = bool(env.ok)
        cat = _classify(c, env, a0.get("errors_before") or [], a1.get("errors_before") or [], final_ok)

        row = {
            "id": c["id"],
            "target_role": c["job"].split("\n")[0],
            "target_company": c.get("target_company"),
            "profile": c["profile"],
            "job": c["job"],
            "final_ok": final_ok,
            "repair_count": rh.get("repair_count"),
            "exhausted": rh.get("exhausted"),
            "category": cat,
            "final_blocking_errors": [e.get("code") for e in (env.validator_errors or [])],
            "attempt0_errors": [e.get("code") for e in (a0.get("errors_before") or [])],
            "attempt0_claims": [
                {"code": e.get("code"), "claim": e.get("claim_text")}
                for e in (a0.get("errors_before") or [])
            ],
            "attempt1_errors": [e.get("code") for e in (a1.get("errors_before") or [])],
            "attempt1_claims": [
                {"code": e.get("code"), "claim": e.get("claim_text")}
                for e in (a1.get("errors_before") or [])
            ],
            "attempt0_body": (a0.get("output_snapshot") or {}).get("body"),
            "attempt1_body": (a1.get("output_snapshot") or {}).get("body") if a1 else None,
            "final_body": body,
            "final_subject": subj,
            "body_len": len(body),
            "grounding_report": env.grounding_report,
        }
        # Manual justification hint for later human/agent review
        if not final_ok:
            if cat in {"A", "B", "H"}:
                row["was_block_justified"] = True
                row["fail_closed_kind"] = "JUSTIFIED"
            elif cat in {"C", "D", "E"}:
                row["was_block_justified"] = False
                row["fail_closed_kind"] = "UNNECESSARY"
            elif cat == "F":
                row["was_block_justified"] = "MIXED"
                row["fail_closed_kind"] = "UNNECESSARY"  # fixable by better repair
            elif cat == "I":
                # empty after hard block vs empty wrongly
                if "WRITING_BLOCKED_HARD_REQUIREMENT" in row["final_blocking_errors"]:
                    row["was_block_justified"] = True
                    row["fail_closed_kind"] = "JUSTIFIED"
                    row["category"] = "H"
                else:
                    row["was_block_justified"] = False
                    row["fail_closed_kind"] = "UNNECESSARY"
            else:
                row["was_block_justified"] = "REVIEW"
                row["fail_closed_kind"] = "REVIEW"
        else:
            row["was_block_justified"] = None
            row["fail_closed_kind"] = None

        (OUT_DIR / f"{c['id']}.json").write_text(
            json.dumps(row, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        if body:
            (OUT_DIR / f"{c['id']}.txt").write_text(
                f"SUBJECT: {subj}\n\n{body}\n", encoding="utf-8"
            )
        rows.append(row)

    fail = [r for r in rows if not r["final_ok"]]
    from collections import Counter

    cats = Counter(r["category"] for r in fail)
    justified = sum(1 for r in fail if r.get("fail_closed_kind") == "JUSTIFIED")
    unnecessary = sum(1 for r in fail if r.get("fail_closed_kind") == "UNNECESSARY")
    review = sum(1 for r in fail if r.get("fail_closed_kind") == "REVIEW")

    summary = {
        "model": "phi4-mini",
        "n": len(rows),
        "final_accepted": sum(1 for r in rows if r["final_ok"]),
        "final_fail_closed": len(fail),
        "elapsed_s": round(time.perf_counter() - t0, 2),
        "category_counts_fail_closed": dict(cats),
        "JUSTIFIED_FAIL_CLOSED": justified,
        "UNNECESSARY_FAIL_CLOSED": unnecessary,
        "REVIEW_FAIL_CLOSED": review,
        "JUSTIFIED_FAIL_CLOSED_OF_30": justified,
        "UNNECESSARY_FAIL_CLOSED_OF_30": unnecessary,
        "rows": rows,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: summary[k] for k in summary if k != "rows"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
