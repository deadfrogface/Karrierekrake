#!/usr/bin/env python3
"""Phase-A forensic audit of Phase-2 Phi blind covers (no model calls)."""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW = (
    ROOT
    / "benchmark/guenther_final_model_shootout_raw/phase1/phi4-mini/phase2_new_fixture_covers"
)
FIXTURE = ROOT / "benchmark/guenther_final_model_shootout_fixture.json"
OUT = ROOT / "benchmark/guenther_quality_loop_raw/phase2_failure_forensics.json"

CATEGORIES = [
    "SAFETY_BLOCK_TRUE",
    "TARGETING_BLOCK_TRUE",
    "CLAIM_GROUNDING_FAILURE",
    "CLAIM_EXTRACTION_FALSE_POSITIVE",
    "EVIDENCE_MATCH_FAILURE",
    "COMPANY_FAILURE",
    "ROLE_FAILURE",
    "PLACEHOLDER_FAILURE",
    "STRUCTURAL_FAILURE",
    "GENERIC_WRITING",
    "WEAK_SPECIFICITY",
    "WEAK_EVIDENCE_SELECTION",
    "POOR_TRANSFERABLE_EXPERIENCE_FRAMING",
    "WEAK_OPENING",
    "WEAK_CLOSING",
    "REPETITION",
    "ROBOTIC_GERMAN",
    "IRRELEVANT_EVIDENCE",
    "MISSED_STRONG_EVIDENCE",
    "REPAIR_FAILURE",
    "OTHER",
]

GENERIC = (
    "mit großem interesse",
    "hiermit bewerbe ich mich",
    "renommiertes unternehmen",
    "meine leidenschaft",
    "ich bin überzeugt",
)
SAFETY_CODES = {
    "UNSUPPORTED_CREDENTIAL",
    "CONTRADICTED_CLAIM",
    "HARD_REQUIREMENT_FALSE_CLAIM",
    "WRONG_COMPANY",
    "ROLE_REVERSAL",
    "UNRESOLVED_PLACEHOLDER",
    "UNSUPPORTED_MATERIAL_CLAIM",
    "RELATED_PRESENTED_AS_DIRECT",
}


def classify(case: dict, fx: dict) -> list[str]:
    labels: set[str] = set()
    body = case.get("body") or ""
    low = body.lower()
    codes = set(case.get("final_errors") or [])
    notes = set(case.get("notes") or [])

    if not case.get("final_ok"):
        if case.get("repair_count"):
            labels.add("REPAIR_FAILURE")
        if codes & {"UNSUPPORTED_CREDENTIAL", "HARD_REQUIREMENT_FALSE_CLAIM", "UNSUPPORTED_MATERIAL_CLAIM"}:
            labels.add("CLAIM_GROUNDING_FAILURE")
            labels.add("SAFETY_BLOCK_TRUE")
        if "UNRESOLVED_PLACEHOLDER" in codes:
            labels.add("PLACEHOLDER_FAILURE")
            labels.add("SAFETY_BLOCK_TRUE")
        if "WRONG_COMPANY" in codes or "missing_company" in notes:
            labels.add("COMPANY_FAILURE")
            labels.add("SAFETY_BLOCK_TRUE")
        if "ROLE_REVERSAL" in codes or "WRONG_TARGET_ROLE" in codes:
            labels.add("ROLE_FAILURE")
            labels.add("SAFETY_BLOCK_TRUE")
        if "WRITING_BLOCKED_HARD_REQUIREMENT" in codes:
            labels.add("TARGETING_BLOCK_TRUE")
        if "EMPTY_OUTPUT" in codes or not body.strip():
            labels.add("STRUCTURAL_FAILURE")
        if not labels:
            labels.add("OTHER")

    # Quality labels (also for accepted-but-not-ready)
    if case.get("edit_class") != "READY_AS_IS" or (case.get("score") or 0) < 8.0:
        if any(p in low for p in GENERIC):
            labels.add("GENERIC_WRITING")
        if low.startswith("ich schreibe") or "ich freue mich darauf, meine" in low:
            labels.add("WEAK_OPENING")
        if len(body.strip()) < 280:
            labels.add("WEAK_SPECIFICITY")
        if body.count(" ich ") + (1 if low.startswith("ich ") else 0) >= 8:
            labels.add("REPETITION")
        if re.search(r"\b(the|and|with|experience)\b", low):
            labels.add("ROBOTIC_GERMAN")
        if "missing_company" in notes:
            labels.add("COMPANY_FAILURE")
        # Heuristic: short letter with little profile detail
        if case.get("final_ok") and (case.get("score") or 0) < 8 and "WEAK_SPECIFICITY" not in labels:
            labels.add("WEAK_EVIDENCE_SELECTION")
        if not labels:
            labels.add("OTHER")

    return sorted(labels)


def main() -> None:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    covers = {c["id"]: c for c in fixture.get("covers") or []}
    rows = []
    counts: Counter[str] = Counter()
    primary: Counter[str] = Counter()

    for path in sorted(RAW.glob("*.json")):
        case = json.loads(path.read_text(encoding="utf-8"))
        fx = covers.get(case["id"], {})
        cats = classify(case, fx)
        for c in cats:
            counts[c] += 1
        primary_cat = cats[0] if cats else "OTHER"
        # Prefer safety categories as primary for fail-closed
        for prefer in (
            "SAFETY_BLOCK_TRUE",
            "PLACEHOLDER_FAILURE",
            "CLAIM_GROUNDING_FAILURE",
            "STRUCTURAL_FAILURE",
            "GENERIC_WRITING",
            "WEAK_SPECIFICITY",
        ):
            if prefer in cats:
                primary_cat = prefer
                break
        primary[primary_cat] += 1
        rows.append(
            {
                "id": case["id"],
                "final_ok": case.get("final_ok"),
                "expect_hard_block": case.get("expect_hard_block"),
                "eligible_safe": not bool(case.get("expect_hard_block")),
                "score": case.get("score"),
                "edit_class": case.get("edit_class"),
                "repair_count": case.get("repair_count"),
                "final_errors": case.get("final_errors"),
                "notes": case.get("notes"),
                "categories": cats,
                "primary_category": primary_cat,
            }
        )

    eligible = [r for r in rows if r["eligible_safe"]]
    fail_elig = [r for r in eligible if not r["final_ok"]]
    not_ready = [r for r in rows if r["edit_class"] != "READY_AS_IS"]
    below8 = [r for r in rows if (r.get("score") or 0) < 8.0]
    repair = [r for r in rows if (r.get("repair_count") or 0) > 0]
    repair_failed = [r for r in repair if not r["final_ok"]]

    out = {
        "purpose": "Phase-A forensic analysis of Phase-2 Phi blind covers",
        "n_cases": len(rows),
        "eligible_safe_n": len(eligible),
        "unnecessary_fail_closed_eligible": len(fail_elig),
        "not_ready_as_is": len(not_ready),
        "below_8": len(below8),
        "repair_required": len(repair),
        "repair_failed": len(repair_failed),
        "category_counts": {k: counts[k] for k in CATEGORIES},
        "primary_category_counts": dict(primary),
        "unnecessary_fail_closed_ids": [r["id"] for r in fail_elig],
        "unnecessary_fail_closed_root_causes": {
            "CLAIM_GROUNDING_FAILURE_UNSUPPORTED_CREDENTIAL": sum(
                1
                for r in fail_elig
                if "CLAIM_GROUNDING_FAILURE" in r["categories"]
            ),
            "PLACEHOLDER_FAILURE": sum(
                1 for r in fail_elig if "PLACEHOLDER_FAILURE" in r["categories"]
            ),
            "STRUCTURAL_EMPTY_OUTPUT": sum(
                1 for r in fail_elig if "STRUCTURAL_FAILURE" in r["categories"]
            ),
            "REPAIR_FAILED_AFTER_MAX1": len(fail_elig),
        },
        "not_ready_root_causes": {
            "fail_closed_safety_or_structure": len(fail_elig),
            "accepted_but_score_below_8_or_material_edit": len(
                [r for r in not_ready if r["final_ok"]]
            ),
            "generic_or_weak_specificity": sum(
                1
                for r in not_ready
                if "GENERIC_WRITING" in r["categories"]
                or "WEAK_SPECIFICITY" in r["categories"]
            ),
        },
        "cases": rows,
        "category_vocabulary": CATEGORIES,
        "note": (
            "Eligible fail-closed (14/94) are counted as unnecessary for automation metric "
            "in shootout summary; most carry real safety codes (placeholder/credential) that "
            "the quality loop must prevent via plan+draft constraints — not by weakening gates."
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: out[k] for k in out if k != "cases"}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
