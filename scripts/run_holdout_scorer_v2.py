#!/usr/bin/env python3
"""Build evidence manifest + score frozen Holdout predictions with Scorer V2.

Never modifies frozen prediction files.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from holdout_scorer_v2 import (  # noqa: E402
    METADATA_FIELDS,
    SCHEMA_MAPPING,
    FactResult,
    aggregate_v2,
    build_evidence_for_doc,
    evaluate_doc_v2,
    perfect_document,
)
from dataclasses import asdict  # noqa: E402

HOLDOUT = ROOT / "tests" / "holdout_100"
GT_PATH = HOLDOUT / "expected_results_full.json"
PRED_ROOT = ROOT / "artifacts" / "holdout_100" / "frozen_baseline_predictions"
OUT = ROOT / "artifacts" / "holdout_100"


def load_gt() -> dict:
    return json.loads(GT_PATH.read_text(encoding="utf-8"))["documents"]


def resolve_pred_dir(name: str) -> Path:
    d = PRED_ROOT / name
    alias = d / "USE_PIPELINE.txt"
    if alias.is_file():
        return PRED_ROOT / alias.read_text(encoding="utf-8").strip()
    return d


def load_preds(name: str) -> dict[str, dict]:
    d = resolve_pred_dir(name)
    out = {}
    for f in d.glob("HO_*.json"):
        rec = json.loads(f.read_text(encoding="utf-8"))
        out[rec.get("document") or f.stem + ".pdf"] = rec
    return out


def verify_integrity(integrity_path: Path) -> dict:
    data = json.loads(integrity_path.read_text(encoding="utf-8"))
    mismatches = []
    for ent in data["files"]:
        p = ROOT / "artifacts" / "holdout_100" / ent["path"]
        if not p.is_file():
            mismatches.append({"path": ent["path"], "error": "missing"})
            continue
        h = hashlib.sha256(p.read_bytes()).hexdigest()
        if h != ent["sha256"]:
            mismatches.append({"path": ent["path"], "error": "hash_mismatch", "expected": ent["sha256"], "got": h})
    return {"ok": not mismatches, "n_checked": len(data["files"]), "mismatches": mismatches}


def build_evidence_manifest(gt: dict) -> dict:
    from core.cv_extract import extract_text

    docs = {}
    for fname, g in sorted(gt.items()):
        text = extract_text(HOLDOUT / "cvs" / fname) or ""
        docs[fname] = build_evidence_for_doc(fname, g, text)
    return {
        "schema_version": 2,
        "n_documents": len(docs),
        "documents": docs,
        "metadata_fields_excluded": sorted(METADATA_FIELDS),
    }


def score_pipeline(name: str, gt: dict, evidence: dict, preds: dict) -> dict:
    summary_path = PRED_ROOT / name / "_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else {}
    if summary.get("status") == "NOT_AVAILABLE":
        return summary
    all_rows = []
    perfect = 0
    perfect_core = 0
    per_doc = {}
    for fname, g in sorted(gt.items()):
        ev = evidence["documents"][fname]
        rec = preds.get(fname)
        pred = (rec or {}).get("prediction")
        rows = evaluate_doc_v2(fname, g, pred, ev)
        all_rows.extend(rows)
        per_doc[fname] = {
            "n": len(rows),
            "perfect": perfect_document(rows),
            "perfect_core": perfect_document(rows, core_only=True),
            "counts": {},
        }
        from collections import Counter

        c = Counter(r.status for r in rows)
        per_doc[fname]["counts"] = dict(c)
        if perfect_document(rows):
            perfect += 1
        if perfect_document(rows, core_only=True):
            perfect_core += 1
    agg = aggregate_v2(all_rows)
    agg.update(
        {
            "pipeline": name,
            "perfect_documents": perfect,
            "perfect_core_documents": perfect_core,
            "document_perfect_match_rate": perfect / max(1, len(gt)),
            "document_perfect_core_match_rate": perfect_core / max(1, len(gt)),
            "wall_s": summary.get("wall_s"),
            "avg_s": summary.get("avg_s"),
            "alias_of": summary.get("alias_of"),
            "per_document_summary": {k: v for k, v in list(per_doc.items())[:3]},  # sample only in aggregate
        }
    )
    # serialize rows sample for errors
    errors = [asdict(r) for r in all_rows if r.status != "correct"]
    return {"metrics": agg, "n_errors": len(errors), "errors": errors, "per_document": per_doc}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pipelines", default="")
    ap.add_argument("--skip-integrity", action="store_true")
    ap.add_argument("--post-analysis", action="store_true")
    args = ap.parse_args()

    integrity_path = OUT / "FROZEN_PREDICTIONS_INTEGRITY.json"
    if not args.skip_integrity and integrity_path.exists() and not args.post_analysis:
        integ = verify_integrity(integrity_path)
        (OUT / "FROZEN_PREDICTIONS_INTEGRITY_VERIFY.json").write_text(
            json.dumps(integ, indent=2), encoding="utf-8"
        )
        if not integ["ok"]:
            print("INTEGRITY FAILURE", integ["mismatches"][:5])
            return 2
        print(f"integrity OK ({integ['n_checked']} files)")

    gt = load_gt()

    # evaluation manifest (field policy)
    manifest = {
        "schema_version": 2,
        "source_gt": "tests/holdout_100/expected_results_full.json (unchanged)",
        "metadata_never_scored": sorted(METADATA_FIELDS),
        "schema_mapping": SCHEMA_MAPPING,
        "field_classes": {
            "A_CORE": [k for k, v in SCHEMA_MAPPING.items() if v["class"] == "A"],
            "B_OPTIONAL": [k for k, v in SCHEMA_MAPPING.items() if v["class"] == "B"],
            "C_METADATA": sorted(METADATA_FIELDS),
        },
        "rules": {
            "target_role": "Only if explicit Berufswunsch/Target Role label + value visible in PDF",
            "null_expected": "Absent annotation or empty → correct if prediction empty; hallucinated if invented",
            "sets": "Order-independent; language+level paired",
            "entries": "Bipartite similarity matching on company/position or qualification/institution",
        },
    }
    (HOLDOUT / "evaluation_manifest_v2.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (OUT / "schema_mapping_v2.json").write_text(
        json.dumps(SCHEMA_MAPPING, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print("Building evidence manifest (PDF text)...")
    evidence = build_evidence_manifest(gt)
    (OUT / "evidence_manifest_v2.json").write_text(
        json.dumps(evidence, ensure_ascii=False), encoding="utf-8"
    )
    n_tr = sum(1 for d in evidence["documents"].values() if d.get("target_role_evaluable"))
    print(f"target_role_evaluable docs: {n_tr}/100")

    if args.post_analysis:
        pred_root = OUT / "post_analysis_predictions"
        pipelines = ["A5_det_product_v2"] if (pred_root / "A5_det_product_v2").is_dir() else []
        results = {}
        for name in pipelines:
            # load from post_analysis path
            preds = {}
            for f in (pred_root / name).glob("HO_*.json"):
                rec = json.loads(f.read_text(encoding="utf-8"))
                preds[rec.get("document") or f.stem + ".pdf"] = rec
            # score using same evaluate but temporary PRED - inline
            all_rows = []
            perfect = perfect_core = 0
            per_doc = {}
            for fname, g in sorted(gt.items()):
                rows = evaluate_doc_v2(fname, g, (preds.get(fname) or {}).get("prediction"), evidence["documents"][fname])
                all_rows.extend(rows)
                per_doc[fname] = {"perfect": perfect_document(rows), "perfect_core": perfect_document(rows, core_only=True)}
                if perfect_document(rows):
                    perfect += 1
                if perfect_document(rows, core_only=True):
                    perfect_core += 1
            agg = aggregate_v2(all_rows)
            agg.update(
                {
                    "pipeline": name,
                    "perfect_documents": perfect,
                    "perfect_core_documents": perfect_core,
                    "document_perfect_match_rate": perfect / 100,
                    "document_perfect_core_match_rate": perfect_core / 100,
                }
            )
            results[name] = {"metrics": agg, "n_errors": sum(1 for r in all_rows if r.status != "correct")}
            m = agg
            print(
                f"{name}: acc={m['field_accuracy']:.4f} P={m['precision']:.4f} R={m['recall']:.4f} "
                f"F1={m['f1']:.4f} hallu={m['hallucination_rate']:.4f} "
                f"perfect={perfect}/100 core_perfect={perfect_core}/100"
            )
        (OUT / "scorer_v2_post_analysis_results.json").write_text(
            json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return 0

    pipelines = []
    for p in sorted(PRED_ROOT.iterdir()):
        if p.is_dir() and (p / "_summary.json").exists() and not p.name.startswith("_"):
            pipelines.append(p.name)
    if args.pipelines:
        pipelines = [x.strip() for x in args.pipelines.split(",") if x.strip()]

    results = {}
    for name in pipelines:
        preds = load_preds(name)
        if not preds and (PRED_ROOT / name / "_summary.json").exists():
            s = json.loads((PRED_ROOT / name / "_summary.json").read_text())
            if s.get("status") == "NOT_AVAILABLE" or s.get("alias_of"):
                # alias: load from alias
                if s.get("alias_of"):
                    preds = load_preds(s["alias_of"])
                else:
                    results[name] = s
                    print(f"{name}: NOT_AVAILABLE")
                    continue
        print(f"Scoring {name} ({len(preds)} preds)...")
        results[name] = score_pipeline(name, gt, evidence, preds)
        m = results[name]["metrics"]
        print(
            f"  acc={m['field_accuracy']:.4f} P={m['precision']:.4f} R={m['recall']:.4f} "
            f"F1={m['f1']:.4f} hallu={m['hallucination_rate']:.4f} "
            f"perfect={m['perfect_documents']}/100 core={m['perfect_core_documents']}/100 avg_s={m.get('avg_s')}"
        )

    (OUT / "scorer_v2_frozen_results.json").write_text(
        json.dumps(
            {k: {"metrics": v.get("metrics", v), "n_errors": v.get("n_errors")} for k, v in results.items()},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    # full errors separately (large)
    (OUT / "scorer_v2_frozen_errors.json").write_text(
        json.dumps({k: v.get("errors", []) for k, v in results.items() if "errors" in v}, ensure_ascii=False),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    # need asdict export
    raise SystemExit(main())
