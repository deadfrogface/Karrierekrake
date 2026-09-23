#!/usr/bin/env python3
"""Post-analysis re-import + Scorer V2 for Final Independent 50 V2.

Does NOT overwrite Phase A frozen predictions or Phase B frozen results.
Writes under artifacts/final_independent_50_v2/post_analysis/ only.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from collections import Counter, defaultdict
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
)
from run_final_holdout_phase_b_eval import (  # noqa: E402
    classify_critical,
    error_bucket,
    group_metrics,
    prepare_gt_for_scorer,
)
from core.cv_extract import extract_text  # noqa: E402
from core.cv_parser import import_cv  # noqa: E402

PDF_DIR = ROOT / "tests" / "final_independent_50_v2" / "phase_a_pdfs"
GT_PATH = (
    ROOT
    / "tests"
    / "final_independent_50_v2"
    / "phase_b_solutions"
    / "expected_results.json"
)
OUT = ROOT / "artifacts" / "final_independent_50_v2" / "post_analysis"
PREFIX = "IH2_"
N = 50


def _git() -> str:
    import subprocess

    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
    except Exception:  # noqa: BLE001
        return ""


def main() -> int:
    gt_raw = json.loads(GT_PATH.read_text(encoding="utf-8"))
    docs = gt_raw["documents"]
    OUT.mkdir(parents=True, exist_ok=True)
    pred_dir = OUT / "det_predictions"
    pred_dir.mkdir(parents=True, exist_ok=True)

    all_rows: list[FactResult] = []
    per_doc: dict[str, Any] = {}
    critical_all: list[dict[str, Any]] = []
    error_inventory: list[dict[str, Any]] = []
    phi = 0
    t0 = time.perf_counter()

    for i in range(1, N + 1):
        doc_id = f"{PREFIX}{i:03d}"
        fname = f"{doc_id}.pdf"
        pdf = PDF_DIR / fname
        parsed = import_cv(pdf, guenther_enabled=False)
        phi += int(parsed.get("phi_extract_call_count") or 0)
        if parsed.get("phi_invoked"):
            phi = max(phi, 1)
        pred_path = pred_dir / f"{doc_id}.json"
        pred_path.write_text(
            json.dumps(parsed, ensure_ascii=False, indent=2, sort_keys=True, default=str)
            + "\n",
            encoding="utf-8",
        )

        g = prepare_gt_for_scorer(docs[fname])
        text = extract_text(pdf) or ""
        evidence = build_evidence_for_doc(fname, g, text)
        rows = evaluate_doc_v2(fname, g, parsed, evidence)
        all_rows.extend(rows)
        crit = classify_critical(rows)
        critical_all.extend(crit)
        errs = [r for r in rows if r.status not in {"correct", "skipped"}]
        per_doc[fname] = {
            "perfect": perfect_document(rows),
            "perfect_core": perfect_document(rows, core_only=True),
            "n_errors": len(errs),
            "error_bucket": error_bucket(len(errs)),
            "n_critical": len(crit),
        }
        for r in errs:
            error_inventory.append(
                {
                    "document": fname,
                    "field": r.field,
                    "group": r.group,
                    "status": r.status,
                    "expected": r.expected,
                    "actual": r.actual,
                }
            )

    agg = aggregate_v2(all_rows)
    field_group = group_metrics(all_rows)
    invented = [
        c
        for c in critical_all
        if c["status"] == "hallucinated"
        and str(c.get("kind") or "").startswith("invented_")
    ]
    wall = time.perf_counter() - t0
    result = {
        "label": "POST-ANALYSIS",
        "dataset": "FINAL_INDEPENDENT_50_V2",
        "commit": _git(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "frozen_reference": {
            "f1": 0.7246,
            "hallucination_rate": 0.0983,
            "perfect_core": 0,
            "immutable": True,
        },
        "metrics": {
            **agg,
            "perfect_documents": sum(1 for v in per_doc.values() if v["perfect"]),
            "perfect_core": sum(1 for v in per_doc.values() if v["perfect_core"]),
            "invented_critical": len(invented),
            "documents_with_critical": len({c["document"] for c in invented}),
            "by_group": field_group,
        },
        "performance": {"wall_s": wall, "phi_calls": phi, "n": N},
        "gt_sha256": hashlib.sha256(GT_PATH.read_bytes()).hexdigest(),
    }
    (OUT / "final_metrics.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    (OUT / "per_document_results.json").write_text(
        json.dumps(per_doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (OUT / "error_inventory.json").write_text(
        json.dumps(error_inventory, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    (OUT / "critical_errors.json").write_text(
        json.dumps(
            {
                "n_invented": len(invented),
                "kinds": dict(Counter(c["kind"] for c in invented)),
                "events": invented[:300],
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "f1": round(agg["f1"], 4),
                "acc": round(agg["field_accuracy"], 4),
                "precision": round(agg["precision"], 4),
                "recall": round(agg["recall"], 4),
                "hallu": round(agg["hallucination_rate"], 4),
                "perfect_core": result["metrics"]["perfect_core"],
                "perfect": result["metrics"]["perfect_documents"],
                "invented_critical": len(invented),
                "phi": phi,
                "groups": {
                    k: {
                        "f1": round(v["f1"], 4),
                        "hallu": round(v["hallucination_rate"], 4),
                        "recall": round(v["recall"], 4),
                    }
                    for k, v in field_group.items()
                },
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
