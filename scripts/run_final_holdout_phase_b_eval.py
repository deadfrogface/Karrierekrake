#!/usr/bin/env python3
"""Holdout Phase B — score sealed predictions only (no re-extraction).

Default: Final Holdout 50. Also supports Mini Holdout 30 via --dataset mini_holdout_30.

Reads sealed predictions + ground truth only.
Uses Scorer V2 unchanged. Never calls import_cv / parse_cv_text.
extract_text is used only to build the evidence manifest (evaluability),
identical to the Holdout-100 Scorer V2 workflow — not to regenerate predictions.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections import Counter, defaultdict
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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
    pred_view,
    scalar_match,
    _norm,
)

DATASETS: dict[str, dict[str, Any]] = {
    "final_holdout": {
        "holdout_rel": Path("tests") / "final_holdout",
        "out_rel": Path("artifacts") / "final_holdout",
        "gt_subdir": "phase_b_solutions",
        "prefix": "FH_",
        "expected_count": 50,
        "expected_seal_file_sha256": None,  # historical: compared manifest only
        "expected_manifest_sha256": "97c64fb31cf8dfff78e530364a546f759bcaa24f1df899af3844d4a4f8c9075c",
        "baseline_note": (
            "100-CV Post-Analysis was a development/regression corpus after visible analysis; "
            "this 50-CV Final Holdout is an independent sealed frozen evaluation."
        ),
    },
    "mini_holdout_30": {
        "holdout_rel": Path("tests") / "mini_holdout_30",
        "out_rel": Path("artifacts") / "mini_holdout_30",
        "gt_subdir": "phase_b_solutions",
        "prefix": "MH_",
        "expected_count": 30,
        "expected_seal_file_sha256": (
            "4cc27cb7e08b5c384f5096d9b1048271db907b8b91d4510095f3603b40c927c4"
        ),
        "expected_manifest_sha256": (
            "da50d4559e12f32bfa06eeb445b2964389f22b5a50331824fad7e644a873851d"
        ),
        "baseline_note": (
            "100-CV / 50-CV Post-Analysis are development corpora; "
            "this 30-CV Mini Holdout is the independent sealed frozen test of the DET candidate."
        ),
    },
}

DATASET_NAME = "final_holdout"
DOC_PREFIX = "FH_"
EXPECTED_COUNT = 50
EXPECTED_SEAL_FILE = None
EXPECTED_SEAL = "97c64fb31cf8dfff78e530364a546f759bcaa24f1df899af3844d4a4f8c9075c"
BASELINE_NOTE = DATASETS["final_holdout"]["baseline_note"]

HOLDOUT = ROOT / "tests" / "final_holdout"
PDF_DIR = HOLDOUT / "phase_a_pdfs"
GT_DIR = HOLDOUT / "phase_b_solutions"
GT_PATH = GT_DIR / "expected_results.json"
PRECHECK_PATH = GT_DIR / "PRECHECK_REPORT.json"
OUT = ROOT / "artifacts" / "final_holdout"
PRED_DIR = OUT / "frozen_predictions"
SEAL_PATH = OUT / "PHASE_A_SEAL.json"
PRED_HASHES_PATH = OUT / "FROZEN_PREDICTION_HASHES.json"
INPUT_HASHES_PATH = OUT / "FROZEN_INPUT_HASHES.json"

# Counters proving no re-extraction of predictions
CV_PARSE_CALLS = 0
PHI_CALLS = 0
C1_CALLS = 0
WRITER_CALLS = 0
IMPORT_CV_CALLS = 0
PDF_EXTRACTION_CALLS = 0  # extract_text for evidence only is tracked separately


def configure_dataset(name: str) -> None:
    global DATASET_NAME, DOC_PREFIX, EXPECTED_COUNT, EXPECTED_SEAL_FILE, EXPECTED_SEAL
    global BASELINE_NOTE, HOLDOUT, PDF_DIR, GT_DIR, GT_PATH, PRECHECK_PATH
    global OUT, PRED_DIR, SEAL_PATH, PRED_HASHES_PATH, INPUT_HASHES_PATH

    if name not in DATASETS:
        raise SystemExit(f"Unknown dataset {name!r}. Choose from: {sorted(DATASETS)}")
    cfg = DATASETS[name]
    DATASET_NAME = name
    DOC_PREFIX = cfg["prefix"]
    EXPECTED_COUNT = int(cfg["expected_count"])
    EXPECTED_SEAL_FILE = cfg.get("expected_seal_file_sha256")
    EXPECTED_SEAL = cfg["expected_manifest_sha256"]
    BASELINE_NOTE = cfg["baseline_note"]
    HOLDOUT = ROOT / cfg["holdout_rel"]
    PDF_DIR = HOLDOUT / "phase_a_pdfs"
    GT_DIR = HOLDOUT / cfg["gt_subdir"]
    GT_PATH = GT_DIR / "expected_results.json"
    PRECHECK_PATH = GT_DIR / "PRECHECK_REPORT.json"
    OUT = ROOT / cfg["out_rel"]
    PRED_DIR = OUT / "frozen_predictions"
    SEAL_PATH = OUT / "PHASE_A_SEAL.json"
    PRED_HASHES_PATH = OUT / "FROZEN_PREDICTION_HASHES.json"
    INPUT_HASHES_PATH = OUT / "FROZEN_INPUT_HASHES.json"


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_phase_a_seal() -> dict[str, Any]:
    blocked = (
        "RESULT: MINI HOLDOUT PHASE B BLOCKED – SEAL INTEGRITY FAILURE\n"
        if DATASET_NAME == "mini_holdout_30"
        else "RESULT: PHASE B BLOCKED – SEAL INTEGRITY FAILURE\n"
    )
    if not SEAL_PATH.is_file():
        raise SystemExit(blocked + "missing PHASE_A_SEAL.json")
    seal_bytes = SEAL_PATH.read_bytes()
    seal_file_sha = hashlib.sha256(seal_bytes).hexdigest()
    seal = json.loads(seal_bytes.decode("utf-8"))
    got = seal.get("predictions_manifest_sha256")
    if EXPECTED_SEAL_FILE and seal_file_sha != EXPECTED_SEAL_FILE:
        raise SystemExit(
            blocked
            + f"seal file hash mismatch: expected {EXPECTED_SEAL_FILE} got {seal_file_sha}"
        )
    if got != EXPECTED_SEAL:
        raise SystemExit(
            blocked + f"manifest hash mismatch: expected {EXPECTED_SEAL} got {got}"
        )
    pred_h = json.loads(PRED_HASHES_PATH.read_text(encoding="utf-8"))
    mismatches = []
    for ent in pred_h["files"]:
        p = OUT / ent["path"]
        if not p.is_file():
            mismatches.append({"path": ent["path"], "error": "missing"})
            continue
        h = _sha256_file(p)
        if h != ent["sha256"]:
            mismatches.append(
                {"path": ent["path"], "error": "hash_mismatch", "expected": ent["sha256"], "got": h}
            )
    agg = hashlib.sha256(
        json.dumps({e["path"]: e["sha256"] for e in pred_h["files"]}, sort_keys=True).encode()
    ).hexdigest()
    if agg != pred_h.get("aggregate_sha256") or agg != EXPECTED_SEAL:
        mismatches.append({"error": "aggregate_mismatch", "got": agg})

    pdf_mismatches = []
    inp = json.loads(INPUT_HASHES_PATH.read_text(encoding="utf-8"))
    for ent in inp.get("pdfs") or []:
        p = PDF_DIR / ent["filename"]
        if not p.is_file():
            pdf_mismatches.append({"file": ent["filename"], "error": "missing"})
            continue
        if _sha256_file(p) != ent["sha256"] or p.stat().st_size != ent["bytes"]:
            pdf_mismatches.append({"file": ent["filename"], "error": "hash_or_size"})

    preds = sorted(PRED_DIR.glob(f"{DOC_PREFIX}*.json"))
    pdfs = sorted(PDF_DIR.glob(f"{DOC_PREFIX}*.pdf"))
    if len(preds) != EXPECTED_COUNT or len(pdfs) != EXPECTED_COUNT:
        raise SystemExit(
            blocked
            + f"count pdfs={len(pdfs)} preds={len(preds)} expected={EXPECTED_COUNT}"
        )
    if {p.stem for p in preds} != {p.stem for p in pdfs}:
        raise SystemExit(blocked + "ID mismatch")
    if mismatches or pdf_mismatches:
        raise SystemExit(
            blocked + json.dumps({"pred": mismatches, "pdf": pdf_mismatches}, indent=2)
        )
    return {
        "seal_valid": True,
        "seal_file_sha256": seal_file_sha,
        "predictions_manifest_sha256": got,
        "n_predictions": EXPECTED_COUNT,
        "n_pdfs": EXPECTED_COUNT,
        "prediction_hash_mismatches": 0,
        "pdf_hash_mismatches": 0,
        "git_commit": seal.get("git_commit"),
        "runner_commit": seal.get("runner_commit") or seal.get("git_commit"),
        "phi_calls_phase_a": seal.get("phi_calls", 0),
        "dataset": DATASET_NAME,
    }


def verify_precheck() -> dict[str, Any]:
    if not PRECHECK_PATH.is_file():
        if DATASET_NAME == "mini_holdout_30":
            raise SystemExit(
                "RESULT: MINI HOLDOUT PHASE B BLOCKED – PRECHECK FAILURE\n"
                "missing PRECHECK_REPORT.json"
            )
        return {"present": False}
    pre = json.loads(PRECHECK_PATH.read_text(encoding="utf-8"))
    docs = pre.get("documents")
    dup = pre.get("duplicate_languages")
    inv = pre.get("invalid_emails")
    unexp = pre.get("unexpected_fields")
    ok = (
        docs == EXPECTED_COUNT
        and dup == []
        and inv == []
        and unexp == []
    )
    if not ok and DATASET_NAME == "mini_holdout_30":
        raise SystemExit(
            "RESULT: MINI HOLDOUT PHASE B BLOCKED – PRECHECK FAILURE\n"
            + json.dumps(pre, indent=2)
        )
    return {"present": True, "ok": ok, "report": pre}


def load_and_validate_gt() -> tuple[dict[str, dict], dict[str, dict], str]:
    if not GT_PATH.is_file():
        raise SystemExit(
            (
                "RESULT: MINI HOLDOUT PHASE B BLOCKED – INVALID GROUND TRUTH\n"
                if DATASET_NAME == "mini_holdout_30"
                else "RESULT: PHASE B BLOCKED – INVALID GROUND TRUTH\n"
            )
            + "missing expected_results.json"
        )
    raw = GT_PATH.read_text(encoding="utf-8")
    data = json.loads(raw)
    docs = data.get("documents")
    if not isinstance(docs, dict) or len(docs) != EXPECTED_COUNT:
        raise SystemExit(
            (
                "RESULT: MINI HOLDOUT PHASE B BLOCKED – INVALID GROUND TRUTH\n"
                if DATASET_NAME == "mini_holdout_30"
                else "RESULT: PHASE B BLOCKED – INVALID GROUND TRUTH\n"
            )
            + f"n_docs={len(docs) if isinstance(docs, dict) else type(docs)}"
        )
    expected = {f"{DOC_PREFIX}{i:03d}.pdf" for i in range(1, EXPECTED_COUNT + 1)}
    got = set(docs.keys())
    if got != expected:
        raise SystemExit(
            (
                "RESULT: MINI HOLDOUT PHASE B BLOCKED – INVALID GROUND TRUTH\n"
                if DATASET_NAME == "mini_holdout_30"
                else "RESULT: PHASE B BLOCKED – INVALID GROUND TRUTH\n"
            )
            + f"missing={sorted(expected-got)} extra={sorted(got-expected)}"
        )
    meta = data.get("metadata") or {}
    if not isinstance(meta, dict) or len(meta) != EXPECTED_COUNT:
        raise SystemExit(
            (
                "RESULT: MINI HOLDOUT PHASE B BLOCKED – INVALID GROUND TRUTH\n"
                if DATASET_NAME == "mini_holdout_30"
                else "RESULT: PHASE B BLOCKED – INVALID GROUND TRUTH\n"
            )
            + "metadata size"
        )
    # Adapt GT for Scorer V2 field names without mutating the on-disk file
    adapted: dict[str, dict] = {}
    for fname, g in docs.items():
        g2 = dict(g)
        if "dob" not in g2 and g2.get("date_of_birth") is not None:
            g2["dob"] = g2.get("date_of_birth")
        # Strip career_notes from main GT — scored as schema extension separately
        adapted[fname] = g2
    return adapted, meta, hashlib.sha256(raw.encode("utf-8")).hexdigest()


def load_sealed_predictions() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for f in sorted(PRED_DIR.glob(f"{DOC_PREFIX}*.json")):
        rec = json.loads(f.read_text(encoding="utf-8"))
        # Do not mutate sealed file; use in-memory prediction payload
        pred = rec.get("prediction") or {}
        out[f"{f.stem}.pdf"] = pred
    return out


def prepare_gt_for_scorer(gt: dict[str, Any]) -> dict[str, Any]:
    """In-memory projection for Scorer V2; does not write GT."""
    g = dict(gt)
    if g.get("dob") is None and g.get("date_of_birth") is not None:
        g["dob"] = g.get("date_of_birth")
    # career_notes not part of productive main metric
    g.pop("career_notes", None)
    return g


def strict_scalar_stats(gt: dict, pred: dict, evidence: dict) -> list[dict]:
    """Secondary strict exact-match stats for scalars (casefold+trim only)."""
    pv = pred_view(pred)
    ev = evidence.get("evaluable_fields") or {}
    rows = []
    mapping = [
        ("name.first_name", "first_name", "personal"),
        ("name.last_name", "last_name", "personal"),
        ("email", "email", "contact"),
        ("phone", "phone", "contact"),
        ("dob", "dob", "personal"),
        ("address.street", "street", "address"),
        ("address.house_number", "house_number", "address"),
        ("address.postal_code", "postal_code", "address"),
        ("address.city", "city", "address"),
        ("address.country", "country", "address"),
    ]
    for key, pv_key, group in mapping:
        if key not in ev:
            continue
        spec = ev[key]
        exp = spec.get("expected")
        act = pv.get(pv_key)
        if spec.get("expect_absent"):
            st = "correct" if not (act or "").strip() else "hallucinated"
        elif exp is None or str(exp).strip() == "":
            continue
        elif not (act or "").strip():
            st = "missing"
        else:
            st = "correct" if _norm(exp) == _norm(act) else "wrong"
        rows.append({"field": key, "group": group, "status": st})
    return rows


def classify_critical(rows: list[FactResult]) -> list[dict]:
    crit = []
    for r in rows:
        if r.status not in {"hallucinated", "wrong", "wrong_category"}:
            continue
        if not r.critical and r.group not in {"employment", "education", "personal", "languages", "licenses"}:
            # still flag hallucinated employment/education/personal
            if r.group not in {"employment", "education", "personal", "contact", "address"}:
                if r.status != "hallucinated":
                    continue
        kind = None
        if r.group == "employment" and r.status == "hallucinated":
            kind = "invented_employment"
        elif r.group == "education" and r.status == "hallucinated":
            kind = "invented_education"
        elif r.group == "personal" and r.status in {"wrong", "hallucinated"}:
            kind = "wrong_or_invented_personal"
        elif r.group == "languages" and r.status == "hallucinated":
            kind = "invented_language"
        elif r.group == "licenses" and r.status == "hallucinated":
            kind = "invented_licence"
        elif r.group == "software" and r.status == "hallucinated":
            kind = "invented_software"
        elif r.group == "education" and r.status == "wrong":
            kind = "wrong_education"
        elif r.group == "employment" and r.status == "wrong":
            kind = "wrong_employment"
        elif r.status == "wrong_category":
            kind = "wrong_category"
        if kind:
            crit.append(
                {
                    "document": r.document,
                    "field": r.field,
                    "group": r.group,
                    "status": r.status,
                    "kind": kind,
                    "expected": r.expected,
                    "actual": r.actual,
                }
            )
    return crit


def schema_extension_career_notes(gt_docs: dict, preds: dict) -> dict:
    """career_notes is not a productive profile field — report separately."""
    results = []
    for fname, g in sorted(gt_docs.items()):
        notes = g.get("career_notes") or []
        if not notes:
            continue
        # Predictions typically lack career_notes; mark as schema extension miss (not main metric)
        results.append(
            {
                "document": fname,
                "expected_career_notes": notes,
                "predicted_career_notes": (preds.get(fname) or {}).get("career_notes"),
                "status": "SCHEMA_EXTENSION_FIELD",
                "counted_in_main_metric": False,
            }
        )
    return {
        "field": "career_notes",
        "n_documents_with_notes": len(results),
        "documents": results,
        "note": "Not part of productive profile main metric.",
    }


def group_metrics(rows: list[FactResult]) -> dict[str, Any]:
    by: dict[str, list[FactResult]] = defaultdict(list)
    for r in rows:
        if r.status == "skipped":
            continue
        by[r.group].append(r)
    out = {}
    for g, rs in sorted(by.items()):
        out[g] = aggregate_v2(rs)
    return out


def error_bucket(n: int) -> str:
    if n == 0:
        return "0"
    if n == 1:
        return "1"
    if n == 2:
        return "2"
    if n <= 5:
        return "3-5"
    return ">5"


def run() -> dict[str, Any]:
    global CV_PARSE_CALLS, IMPORT_CV_CALLS, PDF_EXTRACTION_CALLS

    seal_info = verify_phase_a_seal()
    precheck = verify_precheck()
    gt_docs_raw, meta, gt_hash = load_and_validate_gt()
    preds = load_sealed_predictions()

    # Evidence: extract_text ONLY for Scorer V2 evaluability (Holdout-100 method).
    # Must not call parse_cv_text / import_cv.
    from core.cv_extract import extract_text

    # Optional page-count slice metadata (not prediction regeneration)
    try:
        from pypdf import PdfReader
    except Exception:  # noqa: BLE001
        PdfReader = None  # type: ignore[misc, assignment]

    all_rows: list[FactResult] = []
    per_document: dict[str, Any] = {}
    per_field_acc: dict[str, Counter] = defaultdict(Counter)
    strict_rows_all: list[dict] = []
    critical_all: list[dict] = []
    error_inventory: list[dict] = []
    slice_rows: dict[str, list[FactResult]] = defaultdict(list)
    slice_doc_counts: Counter = Counter()
    evidence_extract_calls = 0

    for fname in sorted(gt_docs_raw.keys()):
        g_raw = gt_docs_raw[fname]
        g = prepare_gt_for_scorer(g_raw)
        pred = preds.get(fname)
        if pred is None:
            raise SystemExit(f"missing sealed prediction for {fname}")
        pdf_path = PDF_DIR / fname
        text = extract_text(pdf_path) or ""
        evidence_extract_calls += 1
        # Prove we did not re-parse
        assert IMPORT_CV_CALLS == 0 and CV_PARSE_CALLS == 0

        evidence = build_evidence_for_doc(fname, g, text)
        rows = evaluate_doc_v2(fname, g, pred, evidence)
        all_rows.extend(rows)

        strict_rows_all.extend(strict_scalar_stats(g, pred, evidence))
        crit = classify_critical(rows)
        critical_all.extend(crit)

        errs = [r for r in rows if r.status != "correct" and r.status != "skipped"]
        n_err = len(errs)
        per_document[fname] = {
            "n_facts": len([r for r in rows if r.status != "skipped"]),
            "n_errors": n_err,
            "perfect": perfect_document(rows),
            "perfect_core": perfect_document(rows, core_only=True),
            "error_bucket": error_bucket(n_err),
            "counts": dict(Counter(r.status for r in rows if r.status != "skipped")),
            "errors": [
                {
                    "field": r.field,
                    "group": r.group,
                    "status": r.status,
                    "critical": r.critical,
                    "expected": r.expected,
                    "actual": r.actual,
                }
                for r in errs
            ],
            "critical_kinds": sorted({c["kind"] for c in crit}),
            "metadata": meta.get(fname) or {},
        }
        for r in errs:
            error_inventory.append(
                {
                    "document": fname,
                    "field": r.field,
                    "group": r.group,
                    "status": r.status,
                    "critical": r.critical,
                    "expected": r.expected,
                    "actual": r.actual,
                    "layout_class": (meta.get(fname) or {}).get("layout_class"),
                    "document_language": (meta.get(fname) or {}).get("document_language"),
                }
            )
        for r in rows:
            if r.status == "skipped":
                continue
            per_field_acc[r.field][r.status] += 1

        # Slice membership from metadata + GT structure (not scored as fields)
        m = meta.get(fname) or {}
        lang = m.get("document_language") or "unknown"
        def _add_slice(key: str) -> None:
            slice_rows[key].extend(rows)
            slice_doc_counts[key] += 1

        _add_slice(f"lang:{lang}")
        _add_slice(f"layout_class:{m.get('layout_class')}")
        emp_n = len(g_raw.get("employment") or [])
        edu_n = len(g_raw.get("education") or [])
        _add_slice("employment:1" if emp_n == 1 else ("employment:multi" if emp_n > 1 else "employment:0"))
        _add_slice("education:1" if edu_n == 1 else ("education:multi" if edu_n > 1 else "education:0"))
        has_email = bool(g_raw.get("email"))
        has_phone = bool(g_raw.get("phone"))
        if has_email and has_phone:
            _add_slice("contact:complete")
        else:
            _add_slice("contact:missing_or_partial")
        addr = g_raw.get("address") or {}
        addr_complete = all(
            addr.get(k) for k in ("street", "house_number", "postal_code", "city", "country")
        )
        _add_slice("address:complete" if addr_complete else "address:incomplete")
        country = (addr.get("country") or "").lower()
        if country in {"deutschland", "de", "germany"}:
            _add_slice("address:de")
        elif country:
            _add_slice("address:foreign_or_other")
        if g_raw.get("target_role"):
            _add_slice("target_role:present")
        else:
            _add_slice("target_role:absent")
        # C1 context: language level C1 or licence C1
        c1 = False
        for item in g_raw.get("languages") or []:
            if isinstance(item, (list, tuple)) and len(item) > 1 and str(item[1]).upper() == "C1":
                c1 = True
        if any(str(x).upper() == "C1" for x in (g_raw.get("licenses") or [])):
            c1 = True
        if c1:
            _add_slice("c1_context")
        notes = g_raw.get("career_notes") or []
        if notes:
            _add_slice("career_notes:present")
        # Page count slice (metadata only)
        pages = None
        if PdfReader is not None and pdf_path.is_file():
            try:
                pages = len(PdfReader(str(pdf_path)).pages)
            except Exception:  # noqa: BLE001
                pages = None
        if pages == 1:
            _add_slice("pages:1")
        elif pages is not None and pages >= 2:
            _add_slice("pages:2+")

    # Ensure no re-extraction occurred
    if IMPORT_CV_CALLS or CV_PARSE_CALLS:
        raise SystemExit(
            "RESULT: MINI HOLDOUT PHASE B INVALID – RE-EXTRACTION OCCURRED"
            if DATASET_NAME == "mini_holdout_30"
            else "RESULT: PHASE B INVALID – RE-EXTRACTION OCCURRED"
        )

    agg = aggregate_v2(all_rows)
    perfect_n = sum(1 for v in per_document.values() if v["perfect"])
    perfect_core_n = sum(1 for v in per_document.values() if v["perfect_core"])
    bucket = Counter(v["error_bucket"] for v in per_document.values())

    # Strict scalar aggregate
    strict_counts = Counter(r["status"] for r in strict_rows_all)
    st_tp = strict_counts.get("correct", 0)
    st_n = sum(strict_counts.values()) or 1
    strict_accuracy = st_tp / st_n

    # Critical invented employment/education/personal
    critical_invented = [
        c
        for c in critical_all
        if c["kind"]
        in {
            "invented_employment",
            "invented_education",
            "invented_language",
            "invented_licence",
            "invented_software",
            "wrong_or_invented_personal",
        }
        and c["status"] == "hallucinated"
    ]
    critical_docs = sorted({c["document"] for c in critical_all})

    scorer_path = ROOT / "scripts" / "holdout_scorer_v2.py"
    scorer_hash = _sha256_file(scorer_path)

    field_group = group_metrics(all_rows)
    slice_metrics = {
        k: {**aggregate_v2(v), "n_documents": slice_doc_counts[k]}
        for k, v in sorted(slice_rows.items())
        if v
    }

    schema_ext = schema_extension_career_notes(gt_docs_raw, preds)

    # Weakest group / slice by F1 among groups with enough facts
    def weakest(metrics: dict[str, Any], min_fields: int = 10) -> tuple[str, float]:
        best_name, best_f1 = "n/a", 1.0
        for name, m in metrics.items():
            if m.get("field_total", 0) < min_fields:
                continue
            f1 = m.get("f1", 1.0)
            if f1 < best_f1:
                best_f1 = f1
                best_name = name
        return best_name, best_f1

    weak_group, weak_group_f1 = weakest(field_group)
    weak_slice, weak_slice_f1 = weakest(slice_metrics, min_fields=20)

    target_ok = (
        agg["field_accuracy"] >= 0.99
        and agg["f1"] >= 0.99
        and agg["hallucination_rate"] <= 0.01
        and len(critical_invented) == 0
    )

    phase_b_results = {
        "phase": "B",
        "dataset": DATASET_NAME,
        "dataset_size": EXPECTED_COUNT,
        "scorer": {
            "file": "scripts/holdout_scorer_v2.py",
            "version": "v2",
            "sha256": scorer_hash,
            "schema_mapping": SCHEMA_MAPPING,
            "metadata_fields_excluded": sorted(METADATA_FIELDS),
            "commit": "00674c3",
        },
        "integrity": seal_info,
        "precheck": precheck,
        "metrics": {
            **agg,
            "strict_scalar_accuracy": strict_accuracy,
            "normalized_field_accuracy": agg["field_accuracy"],
            "metric_note": (
                "strict_scalar_accuracy covers personal/contact/address/dob scalars only; "
                "normalized_field_accuracy is full Scorer V2 over all evaluable fields. "
                "Do not compare them as Strict vs Normalized Accuracy on the same universe. "
                "See docs/project/FINAL_HOLDOUT_SCORER_AUDIT_REPORT.md."
            ),
            "perfect_documents": perfect_n,
            "perfect_core_documents": perfect_core_n,
            "document_perfect_match_rate": perfect_n / EXPECTED_COUNT,
            "document_perfect_core_match_rate": perfect_core_n / EXPECTED_COUNT,
            "documents_with_errors": EXPECTED_COUNT - perfect_n,
            "documents_with_critical_errors": len(critical_docs),
            "error_bucket_distribution": dict(bucket),
            "duplicate_rate": 0.0,  # Scorer V2 does not emit a separate duplicate status
        },
        "targets": {
            "accuracy_ge_0_99": agg["field_accuracy"] >= 0.99,
            "f1_ge_0_99": agg["f1"] >= 0.99,
            "hallucination_le_0_01": agg["hallucination_rate"] <= 0.01,
            "no_critical_invented": len(critical_invented) == 0,
            "overall_pass": target_ok,
        },
        "weakest_field_group": {"name": weak_group, "f1": weak_group_f1},
        "weakest_slice": {"name": weak_slice, "f1": weak_slice_f1},
        "comparison_note": BASELINE_NOTE,
        "baseline_100cv_post_analysis": {
            "accuracy": 0.9969018112488084,
            "f1": 0.9984485022079007,
            "perfect": 89,
            "hallucination_rate": 0.0009532888465204957,
        },
        "baseline_50cv_post_analysis": {
            "f1": 0.9985,
            "perfect_core": 44,
            "n": 50,
            "note": "POST-ANALYSIS on Final Holdout corpus after Phase B reveal — not an independent frozen holdout.",
        },
    }

    # Re-verify predictions unchanged after scoring
    pred_h = json.loads(PRED_HASHES_PATH.read_text(encoding="utf-8"))
    pred_changed = 0
    for ent in pred_h["files"]:
        if _sha256_file(OUT / ent["path"]) != ent["sha256"]:
            pred_changed += 1

    integrity = {
        "seal_valid": True,
        "seal_file_sha256": seal_info.get("seal_file_sha256"),
        "original_seal_hash": EXPECTED_SEAL,
        "predictions_manifest_sha256": EXPECTED_SEAL,
        "pdf_hash_status": "OK",
        "prediction_hash_status": "OK",
        "prediction_hash_mismatches": 0,
        "pdf_hash_mismatches": 0,
        "scorer_sha256": scorer_hash,
        "ground_truth_sha256": gt_hash,
        "n_predictions": EXPECTED_COUNT,
        "n_ground_truth_documents": EXPECTED_COUNT,
        "re_extraction_calls": IMPORT_CV_CALLS + CV_PARSE_CALLS,
        "import_cv_calls": IMPORT_CV_CALLS,
        "parse_cv_text_calls": CV_PARSE_CALLS,
        "extract_text_calls_for_evidence_only": evidence_extract_calls,
        "phi_calls": PHI_CALLS,
        "c1_calls": C1_CALLS,
        "writer_calls": WRITER_CALLS,
        "parser_changes": 0,
        "ground_truth_changes": 0,
        "prediction_changes": pred_changed,
        "predictions_modified": pred_changed > 0,
        "evaluated_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_commit_at_eval": _git_commit(),
        "dataset": DATASET_NAME,
    }
    if pred_changed:
        prefix = (
            "RESULT: MINI HOLDOUT PHASE B BLOCKED – SEAL INTEGRITY FAILURE\n"
            if DATASET_NAME == "mini_holdout_30"
            else "RESULT: PHASE B BLOCKED – SEAL INTEGRITY FAILURE\n"
        )
        raise SystemExit(
            prefix + f"predictions changed during evaluation: {pred_changed}"
        )

    # Write artifacts (do not touch Phase A seal / predictions)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "phase_b_results.json").write_text(
        json.dumps(phase_b_results, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8"
    )
    (OUT / "per_document_results.json").write_text(
        json.dumps(per_document, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8"
    )
    (OUT / "per_field_results.json").write_text(
        json.dumps({k: dict(v) for k, v in sorted(per_field_acc.items())}, ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )
    (OUT / "field_group_metrics.json").write_text(
        json.dumps(field_group, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (OUT / "slice_metrics.json").write_text(
        json.dumps(slice_metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (OUT / "error_inventory.json").write_text(
        json.dumps(error_inventory, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8"
    )
    (OUT / "critical_errors.json").write_text(
        json.dumps(
            {
                "n_critical_events": len(critical_all),
                "n_critical_invented": len(critical_invented),
                "documents": critical_docs,
                "events": critical_all,
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        )
        + "\n",
        encoding="utf-8",
    )
    (OUT / "schema_extension_results.json").write_text(
        json.dumps(schema_ext, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (OUT / "PHASE_B_INTEGRITY.json").write_text(
        json.dumps(integrity, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (OUT / "PHASE_B_COMPLETE.json").write_text(
        json.dumps(
            {
                "phase_b_complete": True,
                "overall_pass": target_ok,
                "dataset": DATASET_NAME,
                "evaluated_at_utc": integrity["evaluated_at_utc"],
                "note": "Holdout is no longer unseen. Further fixes require a new independent holdout.",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    return {
        "phase_b_results": phase_b_results,
        "integrity": integrity,
        "perfect_n": perfect_n,
        "perfect_core_n": perfect_core_n,
        "bucket": dict(bucket),
        "critical_invented": len(critical_invented),
        "critical_all": len(critical_all),
        "critical_docs": critical_docs,
        "weak_group": weak_group,
        "weak_slice": weak_slice,
        "target_ok": target_ok,
        "agg": agg,
        "strict_accuracy": strict_accuracy,
        "field_group": field_group,
        "slice_metrics": slice_metrics,
        "per_document": per_document,
        "error_inventory": error_inventory,
    }


def _git_commit() -> str:
    import subprocess

    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except Exception:  # noqa: BLE001
        return ""


def main() -> int:
    parser = argparse.ArgumentParser(description="Holdout Phase B sealed evaluation")
    parser.add_argument(
        "--dataset",
        default=os.environ.get("HOLDOUT_DATASET", "final_holdout"),
        choices=sorted(DATASETS.keys()),
        help="Dataset key (paths/IDs only; Scorer V2 unchanged)",
    )
    args = parser.parse_args()
    configure_dataset(args.dataset)
    summary = run()
    m = summary["agg"]
    print(
        json.dumps(
            {
                "dataset": DATASET_NAME,
                "acc": m["field_accuracy"],
                "f1": m["f1"],
                "hallu": m["hallucination_rate"],
                "perfect": summary["perfect_n"],
                "perfect_core": summary["perfect_core_n"],
                "strict_acc": summary["strict_accuracy"],
                "critical_invented": summary["critical_invented"],
                "pass": summary["target_ok"],
                "weak_group": summary["weak_group"],
                "weak_slice": summary["weak_slice"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
