#!/usr/bin/env python3
"""Score sealed Blind DE/EN v1 predictions with COMPLETE_GT_ONLY_V3_1 after seal verify."""

from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from holdout_scorer_v3_1_date_norm import METRIC_NAME, aggregate_v3_1, evaluate_doc_v3_1  # noqa: E402

OUT = ROOT / "tests/docpick_blind_de_en_v1"
SEAL = OUT / "PHASE_A_EXTRACTION_SEAL.json"
GT = OUT / "phase_b_solutions/expected_results_full_v3.json"
RESULT = OUT / "PHASE_B_COMPLETE_GT_ONLY_V3_1_RESULTS.json"


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _pdf_text(path: Path) -> str:
    try:
        import pymupdf

        doc = pymupdf.open(path)
        return "\n".join(page.get_text() for page in doc)
    except Exception:
        return ""


def _normalize_gt(g: dict) -> dict:
    g = dict(g)
    if g.get("dob") is None and g.get("date_of_birth") is not None:
        g["dob"] = g["date_of_birth"]
    return g


def main() -> int:
    if not SEAL.is_file():
        print(f"missing seal {SEAL}", file=sys.stderr)
        return 2
    seal = json.loads(SEAL.read_text(encoding="utf-8"))
    assert seal.get("gt_not_loaded") is True
    assert seal.get("test_type") == "INDEPENDENT_BLIND_DE_EN"
    for p in seal["predictions"]:
        path = ROOT / p["prediction_file"]
        if _sha256_file(path) != p["sha256"]:
            print(f"HASH MISMATCH {path}", file=sys.stderr)
            return 5

    gt_raw = json.loads(GT.read_text(encoding="utf-8"))
    gt_docs = gt_raw["documents"]
    doc_results = []
    errors = []
    for p in seal["predictions"]:
        pred = json.loads((ROOT / p["prediction_file"]).read_text(encoding="utf-8"))
        pdf_name = Path(p["pdf"]).name
        gt = _normalize_gt(gt_docs[pdf_name])
        text = _pdf_text(ROOT / p["pdf"])
        dr = evaluate_doc_v3_1(p["id"], gt, pred, text)
        dr["lang"] = p.get("lang")
        doc_results.append(dr)
        for r in dr["scored_rows"]:
            if r.status in {"wrong", "missing", "hallucinated", "wrong_category"}:
                errors.append(
                    {
                        "document": p["id"],
                        "lang": p.get("lang"),
                        "field": r.field,
                        "status": r.status,
                        "expected": r.expected,
                        "actual": r.actual,
                    }
                )

    agg_wrap = aggregate_v3_1(doc_results)
    agg = dict(agg_wrap.get("complete_gt_scored") or {})
    perfect = sum(
        1
        for d in doc_results
        if d["scored_rows"] and all(r.status == "correct" for r in d["scored_rows"])
    )
    perfect_core = f"{perfect}/{len(doc_results)}"

    def lang_f1(lang: str):
        docs = [d for d in doc_results if d.get("lang") == lang]
        if not docs:
            return None
        from holdout_scorer_v3_complete_gt import aggregate_v3

        a = aggregate_v3(
            [
                {
                    "document": d["document"],
                    "scored_rows": d["scored_rows"],
                    "nicht_bewertbar": d["nicht_bewertbar"],
                }
                for d in docs
            ]
        )
        scored = a.get("complete_gt_scored") or a
        return scored.get("f1")

    out = {
        "test_type": "INDEPENDENT_BLIND_DE_EN",
        "metric_name": METRIC_NAME,
        "disclaimer": (
            "Independent synthetic Blind DE/EN v1 (n=4). "
            "NOT Round2/Round3. Small-n — not a large-scale 99% claim by itself; "
            "report F1 honestly and do not upgrade to production solely on n=4."
        ),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "prediction_hashes_verified": True,
        "n_documents": len(doc_results),
        "parser_freeze_commit": (seal.get("parser_freeze") or {}).get("git_commit"),
        "performance_from_seal": seal.get("performance"),
        "coverage": {
            "perfect_core_on_scored_fields": perfect_core,
            "n_scored_fields_total": agg.get("field_total"),
        },
        "metrics_complete_gt_only_v3_1": {**agg, "perfect_core": perfect_core},
        "by_lang": {"de_f1": lang_f1("de"), "en_f1": lang_f1("en")},
        "real_errors": errors,
        "error_status_counts": dict(Counter(e["status"] for e in errors)),
        "claim_99_percent": False,
        "claim_99_reason": "Requires Blind F1>=0.99 on full predeclared field schema; n=4 is informative only.",
    }
    RESULT.write_text(json.dumps(out, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "f1": agg.get("f1"),
                "perfect_core": perfect_core,
                "de_f1": out["by_lang"]["de_f1"],
                "en_f1": out["by_lang"]["en_f1"],
                "warm_avg_s": (seal.get("performance") or {}).get("warm_avg_s"),
                "warm_within_budget": (seal.get("performance") or {}).get("warm_within_budget"),
                "claim_99": False,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
