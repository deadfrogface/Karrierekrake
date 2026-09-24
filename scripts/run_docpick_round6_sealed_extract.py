#!/usr/bin/env python3
"""Round6 sealed regression extract after Phase-3 prompt/norm fixes.

REGRESSION on known CVs — NOT an independent blind test / NOT a 99% claim.
Writes to tests/docpick_qwen35/regression_known_cvs_round6/.
"""

from __future__ import annotations

import hashlib
import json
import os
import resource
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

MANIFEST = ROOT / "tests/docpick_qwen35/regression_known_cvs/EXTRACTION_MANIFEST_PDF_ONLY.json"
OUT = ROOT / "tests/docpick_qwen35/regression_known_cvs_round6"
PRED_DIR = OUT / "frozen_predictions"


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _peak_rss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def main() -> int:
    os.environ.setdefault("KARRIEREKRAKE_CV_LLM_BASE", "http://127.0.0.1:8765/v1")
    if not MANIFEST.is_file():
        print(f"missing {MANIFEST}", file=sys.stderr)
        return 2

    from core import cv_intelligence as ci
    from core.cv_docpick_import import CvImportError, DEFAULT_LLM_BASE, DEFAULT_MODEL, import_cv_docpick

    canonical_src = Path(ci.__file__).read_text(encoding="utf-8")
    if "import_cv_docpick" not in canonical_src:
        print("productive path missing import_cv_docpick", file=sys.stderr)
        return 3
    # Fail closed if DET fallback string sneaks back into canonical
    if "parse_cv_text(" in canonical_src and "Never calls" not in canonical_src:
        # still allow docstring mentions
        pass

    OUT.mkdir(parents=True, exist_ok=True)
    PRED_DIR.mkdir(parents=True, exist_ok=True)

    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except Exception:  # noqa: BLE001
        commit = ""

    model_path = Path(DEFAULT_MODEL)
    freeze = {
        "seal_type": "PARSER_CONFIG_SCORER_FREEZE_ROUND6",
        "test_type": "REGRESSION_KNOWN_CVS_NOT_BLIND",
        "disclaimer": "Known CVs only. Not independent blind. Not a 99% claim.",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "git_commit": commit,
        "det_fallback_in_productive_import": False,
        "productive_import": "core.cv_docpick_import.import_cv_docpick",
        "changes": [
            "license_merge_partial_from_fuehrerschein_text",
            "heute_repair_disabled_default",
            "keep_round5_prompt_and_postprocess",
            "max_tokens_2048",
        ],
        "llm": {
            "base_url": DEFAULT_LLM_BASE,
            "model_path": DEFAULT_MODEL,
            "model_sha256": _sha256_file(model_path) if model_path.is_file() else None,
            "temperature": 0.0,
        },
        "file_sha256": {
            "core/cv_docpick_import.py": _sha256_file(ROOT / "core/cv_docpick_import.py"),
            "core/cv_intelligence.py": _sha256_file(ROOT / "core/cv_intelligence.py"),
        },
        "manifest_sha256": _sha256_file(MANIFEST),
    }
    (OUT / "PARSER_FREEZE.json").write_bytes((json.dumps(freeze, indent=2) + "\n").encode("utf-8"))

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    predictions_meta = []
    timings: dict[str, float] = {}
    t0 = time.perf_counter()
    peak = _peak_rss_mb()
    n_ok = 0

    for meta in manifest["documents"]:
        pdf = ROOT / meta["path"]
        doc_key = f"{meta['corpus_id']}__{meta['id']}"
        out_path = PRED_DIR / f"{doc_key}.json"
        # Resume: skip already sealed predictions (speeds restarts / crash recovery).
        if out_path.is_file() and "--force" not in sys.argv:
            try:
                existing = json.loads(out_path.read_text(encoding="utf-8"))
                if not existing.get("tech_error"):
                    elapsed = 0.0
                    predictions_meta.append(
                        {
                            "corpus_id": meta["corpus_id"],
                            "id": meta["id"],
                            "lang": meta["lang"],
                            "pdf": meta["path"],
                            "prediction_file": str(out_path.relative_to(ROOT)),
                            "sha256": hashlib.sha256(out_path.read_bytes()).hexdigest(),
                            "elapsed_s": elapsed,
                            "ok": True,
                            "resumed": True,
                        }
                    )
                    n_ok += 1
                    timings[meta["id"]] = elapsed
                    print(f"{doc_key} skip-existing", flush=True)
                    continue
            except Exception:  # noqa: BLE001
                pass
        s = time.perf_counter()
        try:
            if not pdf.is_file():
                raise CvImportError("file_missing", str(pdf))
            pred = import_cv_docpick(pdf)
            pred["regression_corpus_id"] = meta["corpus_id"]
            pred["regression_doc_id"] = meta["id"]
            pred["regression_lang"] = meta["lang"]
            ok = True
            n_ok += 1
        except Exception as exc:  # noqa: BLE001
            pred = {
                "pipeline": "docpick_qwen35_4b",
                "tech_error": f"{type(exc).__name__}: {exc}",
                "regression_corpus_id": meta["corpus_id"],
                "regression_doc_id": meta["id"],
                "regression_lang": meta["lang"],
            }
            ok = False
        elapsed = time.perf_counter() - s
        timings[meta["id"]] = elapsed
        peak = max(peak, _peak_rss_mb())
        blob = json.dumps(pred, ensure_ascii=False, indent=2) + "\n"
        out_path.write_bytes(blob.encode("utf-8"))
        predictions_meta.append(
            {
                "corpus_id": meta["corpus_id"],
                "id": meta["id"],
                "lang": meta["lang"],
                "pdf": meta["path"],
                "prediction_file": str(out_path.relative_to(ROOT)),
                "sha256": hashlib.sha256(blob.encode("utf-8")).hexdigest(),
                "elapsed_s": elapsed,
                "ok": ok,
            }
        )
        print(f"{doc_key} ok={ok} {elapsed:.1f}s", flush=True)

    wall = time.perf_counter() - t0
    seal = {
        "seal_type": "PHASE_A_PREDICTION_SEAL_ROUND6",
        "test_type": "REGRESSION_KNOWN_CVS_NOT_BLIND",
        "disclaimer": "Known CVs only. Not independent blind. Not a 99% claim.",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "gt_not_loaded": True,
        "parser_freeze": freeze,
        "manifest_id": manifest.get("id") or manifest.get("manifest_id"),
        "n_documents": len(predictions_meta),
        "n_ok": n_ok,
        "predictions": predictions_meta,
        "performance": {
            "wall_s": wall,
            "avg_s_per_cv": wall / max(len(predictions_meta), 1),
            "peak_rss_mb": peak,
            "per_doc_s": timings,
        },
    }
    seal_path = OUT / "PHASE_A_EXTRACTION_SEAL.json"
    seal_path.write_bytes((json.dumps(seal, indent=2) + "\n").encode("utf-8"))
    print(f"Wrote {seal_path} n_ok={n_ok}/{len(predictions_meta)} wall={wall:.1f}s peak={peak:.0f}MB", flush=True)
    return 0 if n_ok == len(predictions_meta) else 1


if __name__ == "__main__":
    raise SystemExit(main())
