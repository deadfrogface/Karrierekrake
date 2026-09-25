#!/usr/bin/env python3
"""Score whatever sealed Docpick predictions exist (partial or full).

REGRESSION only — NOT independent blind / NOT a 99% claim.
Does not modify GT or scorer logic.
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from holdout_scorer_v3_1_date_norm import (  # noqa: E402
    METRIC_NAME,
    aggregate_v3_1,
    evaluate_doc_v3_1,
)

OUT = ROOT / "tests/docpick_qwen35/regression_known_cvs_round3"
PRED_DIR = OUT / "frozen_predictions"
MANIFEST = ROOT / "tests/docpick_qwen35/regression_known_cvs/EXTRACTION_MANIFEST_PDF_ONLY.json"
INVENTORY = ROOT / "tests/docpick_qwen35/regression_known_cvs/INVENTORY_GT_COMPLETENESS.json"
RESULT = OUT / "PHASE_B_PARTIAL_OR_FULL_V3_1_RESULTS.json"


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _pdf_text(path: Path) -> str:
    try:
        import pymupdf

        doc = pymupdf.open(path)
        return "\n".join(page.get_text() for page in doc)
    except Exception:
        import fitz

        doc = fitz.open(path)
        return "\n".join(page.get_text() for page in doc)


def _load_gt(corpus_id: str, inventory: dict) -> dict:
    for c in inventory["corpora"]:
        if c["corpus_id"] == corpus_id:
            raw = json.loads((ROOT / c["gt_path"]).read_text(encoding="utf-8"))
            return raw["documents"]
    raise KeyError(corpus_id)


def _normalize_gt(g: dict) -> dict:
    g = dict(g)
    if g.get("dob") is None and g.get("date_of_birth") is not None:
        g["dob"] = g["date_of_birth"]
    return g


def main() -> int:
    if not PRED_DIR.is_dir():
        print(f"missing {PRED_DIR}", file=sys.stderr)
        return 2
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
    gt_by_corpus = {c["corpus_id"]: _load_gt(c["corpus_id"], inventory) for c in inventory["corpora"]}
    pdf_by_key = {(d["corpus_id"], d["id"]): d for d in manifest["documents"]}

    pred_files = sorted(PRED_DIR.glob("*.json"))
    if not pred_files:
        print("no predictions", file=sys.stderr)
        return 3

    doc_results = []
    real_errors = []
    meta = []

    for path in pred_files:
        stem = path.stem  # CORPUS__DOCID
        if "__" not in stem:
            continue
        corpus_id, doc_id = stem.split("__", 1)
        pred = json.loads(path.read_text(encoding="utf-8"))
        if pred.get("tech_error"):
            continue
        key = (corpus_id, doc_id)
        if key not in pdf_by_key:
            print(f"skip unknown {stem}", flush=True)
            continue
        gt_docs = gt_by_corpus[corpus_id]
        gt = None
        for k in (doc_id, f"{doc_id}.pdf", pdf_by_key[key]["path"]):
            if k in gt_docs:
                gt = gt_docs[k]
                break
        if gt is None:
            for k, v in gt_docs.items():
                if doc_id in str(k) or str(k).startswith(doc_id):
                    gt = v
                    break
        if gt is None:
            print(f"GT missing {stem}", file=sys.stderr)
            return 6
        gt = _normalize_gt(gt)
        pdf_path = ROOT / pdf_by_key[key]["path"]
        text = _pdf_text(pdf_path) if pdf_path.is_file() else ""
        lang = pdf_by_key[key].get("lang") or pred.get("regression_lang")
        fname = stem
        dr = evaluate_doc_v3_1(fname, gt, pred, text)
        dr["corpus_id"] = corpus_id
        dr["doc_id"] = doc_id
        dr["lang"] = lang
        doc_results.append(dr)
        meta.append(
            {
                "corpus_id": corpus_id,
                "id": doc_id,
                "lang": lang,
                "prediction_file": str(path.relative_to(ROOT)),
                "sha256": _sha256_file(path),
            }
        )
        for r in dr["scored_rows"]:
            if r.status in {"wrong", "missing", "hallucinated", "wrong_category"}:
                real_errors.append(
                    {
                        "document": fname,
                        "lang": lang,
                        "field": r.field,
                        "group": r.group,
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
    n_manifest = len(manifest["documents"])
    partial = len(doc_results) < n_manifest

    def lang_slice(lang: str) -> dict:
        docs = [d for d in doc_results if d.get("lang") == lang]
        if not docs:
            return {"n_documents": 0, "f1": None}
        from holdout_scorer_v3_complete_gt import aggregate_v3

        pc = sum(
            1
            for d in docs
            if d["scored_rows"] and all(r.status == "correct" for r in d["scored_rows"])
        )
        a_wrap = aggregate_v3(
            [
                {
                    "document": d["document"],
                    "scored_rows": d["scored_rows"],
                    "nicht_bewertbar": d["nicht_bewertbar"],
                }
                for d in docs
            ]
        )
        a = dict(a_wrap.get("complete_gt_scored") or a_wrap)
        a["perfect_core"] = f"{pc}/{len(docs)}"
        a["n_documents"] = len(docs)
        return a

    out = {
        "test_type": "REGRESSION_KNOWN_CVS_NOT_BLIND",
        "partial": partial,
        "metric_name": METRIC_NAME,
        "disclaimer": (
            "Partial or full Round3 score on known development CVs. "
            "NOT an independent blind test. NOT a 99% claim."
            + (f" Scored {len(doc_results)}/{n_manifest} documents so far." if partial else "")
        ),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "n_scored": len(doc_results),
        "n_manifest": n_manifest,
        "predictions": meta,
        "coverage": {
            "n_documents_scored": len(doc_results),
            "n_scored_fields_total": agg.get("field_total"),
            "perfect_core_on_scored_fields": perfect_core,
        },
        "metrics_complete_gt_only_v3_1": {**agg, "perfect_core": perfect_core},
        "by_lang": {"de": lang_slice("de"), "en": lang_slice("en")},
        "real_errors_on_complete_gt": real_errors,
        "error_status_counts": dict(Counter(e["status"] for e in real_errors)),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    RESULT.write_text(json.dumps(out, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    summary = {
        "partial": partial,
        "n_scored": len(doc_results),
        "n_manifest": n_manifest,
        "f1": agg.get("f1"),
        "perfect_core": perfect_core,
        "missing": agg.get("counts", {}).get("missing") if isinstance(agg.get("counts"), dict) else None,
        "wrong": agg.get("counts", {}).get("wrong") if isinstance(agg.get("counts"), dict) else None,
        "hallucinated": agg.get("counts", {}).get("hallucinated")
        if isinstance(agg.get("counts"), dict)
        else None,
        "de_f1": out["by_lang"]["de"].get("f1"),
        "en_f1": out["by_lang"]["en"].get("f1"),
        "result": str(RESULT.relative_to(ROOT)),
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
