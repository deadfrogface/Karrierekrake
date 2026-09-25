#!/usr/bin/env python3
"""NV3 Post-Analysis score for Round8 predictions (or targeted).

Does NOT modify frozen Phase-A predictions / PHASE_B blind results / scorer.
Uses already-mapped expected_results_full_v3.json from Phase B.
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from holdout_scorer_v3_1_date_norm import (  # noqa: E402
    METRIC_NAME,
    aggregate_v3_1,
    evaluate_doc_v3_1,
)

OUT = ROOT / "tests/docpick_blind_de_en_v2/post_analysis_round8"
GT_MAPPED = (
    ROOT
    / "tests/docpick_blind_de_en_v2/phase_b_solutions/expected_results_full_v3.json"
)
FROZEN_RESULT = (
    ROOT / "tests/docpick_blind_de_en_v2/PHASE_B_COMPLETE_GT_ONLY_V3_1_RESULTS.json"
)
PDF_DIR = ROOT / "tests/docpick_blind_de_en_v2/phase_a_pdfs"


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _pdf_text(path: Path) -> str:
    try:
        import pymupdf

        doc = pymupdf.open(path)
        return "\n".join(page.get_text() for page in doc)
    except Exception:
        try:
            import fitz

            doc = fitz.open(path)
            return "\n".join(page.get_text() for page in doc)
        except Exception:
            return ""


def main() -> int:
    if not GT_MAPPED.is_file():
        print(f"missing GT {GT_MAPPED}", file=sys.stderr)
        return 2
    pred_dir = OUT / "predictions"
    paths: list[Path] = []
    if pred_dir.is_dir():
        paths = sorted(pred_dir.glob("NV3_*.json"))
    if not paths:
        paths = sorted(OUT.glob("pred_NV3_*.json"))
    if not paths:
        print("no post-analysis predictions found", file=sys.stderr)
        return 3

    gt_docs = json.loads(GT_MAPPED.read_text(encoding="utf-8"))["documents"]
    per_doc: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for path in paths:
        did = path.stem.replace("pred_", "")
        pdf_key = f"{did}.pdf"
        if pdf_key not in gt_docs:
            print(f"skip {did}: no GT", flush=True)
            continue
        pred = json.loads(path.read_text(encoding="utf-8"))
        if pred.get("tech_error"):
            print(f"skip {did}: tech_error", flush=True)
            continue
        gt = gt_docs[pdf_key]
        pdf_path = PDF_DIR / pdf_key
        text = _pdf_text(pdf_path) if pdf_path.is_file() else ""
        dr = evaluate_doc_v3_1(did, gt, pred, text)
        dr["lang"] = (gt.get("language") or "").lower()
        per_doc.append(dr)
        for r in dr["scored_rows"]:
            if r.status in {"wrong", "missing", "hallucinated", "wrong_category"}:
                errors.append(
                    {
                        "document": did,
                        "lang": dr["lang"],
                        "field": r.field,
                        "group": r.group,
                        "status": r.status,
                        "expected": r.expected,
                        "actual": r.actual,
                    }
                )

    agg_wrap = aggregate_v3_1(per_doc)
    agg = dict(agg_wrap.get("complete_gt_scored") or {})
    lang_metrics = {}
    for lang in sorted({d.get("lang") for d in per_doc}):
        docs = [d for d in per_doc if d.get("lang") == lang]
        wrap = aggregate_v3_1(docs)
        lang_metrics[lang] = dict(wrap.get("complete_gt_scored") or {})

    perfect = sum(
        1
        for d in per_doc
        if d["scored_rows"] and all(r.status == "correct" for r in d["scored_rows"])
    )

    frozen_f1 = None
    if FROZEN_RESULT.is_file():
        fr = json.loads(FROZEN_RESULT.read_text(encoding="utf-8"))
        frozen_f1 = (fr.get("metrics_complete_gt_only_v3_1") or {}).get("f1")

    per_doc_out = []
    for d in per_doc:
        per_doc_out.append(
            {
                "document": d["document"],
                "lang": d.get("lang"),
                "n_scored": len(d["scored_rows"]),
                "n_correct": sum(1 for r in d["scored_rows"] if r.status == "correct"),
            }
        )

    status_counts: dict[str, int] = defaultdict(int)
    for e in errors:
        status_counts[e["status"]] += 1

    out = {
        "test_type": "POST_ANALYSIS_NV3_NOT_BLIND",
        "metric_name": METRIC_NAME,
        "disclaimer": (
            "Post-Analysis only. Frozen Blind F1 0.980 unchanged. No 99% claim."
        ),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "n_scored": len(per_doc),
        "perfect_core": f"{perfect}/{len(per_doc)}",
        "frozen_blind_f1_reference": frozen_f1,
        "frozen_artifacts_sha256": {
            "PHASE_B_RESULTS": _sha256_file(FROZEN_RESULT)
            if FROZEN_RESULT.is_file()
            else None,
        },
        "metrics_complete_gt_only_v3_1": agg,
        "by_lang": lang_metrics,
        "real_errors_on_complete_gt": errors,
        "error_status_counts": dict(status_counts),
        "per_document": per_doc_out,
    }
    out_path = OUT / "POST_ANALYSIS_SCORE.json"
    out_path.write_text(
        json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(
        f"Wrote {out_path} n={len(per_doc)} f1={agg.get('f1')} "
        f"PC={perfect}/{len(per_doc)} (frozen ref {frozen_f1})",
        flush=True,
    )
    print(f"errors={len(errors)} by_status={dict(status_counts)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
