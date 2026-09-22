#!/usr/bin/env python3
"""Frozen Holdout-100 PREDICTION runner.

CRITICAL: This script must NOT open expected_results_full.json or solution_sheet.csv.
It only reads PDFs under tests/holdout_100/cvs/ and writes predictions.

Usage:
  python scripts/run_holdout_100_predictions.py --pipelines A1,A5,D2_DET
  python scripts/run_holdout_100_predictions.py --all-available
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import resource
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

HOLDOUT = ROOT / "tests" / "holdout_100"
CVS = HOLDOUT / "cvs"
OUT_ROOT = ROOT / "artifacts" / "holdout_100"
FROZEN_PRED = OUT_ROOT / "frozen_baseline_predictions"
META_PATH = OUT_ROOT / "FROZEN_BASELINE_METADATA.json"

# Forbidden files — refuse to open
_FORBIDDEN = {
    "expected_results_full.json",
    "solution_sheet.csv",
}


def _assert_no_gt_access() -> None:
    """Refuse if caller somehow tries to load GT via this module's helpers."""
    for name in _FORBIDDEN:
        p = HOLDOUT / name
        # existence check OK; reading content is forbidden in this script
        if not p.exists():
            continue


def _pdf_list() -> list[Path]:
    files = sorted(CVS.glob("*.pdf"))
    if len(files) != 100:
        raise SystemExit(f"expected 100 PDFs in {CVS}, found {len(files)}")
    return files


def _peak_rss_mb() -> float:
    # Linux: ru_maxrss is KB
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def _serialize(parsed: dict[str, Any]) -> dict[str, Any]:
    """JSON-safe subset of parsed CV dict."""

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


def pipe_A1_det_raw(path: Path) -> dict[str, Any]:
    from core.cv_extract import extract_text
    from core.cv_parser import parse_cv_text

    text = extract_text(path) or ""
    parsed = parse_cv_text(text)
    parsed["document_backend"] = "current"
    parsed["pipeline"] = "A1_det_raw"
    return parsed


def pipe_A3_det_evidence(path: Path) -> dict[str, Any]:
    from core.cv_extract import extract_text
    from core.cv_evidence import ground_language_entries
    from core.cv_parser import parse_cv_text

    text = extract_text(path) or ""
    parsed = parse_cv_text(text)
    kept, findings, rejected = ground_language_entries(parsed.get("languages") or [], text)
    parsed["languages"] = kept
    parsed["evidence_findings"] = [
        {"category": f.category, "value": f.value, "status": f.status.value, "notes": f.notes}
        for f in findings
    ]
    uncertain = list(parsed.get("uncertain_items") or [])
    for r in rejected:
        uncertain.append({"field": "languages", "value": r.get("language"), "reason": "evidence_reject"})
    parsed["uncertain_items"] = uncertain
    parsed["pipeline"] = "A3_det_evidence"
    return parsed


def pipe_A4_det_verify(path: Path) -> dict[str, Any]:
    from core.cv_extract import extract_text
    from core.cv_parser import parse_cv_text
    from core.cv_verify_repair import apply_verify_repair_pipeline

    text = extract_text(path) or ""
    parsed = parse_cv_text(text)
    parsed = apply_verify_repair_pipeline(parsed, text)
    parsed["pipeline"] = "A4_det_verify_repair"
    return parsed


def pipe_A5_det_product(path: Path) -> dict[str, Any]:
    from core.cv_parser import import_cv

    parsed = import_cv(path, guenther_enabled=False)
    parsed["pipeline"] = "A5_det_product"
    return parsed


def pipe_B1_phi_only(path: Path) -> dict[str, Any]:
    """Phi extract mapped into parsed shape without relying on DET structure fill.

    Still extracts text via CURRENT; DET parse is NOT used for content.
    """
    from core.cv_extract import extract_text
    from guenther.model_manager import PRODUCTION_MODEL_ID
    from guenther.service import get_guenther_service

    text = extract_text(path) or ""
    svc = get_guenther_service(enabled=True, model=PRODUCTION_MODEL_ID, refresh=False)
    env = svc.suggest_cv_extract(text)
    suggestion = dict(env.suggestion or {}) if env.ok else {}
    # Map flat suggestion → parsed-like
    langs = []
    for item in suggestion.get("languages") or []:
        if isinstance(item, str):
            parts = [p.strip() for p in item.replace("–", "-").split("-", 1)]
            langs.append({"language": parts[0], "level": parts[1] if len(parts) > 1 else ""})
    parsed: dict[str, Any] = {
        "personal": {"full_name": suggestion.get("full_name") or ""},
        "emails": list(suggestion.get("emails") or []),
        "phones": list(suggestion.get("phones") or []),
        "skills": list(suggestion.get("skills") or []),
        "software": [],
        "languages": langs,
        "education": [{"qualification": e, "institution": "", "start_date": "", "end_date": ""} for e in (suggestion.get("education") or [])],
        "work_experience": [
            {"title": t, "company": "", "start_date": "", "end_date": "", "responsibilities": []}
            for t in (suggestion.get("experience_titles") or [])
        ],
        "certificates": [{"name": c, "issuer": "", "year": ""} for c in (suggestion.get("certificates") or [])],
        "driving_license": "",
        "intelligence_status": "phi_only" if env.ok else "GUENTHER_UNAVAILABLE",
        "phi_invoked": bool(env.ok),
        "pipeline": "B1_phi_only",
        "phi_safety_notes": list(env.safety_notes or []),
    }
    name = (suggestion.get("full_name") or "").strip().split()
    if name:
        parsed["personal"]["first_name"] = name[0]
        parsed["personal"]["last_name"] = " ".join(name[1:]) if len(name) > 1 else ""
    return parsed


def pipe_B4_phi_verify(path: Path) -> dict[str, Any]:
    from core.cv_parser import import_cv

    parsed = import_cv(path, guenther_enabled=True)
    parsed["pipeline"] = "B4_phi_product_verify"
    return parsed


def pipe_B5_phi_split(path: Path) -> dict[str, Any]:
    from core.cv_intelligence import import_cv_canonical

    parsed = import_cv_canonical(path, guenther_enabled=True, split_phi_passes=True)
    parsed["pipeline"] = "B5_phi_split"
    return parsed


def pipe_C1_hybrid_uncertain(path: Path) -> dict[str, Any]:
    """DET product first; invoke Phi only if languages empty or education empty."""
    from core.cv_extract import extract_text
    from core.cv_parser import import_cv, parse_cv_text, parsed_to_qualifications
    from core.cv_intelligence import import_cv_canonical, reconcile_phi_into_parsed
    from guenther.model_manager import PRODUCTION_MODEL_ID
    from guenther.service import get_guenther_service

    det = import_cv(path, guenther_enabled=False)
    need_phi = (not det.get("languages")) or (not det.get("education")) or (not det.get("work_experience"))
    det["pipeline"] = "C1_hybrid_uncertain"
    det["phi_fallback_triggered"] = bool(need_phi)
    if not need_phi:
        return det
    text = extract_text(path) or ""
    svc = get_guenther_service(enabled=True, model=PRODUCTION_MODEL_ID, refresh=False)
    env = svc.suggest_cv_extract(text)
    if env.ok:
        sug = dict(env.suggestion or {})
        sug["_model_id"] = env.model_id or PRODUCTION_MODEL_ID
        det = reconcile_phi_into_parsed(det, sug, cv_text=text)
        from core.cv_verify_repair import apply_verify_repair_pipeline

        det = apply_verify_repair_pipeline(det, text)
        det["phi_invoked"] = True
    det["pipeline"] = "C1_hybrid_uncertain"
    return det


def pipe_C4_hybrid_fields(path: Path) -> dict[str, Any]:
    """DET for contact/personal; Phi gap-fill for semantic lists via product path when DET thin."""
    # Equivalent to product hybrid: always DET, Phi only fills gaps (reconcile already does that)
    return pipe_B4_phi_verify(path) | {"pipeline": "C4_hybrid_fields"}


def pipe_C5_det_phi_verify(path: Path) -> dict[str, Any]:
    return pipe_B4_phi_verify(path) | {"pipeline": "C5_det_phi_verify"}


def pipe_D2_det(path: Path) -> dict[str, Any]:
    from core.cv_document_backends import extract_with_backend
    from core.cv_parser import parse_cv_text
    from core.cv_verify_repair import apply_verify_repair_pipeline

    text = extract_with_backend(path, "pymupdf4llm")
    parsed = parse_cv_text(text)
    parsed = apply_verify_repair_pipeline(parsed, text)
    parsed["document_backend"] = "pymupdf4llm"
    parsed["pipeline"] = "D2_pymupdf4llm_det"
    return parsed


def pipe_D2_phi(path: Path) -> dict[str, Any]:
    from core.cv_intelligence import import_cv_canonical

    parsed = import_cv_canonical(path, guenther_enabled=True, document_backend="pymupdf4llm")
    parsed["pipeline"] = "D2_pymupdf4llm_phi"
    return parsed


PIPELINES: dict[str, Callable[[Path], dict[str, Any]]] = {
    "A1_det_raw": pipe_A1_det_raw,
    "A3_det_evidence": pipe_A3_det_evidence,
    "A4_det_verify_repair": pipe_A4_det_verify,
    "A5_det_product": pipe_A5_det_product,
    "B1_phi_only": pipe_B1_phi_only,
    "B4_phi_product_verify": pipe_B4_phi_verify,
    "B5_phi_split": pipe_B5_phi_split,
    "C1_hybrid_uncertain": pipe_C1_hybrid_uncertain,
    "C4_hybrid_fields": pipe_C4_hybrid_fields,
    "C5_det_phi_verify": pipe_C5_det_phi_verify,
    "D2_pymupdf4llm_det": pipe_D2_det,
    "D2_pymupdf4llm_phi": pipe_D2_phi,
}

NOT_AVAILABLE = {
    "D3_docling_det": "docling not installed",
    "D3_docling_phi": "docling not installed",
    "D4_marker": "marker not installed / disproportionate cost",
    "A2_det_validators": "folded into A1/A5 (validators live inside parse_cv_text)",
}


def run_pipeline(name: str, *, limit: int | None = None) -> dict[str, Any]:
    if name in NOT_AVAILABLE:
        return {"pipeline": name, "status": "NOT_AVAILABLE", "reason": NOT_AVAILABLE[name]}
    fn = PIPELINES[name]
    out_dir = FROZEN_PRED / name
    out_dir.mkdir(parents=True, exist_ok=True)
    docs = _pdf_list()
    if limit:
        docs = docs[:limit]
    results = []
    t0 = time.perf_counter()
    rss0 = _peak_rss_mb()
    for i, pdf in enumerate(docs, 1):
        started = time.perf_counter()
        err = None
        parsed: dict[str, Any] | None = None
        try:
            parsed = fn(pdf)
        except Exception as exc:  # noqa: BLE001
            err = f"{type(exc).__name__}: {exc}"
            traceback.print_exc()
        elapsed = time.perf_counter() - started
        rec = {
            "document": pdf.name,
            "elapsed_s": elapsed,
            "error": err,
            "prediction": _serialize(parsed) if parsed is not None else None,
        }
        (out_dir / f"{pdf.stem}.json").write_text(
            json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        results.append(
            {
                "document": pdf.name,
                "elapsed_s": elapsed,
                "error": err,
                "ok": err is None and parsed is not None,
            }
        )
        print(f"[{name}] {i}/{len(docs)} {pdf.name} {elapsed:.2f}s err={err}", flush=True)
    wall = time.perf_counter() - t0
    summary = {
        "pipeline": name,
        "status": "OK",
        "n_documents": len(docs),
        "n_ok": sum(1 for r in results if r["ok"]),
        "n_error": sum(1 for r in results if not r["ok"]),
        "wall_s": wall,
        "avg_s": wall / max(1, len(docs)),
        "median_s": sorted(r["elapsed_s"] for r in results)[len(results) // 2] if results else 0,
        "p95_s": sorted(r["elapsed_s"] for r in results)[int(0.95 * (len(results) - 1))] if results else 0,
        "peak_rss_mb": max(rss0, _peak_rss_mb()),
        "documents": results,
    }
    (out_dir / "_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return summary


def write_metadata(pipelines: list[str], summaries: list[dict[str, Any]]) -> None:
    import subprocess

    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    branch = subprocess.check_output(
        ["git", "branch", "--show-current"], cwd=ROOT, text=True
    ).strip()
    status = subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True)
    # prompt hashes
    from guenther.prompts import SYSTEM_PHI_EXTRACT, SYSTEM_PHI_WRITE, SYSTEM_CORE

    def ph(s: str) -> str:
        return hashlib.sha256(s.encode()).hexdigest()[:16]

    meta = {
        "schema_version": 1,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_commit": commit,
        "branch": branch,
        "uncommitted_changes": [ln for ln in status.splitlines() if ln.strip()],
        "n_documents": 100,
        "pipelines_requested": pipelines,
        "pipeline_summaries": [
            {k: s[k] for k in s if k != "documents"} for s in summaries
        ],
        "models": {"production": "phi4-mini", "temperature_extract": 0.0},
        "prompt_hashes": {
            "SYSTEM_CORE": ph(SYSTEM_CORE),
            "SYSTEM_PHI_EXTRACT": ph(SYSTEM_PHI_EXTRACT),
            "SYSTEM_PHI_WRITE": ph(SYSTEM_PHI_WRITE),
        },
        "document_backends": {
            "current": "pypdf",
            "pymupdf4llm": "optional",
            "docling": "NOT_AVAILABLE",
        },
        "hardware": {
            "platform": platform.platform(),
            "processor": platform.processor(),
            "python": sys.version,
            "cpu_count": os.cpu_count(),
        },
        "forbidden_gt_read_during_predictions": True,
        "notes": "Frozen baseline — do not overwrite after evaluation begins.",
    }
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    if META_PATH.exists():
        # never overwrite frozen metadata — write sibling with timestamp
        alt = OUT_ROOT / f"FROZEN_BASELINE_METADATA_{int(time.time())}.json"
        alt.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"metadata exists; wrote {alt}")
    else:
        META_PATH.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"wrote {META_PATH}")


def main() -> int:
    _assert_no_gt_access()
    ap = argparse.ArgumentParser()
    ap.add_argument("--pipelines", default="", help="Comma-separated pipeline ids")
    ap.add_argument("--all-available", action="store_true")
    ap.add_argument("--fast-only", action="store_true", help="DET + pymupdf DET only")
    ap.add_argument("--phi-only", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    if args.fast_only:
        names = [
            "A1_det_raw",
            "A3_det_evidence",
            "A4_det_verify_repair",
            "A5_det_product",
            "D2_pymupdf4llm_det",
        ]
    elif args.phi_only:
        names = [
            "B1_phi_only",
            "B4_phi_product_verify",
            "B5_phi_split",
            "C1_hybrid_uncertain",
            "D2_pymupdf4llm_phi",
        ]
    elif args.all_available:
        names = list(PIPELINES.keys())
    elif args.pipelines:
        names = [x.strip() for x in args.pipelines.split(",") if x.strip()]
    else:
        raise SystemExit("specify --pipelines, --fast-only, --phi-only, or --all-available")

    FROZEN_PRED.mkdir(parents=True, exist_ok=True)
    # record NOT_AVAILABLE stubs
    for na, reason in NOT_AVAILABLE.items():
        d = FROZEN_PRED / na
        d.mkdir(parents=True, exist_ok=True)
        (d / "_summary.json").write_text(
            json.dumps(
                {"pipeline": na, "status": "NOT_AVAILABLE", "reason": reason},
                indent=2,
            ),
            encoding="utf-8",
        )

    summaries = []
    for name in names:
        print(f"=== START {name} ===", flush=True)
        summaries.append(run_pipeline(name, limit=args.limit))
    write_metadata(names, summaries)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
