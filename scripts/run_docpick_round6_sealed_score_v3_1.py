#!/usr/bin/env python3
"""Score sealed Round6 Docpick predictions with COMPLETE_GT_ONLY_V3_1_DATE_NORM.

Verifies prediction seal hashes BEFORE loading GT.
Does not modify parser, prompt, model, scorer code, or solution sheets.
Labels result as REGRESSION_KNOWN_CVS_NOT_BLIND (not independent blind / not 99%).
Round6 = re-extract after Round6 postprocess+prompt address/employment/software fixes.
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

OUT = ROOT / "tests" / "docpick_qwen35" / "regression_known_cvs_round6"
SEAL = OUT / "PHASE_A_EXTRACTION_SEAL.json"
INVENTORY = (
    ROOT / "tests" / "docpick_qwen35" / "regression_known_cvs" / "INVENTORY_GT_COMPLETENESS.json"
)
RESULT = OUT / "PHASE_B_COMPLETE_GT_ONLY_V3_1_RESULTS.json"
DONE = OUT / "PHASE_B_SCORING_DONE.json"


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
    if not SEAL.is_file():
        print(f"missing seal {SEAL}", file=sys.stderr)
        return 2
    if RESULT.is_file():
        print(f"refusing overwrite of existing {RESULT}", file=sys.stderr)
        return 3

    seal = json.loads(SEAL.read_text(encoding="utf-8"))
    assert seal.get("seal_type") == "PHASE_A_PREDICTION_SEAL_ROUND6"
    assert seal.get("n_ok") == 40
    assert seal.get("n_documents") == 40
    assert seal.get("test_type") == "REGRESSION_KNOWN_CVS_NOT_BLIND"
    # Protocol: gt must not have been loaded during extract (flag optional on early seals)
    if "gt_not_loaded" in seal:
        assert seal["gt_not_loaded"] is True

    # Verify prediction hashes before opening GT
    verified = []
    for p in seal["predictions"]:
        path = ROOT / p["prediction_file"]
        if not path.is_file():
            print(f"missing prediction {path}", file=sys.stderr)
            return 4
        h = _sha256_file(path)
        if h != p["sha256"]:
            print(f"HASH MISMATCH {path}", file=sys.stderr)
            return 5
        verified.append({**p, "sha256_verified": True})

    inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
    gt_by_corpus: dict[str, dict] = {}
    for c in inventory["corpora"]:
        gt_by_corpus[c["corpus_id"]] = _load_gt(c["corpus_id"], inventory)

    manifest = json.loads(
        (
            ROOT
            / "tests"
            / "docpick_qwen35"
            / "regression_known_cvs"
            / "EXTRACTION_MANIFEST_PDF_ONLY.json"
        ).read_text(encoding="utf-8")
    )
    pdf_by_key = {(d["corpus_id"], d["id"]): d for d in manifest["documents"]}

    doc_results = []
    real_errors = []
    by_lang_rows: dict[str, list] = defaultdict(list)

    for p in seal["predictions"]:
        corpus_id = p["corpus_id"]
        doc_id = p["id"]
        lang = p.get("lang") or pdf_by_key[(corpus_id, doc_id)].get("lang")
        pred = json.loads((ROOT / p["prediction_file"]).read_text(encoding="utf-8"))
        gt_docs = gt_by_corpus[corpus_id]
        gt = None
        for key in (doc_id, f"{doc_id}.pdf", pdf_by_key[(corpus_id, doc_id)]["path"]):
            if key in gt_docs:
                gt = gt_docs[key]
                break
        if gt is None:
            for k, v in gt_docs.items():
                if doc_id in str(k) or str(k).startswith(doc_id):
                    gt = v
                    break
        if gt is None:
            print(f"GT missing for {corpus_id}/{doc_id} keys={list(gt_docs)[:5]}", file=sys.stderr)
            return 6
        gt = _normalize_gt(gt)
        pdf_path = ROOT / pdf_by_key[(corpus_id, doc_id)]["path"]
        text = _pdf_text(pdf_path) if pdf_path.is_file() else ""
        fname = f"{corpus_id}__{doc_id}"
        dr = evaluate_doc_v3_1(fname, gt, pred, text)
        dr["corpus_id"] = corpus_id
        dr["doc_id"] = doc_id
        dr["lang"] = lang
        doc_results.append(dr)
        by_lang_rows[lang].extend(dr["scored_rows"])
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
    agg["metric_name"] = agg_wrap.get("metric_name")
    agg["disclaimer"] = agg_wrap.get("disclaimer")
    agg["date_norm_flipped_fields"] = agg_wrap.get("date_norm_flipped_fields")
    agg["nicht_bewertbar"] = agg_wrap.get("nicht_bewertbar")

    perfect = 0
    for dr in doc_results:
        rows = dr["scored_rows"]
        if rows and all(r.status == "correct" for r in rows):
            perfect += 1
    perfect_core = f"{perfect}/{len(doc_results)}"

    def lang_slice(lang: str) -> dict:
        docs = [d for d in doc_results if d.get("lang") == lang]
        pc = sum(
            1
            for d in docs
            if d["scored_rows"] and all(r.status == "correct" for r in d["scored_rows"])
        )
        from holdout_scorer_v3_complete_gt import aggregate_v3

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
        a["metric_name"] = a_wrap.get("metric_name")
        return a

    perf = seal.get("performance") or {}
    per_doc = perf.get("per_doc_s") or {}
    cold_id = seal["predictions"][0]["id"] if seal["predictions"] else None
    warm_id = seal["predictions"][1]["id"] if len(seal["predictions"]) > 1 else None

    out = {
        "test_type": "REGRESSION_KNOWN_CVS_NOT_BLIND",
        "metric_name": METRIC_NAME,
        "disclaimer": (
            "Round6 re-extract after Phase-3 present→heute norm + schema/prompt fixes. "
            "Known development CVs only. NOT an independent blind test. NOT a 99% claim."
        ),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "prediction_seal_path": str(SEAL.relative_to(ROOT)),
        "prediction_hashes_verified": True,
        "n_predictions_verified": len(verified),
        "parser_freeze_commit": (seal.get("parser_freeze") or {}).get("git_commit"),
        "det_fallback": False,
        "performance_from_seal": {
            "wall_s": perf.get("wall_s"),
            "avg_s_per_cv": perf.get("avg_s_per_cv"),
            "peak_rss_mb": perf.get("peak_rss_mb"),
            "cold_start_doc": cold_id,
            "cold_start_s": per_doc.get(cold_id) if cold_id else None,
            "followup_doc": warm_id,
            "followup_s": per_doc.get(warm_id) if warm_id else None,
            "per_doc_s": per_doc,
        },
        "coverage": {
            "n_documents_extracted": seal.get("n_documents"),
            "n_documents_extract_ok": seal.get("n_ok"),
            "n_documents_scored": len(doc_results),
            "n_scored_fields_total": agg.get("field_total"),
            "n_nicht_bewertbar_fields": sum(
                len(d.get("nicht_bewertbar") or []) for d in doc_results
            ),
            "perfect_core_on_scored_fields": perfect_core,
        },
        "metrics_complete_gt_only_v3_1": {
            **agg,
            "perfect_core": perfect_core,
        },
        "by_lang": {
            "de": lang_slice("de"),
            "en": lang_slice("en"),
        },
        "real_errors_on_complete_gt": real_errors,
        "error_status_counts": dict(Counter(e["status"] for e in real_errors)),
        "error_group_counts": dict(Counter(e["group"] for e in real_errors)),
    }

    RESULT.write_text(json.dumps(out, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    DONE.write_text(
        json.dumps(
            {
                "scored_at": out["created_at"],
                "metric": METRIC_NAME,
                "f1": agg.get("f1"),
                "perfect_core": perfect_core,
                "result_path": str(RESULT.relative_to(ROOT)),
                "test_type": "REGRESSION_KNOWN_CVS_NOT_BLIND",
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    scored_flag = OUT / "PHASE_A_SCORED_FLAG.json"
    scored_flag.write_text(
        json.dumps(
            {"gt_loaded_after_seal": True, "scored": True, "metric": METRIC_NAME},
            indent=2,
        ),
        encoding="utf-8",
    )

    print(
        json.dumps(
            {
                "ok": True,
                "test_type": "REGRESSION_KNOWN_CVS_NOT_BLIND",
                "f1": agg.get("f1"),
                "perfect_core": perfect_core,
                "hallu": agg.get("hallucination_rate"),
                "field_total": agg.get("field_total"),
                "de_f1": out["by_lang"]["de"].get("f1"),
                "en_f1": out["by_lang"]["en"].get("f1"),
                "avg_s": perf.get("avg_s_per_cv"),
                "peak_rss_mb": perf.get("peak_rss_mb"),
                "cold_s": out["performance_from_seal"]["cold_start_s"],
                "followup_s": out["performance_from_seal"]["followup_s"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
