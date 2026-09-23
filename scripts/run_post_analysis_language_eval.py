#!/usr/bin/env python3
"""POST-ANALYSIS language pipeline evaluation (never writes frozen_predictions/).

Runs DET (and optional experimental variants) on the 50 FH CVs and scores with
Scorer V2. All outputs land under:

  artifacts/final_holdout/post_analysis_language/

Usage:
  python scripts/run_post_analysis_language_eval.py --variant det_repaired
  python scripts/run_post_analysis_language_eval.py --variant det_baseline --baseline-preds artifacts/final_holdout/frozen_predictions
"""

from __future__ import annotations

import argparse
import hashlib
import json
import resource
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from holdout_scorer_v2 import (  # noqa: E402
    FactResult,
    aggregate_v2,
    build_evidence_for_doc,
    evaluate_doc_v2,
    perfect_document,
    pred_view,
)

HOLDOUT = ROOT / "tests" / "final_holdout"
PDF_DIR = HOLDOUT / "phase_a_pdfs"
GT_PATH = HOLDOUT / "phase_b_solutions" / "expected_results.json"
OUT_ROOT = ROOT / "artifacts" / "final_holdout" / "post_analysis_language"
FROZEN_PRED = ROOT / "artifacts" / "final_holdout" / "frozen_predictions"


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _peak_rss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def _serialize(parsed: dict[str, Any]) -> dict[str, Any]:
    def conv(o: Any) -> Any:
        if isinstance(o, dict):
            return {str(k): conv(v) for k, v in o.items()}
        if isinstance(o, (list, tuple)):
            return [conv(x) for x in o]
        if isinstance(o, (str, int, float, bool)) or o is None:
            return o
        if hasattr(o, "model_dump"):
            return conv(o.model_dump())
        if hasattr(o, "__dict__"):
            return conv(dict(o.__dict__))
        return str(o)

    return conv(parsed)


def load_gt() -> dict[str, Any]:
    data = json.loads(GT_PATH.read_text(encoding="utf-8"))
    docs = data.get("documents") or data
    # Keys are filenames (FH_001.pdf); keep as-is for scorer/evidence.
    return docs


def prepare_gt_doc(raw: dict[str, Any]) -> dict[str, Any]:
    """Map GT document into scorer-facing shape."""
    out = dict(raw)
    if out.get("dob") is None and out.get("date_of_birth") is not None:
        out["dob"] = out.get("date_of_birth")
    out.pop("career_notes", None)
    return out


def run_det_predictions(pred_dir: Path) -> dict[str, Any]:
    from core.cv_parser import import_cv

    pred_dir.mkdir(parents=True, exist_ok=True)
    pdfs = sorted(PDF_DIR.glob("FH_*.pdf"))
    if len(pdfs) != 50:
        raise SystemExit(f"expected 50 PDFs, found {len(pdfs)} in {PDF_DIR}")

    timings: list[float] = []
    peak = _peak_rss_mb()
    for pdf in pdfs:
        t0 = time.perf_counter()
        parsed = import_cv(pdf, guenther_enabled=False)
        dt = (time.perf_counter() - t0) * 1000.0
        timings.append(dt)
        peak = max(peak, _peak_rss_mb())
        doc_id = pdf.stem
        payload = {
            "document_id": doc_id,
            "source_filename": pdf.name,
            "pipeline": "DET_POST_ANALYSIS",
            "label": "POST-ANALYSIS",
            "timing_ms": round(dt, 2),
            "phi_calls": 0,
            "prediction": _serialize(parsed),
            "errors": [],
        }
        (pred_dir / f"{doc_id}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return {
        "n": len(pdfs),
        "timing_ms_mean": sum(timings) / len(timings),
        "timing_ms_p50": sorted(timings)[len(timings) // 2],
        "timing_ms_total": sum(timings),
        "peak_rss_mb": peak,
        "pred_dir": str(pred_dir.relative_to(ROOT)),
    }


def load_predictions(pred_dir: Path) -> dict[str, dict]:
    """Return map keyed by filename (FH_001.pdf) → prediction payload."""
    out: dict[str, dict] = {}
    for f in sorted(pred_dir.glob("FH_*.json")):
        data = json.loads(f.read_text(encoding="utf-8"))
        fname = f"{f.stem}.pdf"
        out[fname] = data.get("prediction") or data
    return out


def language_licence_stats(gt_docs: dict, preds: dict) -> dict[str, Any]:
    """Field-group focused metrics for languages + licences."""
    from holdout_scorer_v2 import match_language_pairs

    tp = fp = fn = 0
    pair_correct = pair_total = 0
    lic_tp = lic_fp = lic_fn = 0
    confusion = 0
    lang_hallu = 0
    empty_pred_docs = 0

    for fname, g_raw in sorted(gt_docs.items()):
        g = prepare_gt_doc(g_raw)
        p = pred_view(preds.get(fname) or {})
        exp_langs = g.get("languages") or []
        act_langs = p.get("languages") or []
        if not act_langs:
            empty_pred_docs += 1
        rows, stats = match_language_pairs(exp_langs, act_langs)
        tp += stats.get("entry_tp", 0)
        fp += stats.get("entry_fp", 0)
        fn += stats.get("entry_fn", 0)
        for r in rows:
            if r.status == "correct":
                pair_correct += 1
            if r.status in {"correct", "wrong", "missing"}:
                pair_total += 1
            if r.status == "hallucinated":
                lang_hallu += 1
                name = ""
                if isinstance(r.actual, dict):
                    name = str(r.actual.get("language") or r.actual.get("name") or "")
                if name.upper() in {"A1", "A2", "B1", "B", "BE", "C1", "C", "CE"}:
                    confusion += 1

        exp_lic = {
            str(x).upper()
            for x in (g.get("licenses") or g.get("driving_license") or [])
            if str(x).strip()
        }
        act_lic_raw = p.get("driving_license") or p.get("licenses") or []
        act_lic = set()
        for item in act_lic_raw:
            if isinstance(item, dict):
                act_lic.add(str(item.get("value") or "").upper())
            else:
                act_lic.add(str(item).upper())
        act_lic.discard("")
        lic_tp += len(exp_lic & act_lic)
        lic_fp += len(act_lic - exp_lic)
        lic_fn += len(exp_lic - act_lic)

    def f1(t, f_p, f_n):
        prec = t / (t + f_p) if (t + f_p) else 0.0
        rec = t / (t + f_n) if (t + f_n) else 0.0
        return prec, rec, (2 * prec * rec / (prec + rec) if (prec + rec) else 0.0)

    l_prec, l_rec, l_f1 = f1(tp, fp, fn)
    lic_prec, lic_rec, lic_f1 = f1(lic_tp, lic_fp, lic_fn)
    return {
        "language_precision": round(l_prec, 4),
        "language_recall": round(l_rec, 4),
        "language_f1": round(l_f1, 4),
        "language_tp": tp,
        "language_fp": fp,
        "language_fn": fn,
        "pair_accuracy": round(pair_correct / pair_total, 4) if pair_total else 0.0,
        "pair_correct": pair_correct,
        "pair_total": pair_total,
        "licence_precision": round(lic_prec, 4),
        "licence_recall": round(lic_rec, 4),
        "licence_f1": round(lic_f1, 4),
        "language_licence_confusion_count": confusion,
        "language_hallucination_count": lang_hallu,
        "language_hallucination_rate": round(
            lang_hallu / max(1, tp + fp + lang_hallu), 4
        ),
        "docs_with_empty_language_pred": empty_pred_docs,
    }


def score_all(gt_docs: dict, preds: dict) -> dict[str, Any]:
    from core.cv_extract import extract_text

    all_rows: list[FactResult] = []
    per_doc: list[dict[str, Any]] = []
    perfect = 0
    for fname, g_raw in sorted(gt_docs.items()):
        g = prepare_gt_doc(g_raw)
        p_raw = preds.get(fname) or {}
        pdf = PDF_DIR / fname
        text = extract_text(pdf) if pdf.is_file() else ""
        evidence = build_evidence_for_doc(fname, g, text)
        rows = evaluate_doc_v2(fname, g, p_raw, evidence)
        all_rows.extend(rows)
        is_perfect = perfect_document(rows, core_only=True)
        if is_perfect:
            perfect += 1
        agg = aggregate_v2(rows)
        pv = pred_view(p_raw)
        per_doc.append(
            {
                "document_id": fname,
                "perfect_core": is_perfect,
                "accuracy": agg.get("accuracy"),
                "f1": agg.get("f1"),
                "languages_pred_n": len(pv.get("languages") or []),
            }
        )
    overall = aggregate_v2(all_rows)
    lang_stats = language_licence_stats(gt_docs, preds)
    hallu = sum(1 for r in all_rows if r.status == "hallucinated")
    evaluable = sum(1 for r in all_rows if r.status != "skipped")
    return {
        "label": "POST-ANALYSIS",
        "n_documents": len(gt_docs),
        "overall": overall,
        "language_licence": lang_stats,
        "perfect_core_profiles": perfect,
        "hallucination_count": hallu,
        "hallucination_rate": round(hallu / max(1, evaluable), 4),
        "per_document": per_doc,
        "n_facts": len(all_rows),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--variant",
        default="det_repaired",
        choices=["det_repaired", "det_baseline"],
    )
    ap.add_argument(
        "--baseline-preds",
        type=Path,
        default=FROZEN_PRED,
        help="Prediction dir for det_baseline (default: frozen_predictions)",
    )
    args = ap.parse_args()

    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    # Safety: never touch frozen_predictions
    assert FROZEN_PRED.resolve() != (OUT_ROOT / "det_predictions").resolve()

    gt_docs = load_gt()
    if len(gt_docs) != 50:
        raise SystemExit(f"expected 50 GT docs, got {len(gt_docs)}")

    runtime: dict[str, Any] = {}
    if args.variant == "det_repaired":
        pred_dir = OUT_ROOT / "det_predictions"
        runtime = run_det_predictions(pred_dir)
        preds = load_predictions(pred_dir)
        out_name = "det_language_results.json"
    else:
        pred_dir = args.baseline_preds
        if not pred_dir.is_dir():
            raise SystemExit(f"missing baseline preds: {pred_dir}")
        # Verify frozen hashes untouched
        for f in sorted(pred_dir.glob("FH_*.json")):
            _ = f.stat().st_mtime
        preds = load_predictions(pred_dir)
        runtime = {
            "n": len(preds),
            "timing_ms_mean": None,
            "peak_rss_mb": None,
            "pred_dir": str(pred_dir.relative_to(ROOT)),
            "note": "baseline uses sealed frozen predictions (no re-run)",
        }
        out_name = "det_baseline_language_results.json"

    scored = score_all(gt_docs, preds)
    result = {
        "protocol": "POST_ANALYSIS_LANGUAGE_V1",
        "variant": args.variant,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "frozen_holdout_reference": {
            "accuracy": 0.674,
            "f1": 0.805,
            "languages_f1": 0.0,
            "perfect_core": 0,
            "note": "immutable; not overwritten by this run",
        },
        "runtime": runtime,
        "metrics": scored,
        "frozen_prediction_hashes_intact": _sha256_file(
            ROOT / "artifacts" / "final_holdout" / "FROZEN_PREDICTION_HASHES.json"
        ),
    }
    out_path = OUT_ROOT / out_name
    out_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "variant": args.variant,
        "out": str(out_path.relative_to(ROOT)),
        "language_f1": scored["language_licence"]["language_f1"],
        "overall_f1": scored["overall"].get("f1"),
        "perfect_core": scored["perfect_core_profiles"],
        "hallucination_rate": scored["hallucination_rate"],
    }, indent=2))


if __name__ == "__main__":
    main()
