#!/usr/bin/env python3
"""Final Holdout — Phase B: evaluate sealed predictions only.

Requires Phase A seal. Must NOT re-run the parser or mutate predictions.

Usage:
  python scripts/evaluate_final_holdout.py
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

HOLDOUT = ROOT / "tests" / "final_holdout"
GT_PATH = HOLDOUT / "expected_results.json"
OUT = ROOT / "artifacts" / "final_holdout"
PRED_DIR = OUT / "frozen_predictions"
META_PATH = OUT / "FROZEN_METADATA.json"
HASHES_PATH = OUT / "FROZEN_HASHES.json"
SEAL_MARKER = OUT / "PHASE_A_COMPLETE.json"
EVAL_OUT = OUT / "EVALUATION_RESULTS.json"
EVAL_MARKER = OUT / "PHASE_B_COMPLETE.json"


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_seal() -> dict[str, Any]:
    if not SEAL_MARKER.is_file():
        raise SystemExit("Phase A not complete: missing PHASE_A_COMPLETE.json")
    if not HASHES_PATH.is_file():
        raise SystemExit("Missing FROZEN_HASHES.json — cannot evaluate")
    seal = json.loads(SEAL_MARKER.read_text(encoding="utf-8"))
    if not seal.get("phase_a_complete") or not seal.get("sealed"):
        raise SystemExit("Phase A seal invalid")
    hashes = json.loads(HASHES_PATH.read_text(encoding="utf-8"))
    mismatches = []
    for ent in hashes.get("files") or []:
        p = OUT / ent["path"]
        if not p.is_file():
            mismatches.append({"path": ent["path"], "error": "missing"})
            continue
        got = _sha256_file(p)
        if got != ent["sha256"]:
            mismatches.append(
                {
                    "path": ent["path"],
                    "error": "hash_mismatch",
                    "expected": ent["sha256"],
                    "got": got,
                }
            )
    if mismatches:
        raise SystemExit(
            "Prediction seal broken — abort evaluation:\n"
            + json.dumps(mismatches, indent=2)
        )
    return {"ok": True, "n_checked": len(hashes.get("files") or []), "seal": seal}


def load_gt() -> dict[str, Any]:
    if not GT_PATH.is_file():
        raise SystemExit(
            f"Ground truth missing: {GT_PATH}\n"
            "Provide independent expected_results.json before Phase B."
        )
    data = json.loads(GT_PATH.read_text(encoding="utf-8"))
    if "documents" in data:
        return data["documents"]
    return data


def load_preds() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for f in sorted(PRED_DIR.glob("*.json")):
        rec = json.loads(f.read_text(encoding="utf-8"))
        doc = rec.get("document") or f.name
        out[doc] = rec.get("prediction") or rec
    return out


def evaluate() -> dict[str, Any]:
    """Score with Scorer V2 when GT schema matches holdout_100; else basic report."""
    verify_seal()
    gt = load_gt()
    preds = load_preds()

    # Prefer holdout_scorer_v2 when structure is compatible
    try:
        from holdout_scorer_v2 import aggregate_v2, evaluate_doc_v2, perfect_document

        results = []
        for doc, expected in sorted(gt.items()):
            pred = preds.get(doc)
            if pred is None:
                # try stem match
                stem = Path(doc).stem
                pred = next(
                    (
                        preds[k]
                        for k in preds
                        if Path(k).stem == stem
                    ),
                    None,
                )
            if pred is None:
                results.append(
                    {
                        "document": doc,
                        "error": "missing_prediction",
                    }
                )
                continue
            # Scorer V2 expects evidence text; use empty if not provided in GT
            text = ""
            if isinstance(expected, dict):
                text = str(expected.get("_evidence_text") or expected.get("raw_text") or "")
            facts = evaluate_doc_v2(doc, expected, pred, text)
            results.append(
                {
                    "document": doc,
                    "facts": [f.__dict__ if hasattr(f, "__dict__") else f for f in facts]
                    if not isinstance(facts, dict)
                    else facts,
                    "perfect": perfect_document(facts)
                    if not isinstance(facts, dict)
                    else False,
                }
            )
        # Try aggregate if API matches
        try:
            # rebuild FactResult list path used by holdout_100 runner
            from holdout_scorer_v2 import FactResult

            all_facts: list[Any] = []
            for doc, expected in sorted(gt.items()):
                pred = preds.get(doc) or preds.get(Path(doc).name)
                if pred is None:
                    continue
                text = ""
                if isinstance(expected, dict):
                    text = str(
                        expected.get("_evidence_text") or expected.get("raw_text") or ""
                    )
                all_facts.extend(evaluate_doc_v2(doc, expected, pred, text))
            summary = aggregate_v2(all_facts)
        except Exception as exc:  # noqa: BLE001
            summary = {"aggregate_error": str(exc), "n_docs": len(results)}

        report = {
            "phase": "B",
            "scorer": "holdout_scorer_v2",
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "n_gt": len(gt),
            "n_pred": len(preds),
            "summary": summary if isinstance(summary, dict) else {"raw": str(summary)},
            "per_document": results,
            "seal_verified": True,
            "claim_language": (
                "On the independent synthetic Final-Holdout, report metrics only; "
                "do not claim unbounded global guarantees."
            ),
        }
    except Exception as exc:  # noqa: BLE001
        report = {
            "phase": "B",
            "scorer": "unavailable",
            "error": str(exc),
            "n_gt": len(gt),
            "n_pred": len(preds),
            "seal_verified": True,
            "note": "Provide GT compatible with Scorer V2 or extend this evaluator.",
        }

    EVAL_OUT.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    EVAL_MARKER.write_text(
        json.dumps(
            {
                "phase_b_complete": True,
                "evaluated_at_utc": datetime.now(timezone.utc).isoformat(),
                "results_path": str(EVAL_OUT.relative_to(ROOT)),
                "note": (
                    "This holdout is no longer 'unseen'. Further fixes make it a "
                    "regression set; a new holdout is required for independent proof."
                ),
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Phase B complete → {EVAL_OUT}")
    return report


def main() -> int:
    evaluate()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
