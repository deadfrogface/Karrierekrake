#!/usr/bin/env python3
"""DET candidate regression score across known corpora (post-analysis only).

Does NOT overwrite frozen Phase A predictions.
Writes under artifacts/det_candidate_regression/ only.
"""

from __future__ import annotations

import hashlib
import json
import resource
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from holdout_scorer_v2 import (  # noqa: E402
    aggregate_v2,
    build_evidence_for_doc,
    evaluate_doc_v2,
    perfect_document,
)
from run_final_holdout_phase_b_eval import (  # noqa: E402
    classify_critical,
    group_metrics,
    prepare_gt_for_scorer,
)
from core.cv_extract import extract_text  # noqa: E402
from core.cv_parser import import_cv  # noqa: E402

OUT = ROOT / "artifacts" / "det_candidate_regression"

CORPORA = {
    "holdout_100": {
        "pdf_dir": ROOT / "tests" / "holdout_100" / "cvs",
        "gt": ROOT / "tests" / "holdout_100" / "expected_results_full.json",
    },
    "final_holdout_50": {
        "pdf_dir": ROOT / "tests" / "final_holdout" / "phase_a_pdfs",
        "gt": ROOT
        / "tests"
        / "final_holdout"
        / "phase_b_solutions"
        / "expected_results.json",
    },
    "mini_holdout_30": {
        "pdf_dir": ROOT / "tests" / "mini_holdout_30" / "phase_a_pdfs",
        "gt": ROOT
        / "tests"
        / "mini_holdout_30"
        / "phase_b_solutions"
        / "expected_results.json",
    },
    "final_independent_50_v2": {
        "pdf_dir": ROOT / "tests" / "final_independent_50_v2" / "phase_a_pdfs",
        "gt": ROOT
        / "tests"
        / "final_independent_50_v2"
        / "phase_b_solutions"
        / "expected_results.json",
    },
}


def _peak_rss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def _score_corpus(name: str, cfg: dict[str, Path]) -> dict[str, Any]:
    gt_raw = json.loads(cfg["gt"].read_text(encoding="utf-8"))
    docs = gt_raw["documents"]
    all_rows = []
    per_doc = {}
    phi = 0
    c1 = 0
    t0 = time.perf_counter()
    for fname in sorted(docs.keys()):
        pdf = cfg["pdf_dir"] / fname
        if not pdf.is_file():
            # holdout_100 may use bare IDs
            alt = cfg["pdf_dir"] / Path(fname).name
            pdf = alt if alt.is_file() else pdf
        if not pdf.is_file():
            continue
        parsed = import_cv(pdf, guenther_enabled=False)
        phi += int(parsed.get("phi_extract_call_count") or 0)
        if parsed.get("phi_invoked"):
            phi = max(phi, 1)
        c1 += int(parsed.get("c1_extract_call_count") or 0)
        if parsed.get("c1_invoked"):
            c1 = max(c1, 1)
        g = prepare_gt_for_scorer(docs[fname])
        text = extract_text(pdf) or ""
        evidence = build_evidence_for_doc(fname, g, text)
        rows = evaluate_doc_v2(fname, g, parsed, evidence)
        all_rows.extend(rows)
        crit = classify_critical(rows)
        per_doc[fname] = {
            "perfect": perfect_document(rows),
            "perfect_core": perfect_document(rows, core_only=True),
            "n_critical": len(crit),
        }
    agg = aggregate_v2(all_rows)
    invented = [
        c
        for c in (classify_critical(all_rows) if all_rows else [])
        if c.get("status") == "hallucinated"
        and str(c.get("kind") or "").startswith("invented_")
    ]
    return {
        "corpus": name,
        "n_docs_scored": len(per_doc),
        "metrics": {
            **{k: agg[k] for k in ("f1", "precision", "recall", "hallucination_rate", "field_accuracy") if k in agg},
            "counts": agg.get("counts"),
            "perfect_documents": sum(1 for v in per_doc.values() if v["perfect"]),
            "perfect_core": sum(1 for v in per_doc.values() if v["perfect_core"]),
            "invented_critical": len(invented),
            "by_group": group_metrics(all_rows) if all_rows else {},
        },
        "performance": {
            "wall_s": time.perf_counter() - t0,
            "peak_rss_mb": _peak_rss_mb(),
            "phi_calls": phi,
            "c1_calls": c1,
        },
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    results = {
        "label": "DET_CANDIDATE_REGRESSION",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "honesty": {
            "ih2_frozen_independent": {"f1": 0.7246, "hallu": 0.0983, "perfect_core": "0/50"},
            "ih2_post_analysis_not_independent": True,
            "status": "POST-ANALYSIS TARGET ACHIEVED – INDEPENDENT 0.99 NOT YET PROVEN",
        },
        "corpora": {},
    }
    for name, cfg in CORPORA.items():
        if not cfg["gt"].is_file() or not cfg["pdf_dir"].is_dir():
            results["corpora"][name] = {"skipped": True, "reason": "missing paths"}
            continue
        print(f"scoring {name}...", flush=True)
        results["corpora"][name] = _score_corpus(name, cfg)
        m = results["corpora"][name]["metrics"]
        print(
            f"  F1={m.get('f1')} perfect_core={m.get('perfect_core')} "
            f"hallu={m.get('hallucination_rate')} phi={results['corpora'][name]['performance']['phi_calls']}",
            flush=True,
        )
    out_path = OUT / "regression_summary.json"
    out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False, default=str) + "\n")
    print("wrote", out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
