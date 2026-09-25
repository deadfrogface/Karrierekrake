#!/usr/bin/env python3
"""Sealed regression extraction for Docpick CV import (PR #62).

REGRESSION on known CVs — NOT an independent blind test / NOT a 99% claim.

Guarantees:
- Reads ONLY PDF paths from EXTRACTION_MANIFEST_PDF_ONLY.json
- Does NOT open ground-truth JSON or prior prediction files
- Calls core.cv_docpick_import.import_cv_docpick only (no DET)
- Writes predictions + SHA-256 seal BEFORE any scoring step

Usage:
  python scripts/run_docpick_regression_sealed_extract.py
"""

from __future__ import annotations

import hashlib
import json
import os
import resource
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OUT = ROOT / "tests" / "docpick_qwen35" / "regression_known_cvs"
MANIFEST = OUT / "EXTRACTION_MANIFEST_PDF_ONLY.json"
PRED_DIR = OUT / "frozen_predictions"
SEAL_PATH = OUT / "PHASE_A_EXTRACTION_SEAL.json"

# Hard deny: refuse to open these during extraction
_FORBIDDEN_SUBSTR = (
    "expected_results",
    "Sollwerte",
    "ground_truth",
    "predictions_docpick",
    "COMPLETE_GT",
    "INVENTED_AUDIT",
)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _peak_rss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def _assert_no_gt_access(path: Path) -> None:
    s = str(path).replace("\\", "/")
    for frag in _FORBIDDEN_SUBSTR:
        if frag in s and path.suffix.lower() in {".json", ".txt"} and "EXTRACTION_MANIFEST" not in s:
            raise RuntimeError(f"Refusing to read GT/prior artifact during extraction: {path}")


def build_freeze_seal() -> dict:
    """Freeze parser + config + scorer hashes (no GT)."""
    from core.cv_docpick_import import DEFAULT_LLM_BASE, DEFAULT_MODEL, KarrierekrakeCVSchema
    import core.cv_docpick_import as cdi
    import core.cv_intelligence as ci
    import core.cv_parser as cp

    # Confirm DET blocked
    det_blocked = False
    try:
        cp.parse_cv_text("x")
    except RuntimeError as exc:
        det_blocked = "DET" in str(exc)

    model_path = Path(DEFAULT_MODEL)
    model_sha = _sha256_file(model_path) if model_path.is_file() else None

    files = {
        "core/cv_docpick_import.py": _sha256_file(ROOT / "core" / "cv_docpick_import.py"),
        "core/cv_intelligence.py": _sha256_file(ROOT / "core" / "cv_intelligence.py"),
        "core/cv_parser.py": _sha256_file(ROOT / "core" / "cv_parser.py"),
        "scripts/holdout_scorer_v2.py": _sha256_file(ROOT / "scripts" / "holdout_scorer_v2.py"),
        "scripts/holdout_scorer_v3_complete_gt.py": _sha256_file(
            ROOT / "scripts" / "holdout_scorer_v3_complete_gt.py"
        ),
        "scripts/run_docpick_regression_sealed_extract.py": _sha256_file(Path(__file__)),
    }

    import subprocess

    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
    except Exception:  # noqa: BLE001
        commit = ""

    return {
        "seal_type": "PARSER_CONFIG_SCORER_FREEZE",
        "test_type": "REGRESSION_KNOWN_CVS_NOT_BLIND",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "git_commit": commit,
        "det_parse_cv_text_blocked": det_blocked,
        "productive_import": "core.cv_docpick_import.import_cv_docpick",
        "cv_intelligence_uses_docpick": "import_cv_docpick" in Path(ci.__file__).read_text(encoding="utf-8"),
        "llm": {
            "base_url": DEFAULT_LLM_BASE,
            "model_path": DEFAULT_MODEL,
            "model_sha256": model_sha,
            "temperature": 0.0,
            "schema": KarrierekrakeCVSchema.__name__,
            "module": cdi.__file__,
        },
        "file_sha256": files,
        "manifest_sha256": _sha256_file(MANIFEST),
        "forbidden_reads_during_extraction": list(_FORBIDDEN_SUBSTR),
    }


def main() -> int:
    if not MANIFEST.is_file():
        print(f"missing {MANIFEST}", file=sys.stderr)
        return 2

    # Ensure LLM reachable
    os.environ.setdefault("KARRIEREKRAKE_CV_LLM_BASE", "http://127.0.0.1:8765/v1")

    freeze = build_freeze_seal()
    if not freeze["det_parse_cv_text_blocked"]:
        print("DET not blocked — abort", file=sys.stderr)
        return 3

    PRED_DIR.mkdir(parents=True, exist_ok=True)
    (OUT / "PARSER_FREEZE.json").write_text(
        json.dumps(freeze, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert manifest.get("locked") is True
    # Manifest must not embed GT
    raw_m = MANIFEST.read_text(encoding="utf-8")
    for frag in ("expected_results", "ground_truth", "Sollwerte"):
        if frag in raw_m:
            print(f"Manifest must not reference {frag}", file=sys.stderr)
            return 4

    from core.cv_docpick_import import import_cv_docpick, CvImportError

    predictions_meta = []
    timings = {}
    t0 = time.perf_counter()
    peak = _peak_rss_mb()

    for meta in manifest["documents"]:
        pdf = ROOT / meta["path"]
        _assert_no_gt_access(pdf)
        if not pdf.is_file():
            pred = {"tech_error": f"missing_pdf:{pdf}", "pipeline": "docpick_qwen35_4b"}
            elapsed = 0.0
        else:
            s = time.perf_counter()
            try:
                # ONLY PDF path — import_cv_docpick does not take GT
                pred = import_cv_docpick(pdf)
                pred["regression_corpus_id"] = meta["corpus_id"]
                pred["regression_doc_id"] = meta["id"]
                pred["regression_lang"] = meta["lang"]
            except CvImportError as exc:
                pred = {
                    "pipeline": "docpick_qwen35_4b",
                    "tech_error": str(exc),
                    "cv_import_error_code": getattr(exc, "code", ""),
                    "regression_corpus_id": meta["corpus_id"],
                    "regression_doc_id": meta["id"],
                    "regression_lang": meta["lang"],
                }
            except Exception as exc:  # noqa: BLE001
                pred = {
                    "pipeline": "docpick_qwen35_4b",
                    "tech_error": f"{type(exc).__name__}: {exc}",
                    "traceback": traceback.format_exc(),
                    "regression_corpus_id": meta["corpus_id"],
                    "regression_doc_id": meta["id"],
                    "regression_lang": meta["lang"],
                }
            elapsed = time.perf_counter() - s
        timings[meta["id"]] = elapsed
        peak = max(peak, _peak_rss_mb())

        out_name = f"{meta['corpus_id']}__{meta['id']}.json"
        out_path = PRED_DIR / out_name
        payload = json.dumps(pred, ensure_ascii=False, indent=2, default=str) + "\n"
        out_path.write_text(payload, encoding="utf-8")
        predictions_meta.append(
            {
                "corpus_id": meta["corpus_id"],
                "id": meta["id"],
                "lang": meta["lang"],
                "pdf": meta["path"],
                "prediction_file": str(out_path.relative_to(ROOT)),
                "sha256": _sha256_bytes(payload.encode("utf-8")),
                "elapsed_s": elapsed,
                "ok": not bool(pred.get("tech_error")),
            }
        )
        print(
            f"EXTRACT {meta['corpus_id']}/{meta['id']} {elapsed:.1f}s ok={predictions_meta[-1]['ok']}",
            flush=True,
        )

    wall = time.perf_counter() - t0
    seal = {
        "seal_type": "PHASE_A_PREDICTION_SEAL",
        "test_type": "REGRESSION_KNOWN_CVS_NOT_BLIND",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "parser_freeze": freeze,
        "manifest_id": manifest.get("manifest_id"),
        "manifest_sha256": _sha256_file(MANIFEST),
        "n_documents": len(predictions_meta),
        "n_ok": sum(1 for p in predictions_meta if p["ok"]),
        "predictions": predictions_meta,
        "performance": {
            "wall_s": wall,
            "avg_s_per_cv": wall / max(1, len(predictions_meta)),
            "peak_rss_mb": peak,
            "per_doc_s": timings,
        },
        "gt_not_loaded": True,
        "scoring_not_run_yet": True,
        "disclaimer": "Known-CV regression. Not an independent blind test. Not a 99% claim.",
    }
    SEAL_PATH.write_text(json.dumps(seal, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"SEALED {SEAL_PATH} n_ok={seal['n_ok']}/{seal['n_documents']} avg_s={seal['performance']['avg_s_per_cv']:.1f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
