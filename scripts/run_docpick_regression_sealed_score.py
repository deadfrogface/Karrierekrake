#!/usr/bin/env python3
"""Score sealed Docpick regression predictions with COMPLETE_GT_ONLY_V3.

Loads GT only AFTER verifying prediction seal hashes.
Does not modify parser, prompt, scorer V2, or solution sheets.
Labels result as REGRESSION_KNOWN_CVS_NOT_BLIND.
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

from holdout_scorer_v3_complete_gt import (  # noqa: E402
    METRIC_NAME,
    aggregate_v3,
    evaluate_doc_v3,
)

OUT = ROOT / "tests" / "docpick_qwen35" / "regression_known_cvs"
SEAL = OUT / "PHASE_A_EXTRACTION_SEAL.json"
INVENTORY = OUT / "INVENTORY_GT_COMPLETENESS.json"
RESULT = OUT / "PHASE_B_COMPLETE_GT_ONLY_V3_RESULTS.json"


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
    seal = json.loads(SEAL.read_text(encoding="utf-8"))
    assert seal.get("gt_not_loaded") is True
    assert seal.get("scoring_not_run_yet") is True

    # Verify prediction hashes before opening GT
    verified = []
    for p in seal["predictions"]:
        path = ROOT / p["prediction_file"]
        h = _sha256_file(path)
        if h != p["sha256"]:
            print(f"HASH MISMATCH {path}", file=sys.stderr)
            return 3
        verified.append(p)

    inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
    # Map corpus -> filename -> lang/meta
    meta_by = {}
    for c in inventory["corpora"]:
        for d in c["documents"]:
            meta_by[(c["corpus_id"], d["filename"])] = d

    gt_cache = {}
    doc_results = []
    error_examples = []
    by_corpus_lang_rows = defaultdict(list)
    by_corpus_nb = defaultdict(list)

    for p in verified:
        pred = json.loads((ROOT / p["prediction_file"]).read_text(encoding="utf-8"))
        corpus = p["corpus_id"]
        # resolve filename
        fname = Path(p["pdf"]).name
        if corpus not in gt_cache:
            gt_cache[corpus] = _load_gt(corpus, inventory)
        g = _normalize_gt(gt_cache[corpus][fname])
        text = _pdf_text(ROOT / p["pdf"])
        dr = evaluate_doc_v3(fname, g, pred if not pred.get("tech_error") else {}, text)
        dr["corpus_id"] = corpus
        dr["lang"] = p["lang"]
        dr["prediction_ok"] = p["ok"]
        doc_results.append(dr)
        by_corpus_lang_rows[(corpus, p["lang"])].extend(dr["scored_rows"])
        by_corpus_nb[(corpus, p["lang"])].extend(dr["nicht_bewertbar"])

        for r in dr["scored_rows"]:
            if r.status in {"missing", "hallucinated", "wrong", "wrong_category"}:
                # evidence snippet
                needle = str(r.expected or r.actual or "")[:80]
                idx = text.lower().find(str(r.expected or "").lower()[:40]) if r.expected else -1
                snippet = text[max(0, idx - 40) : idx + 120].replace("\n", " ") if idx >= 0 else text[:160].replace("\n", " ")
                error_examples.append(
                    {
                        "corpus_id": corpus,
                        "document": fname,
                        "lang": p["lang"],
                        "field": r.field,
                        "group": r.group,
                        "status": r.status,
                        "expected": r.expected,
                        "actual": r.actual,
                        "cv_text_snippet": snippet,
                    }
                )

    overall = aggregate_v3(doc_results)

    def pack_rows(rows, nb_list):
        from holdout_scorer_v2 import aggregate_v2

        agg = aggregate_v2(rows) if rows else {
            "f1": 0.0,
            "precision": 0.0,
            "recall": 0.0,
            "hallucination_rate": 0.0,
            "missing_field_rate": 0.0,
            "field_total": 0,
            "counts": {},
        }
        return {
            **agg,
            "n_scored_fields": len([r for r in rows if r.status != "skipped"]),
            "n_nicht_bewertbar_fields": len(nb_list),
            "n_documents": len({r.document for r in rows}) if rows else 0,
            "perfect_core_documents": None,  # computed below per doc
        }

    # Perfect core only on fully scored docs: all scored rows correct and no missing
    # Among docs that have at least one scored field
    per_doc_summary = []
    perfect_core = 0
    docs_with_scores = 0
    for dr in doc_results:
        rows = [r for r in dr["scored_rows"] if r.status != "skipped"]
        if not rows:
            per_doc_summary.append(
                {
                    "corpus_id": dr["corpus_id"],
                    "document": dr["document"],
                    "lang": dr["lang"],
                    "n_scored": 0,
                    "n_nicht_bewertbar": len(dr["nicht_bewertbar"]),
                    "perfect_core_on_scored_fields": None,
                    "note": "no complete-GT fields scored",
                }
            )
            continue
        docs_with_scores += 1
        ok = all(r.status == "correct" for r in rows)
        if ok:
            perfect_core += 1
        per_doc_summary.append(
            {
                "corpus_id": dr["corpus_id"],
                "document": dr["document"],
                "lang": dr["lang"],
                "n_scored": len(rows),
                "n_nicht_bewertbar": len(dr["nicht_bewertbar"]),
                "statuses": dict(Counter(r.status for r in rows)),
                "perfect_core_on_scored_fields": ok,
            }
        )

    slices = {}
    for (corpus, lang), rows in sorted(by_corpus_lang_rows.items()):
        slices[f"{corpus}/{lang}"] = pack_rows(rows, by_corpus_nb[(corpus, lang)])

    corpus_slices = {}
    for corpus in {c["corpus_id"] for c in inventory["corpora"]}:
        rows = []
        nb = []
        for dr in doc_results:
            if dr["corpus_id"] == corpus:
                rows.extend(dr["scored_rows"])
                nb.extend(dr["nicht_bewertbar"])
        corpus_slices[corpus] = pack_rows(rows, nb)

    lang_slices = {}
    for lang in ("de", "en"):
        rows = []
        nb = []
        for dr in doc_results:
            if dr["lang"] == lang:
                rows.extend(dr["scored_rows"])
                nb.extend(dr["nicht_bewertbar"])
        lang_slices[lang] = pack_rows(rows, nb)

    # Coverage: can we compute overall F1 including emp/edu?
    smoke_emp_complete = all(
        d["employment_gt"] == "complete"
        for c in inventory["corpora"]
        if c["corpus_id"] == "SMOKE_DE_EN_10_V1"
        for d in c["documents"]
    )
    overall_f1_possible = smoke_emp_complete and all(
        d["employment_gt"] == "complete" and d["education_gt"] == "complete"
        for c in inventory["corpora"]
        for d in c["documents"]
    )

    result = {
        "test_type": "REGRESSION_KNOWN_CVS_NOT_BLIND",
        "metric_name": METRIC_NAME,
        "disclaimer": (
            "Regression on known CVs. Extraction was GT-blind and sealed, "
            "but documents/solutions were previously known to the project. "
            "NOT an independent blind test. NOT a 99% claim on unknown CVs."
        ),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "prediction_seal_path": str(SEAL.relative_to(ROOT)),
        "prediction_hashes_verified": True,
        "parser_freeze_commit": seal.get("parser_freeze", {}).get("git_commit"),
        "det_fallback": False,
        "det_blocked_at_freeze": seal.get("parser_freeze", {}).get("det_parse_cv_text_blocked"),
        "performance_from_seal": seal.get("performance"),
        "coverage": {
            "n_documents_extracted": seal["n_documents"],
            "n_documents_extract_ok": seal["n_ok"],
            "n_documents_with_scored_fields": docs_with_scores,
            "n_scored_fields_total": overall["complete_gt_scored"].get("field_total"),
            "n_nicht_bewertbar_fields": overall["nicht_bewertbar"]["n_fields"],
            "perfect_core_on_scored_fields": f"{perfect_core}/{docs_with_scores}",
            "overall_f1_including_all_emp_edu_possible": overall_f1_possible,
            "overall_f1_possible_reason": (
                "All corpora have complete employment+education lists"
                if overall_f1_possible
                else "SMOKE_DE_EN_10 lacks full employment/education lists (count-only) → no full overall F1"
            ),
        },
        "metrics_complete_gt_only": overall["complete_gt_scored"],
        "nicht_bewertbar": {
            "n_fields": overall["nicht_bewertbar"]["n_fields"],
            "by_group": overall["nicht_bewertbar"]["by_group"],
            "by_reason": overall["nicht_bewertbar"]["by_reason"],
        },
        "by_language": lang_slices,
        "by_corpus": corpus_slices,
        "by_corpus_language": slices,
        "per_document": per_doc_summary,
        "real_errors_on_complete_gt": error_examples,
        "quality_claim": overall["quality_claim_scope"],
    }
    RESULT.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")

    # Mark seal scoring done (append companion file; do not rewrite sealed hashes)
    (OUT / "PHASE_B_SCORING_DONE.json").write_text(
        json.dumps(
            {
                "scored_at": datetime.now(timezone.utc).isoformat(),
                "seal_sha256": _sha256_file(SEAL),
                "result_path": str(RESULT.relative_to(ROOT)),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    m = result["metrics_complete_gt_only"]
    print(
        f"V3 F1={m.get('f1')} P={m.get('precision')} R={m.get('recall')} "
        f"hallu={m.get('hallucination_rate')} missing={m.get('n_missing')} "
        f"nb={result['nicht_bewertbar']['n_fields']} errors={len(error_examples)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
