#!/usr/bin/env python3
"""NV3 Post-Analysis full re-extract (50 PDFs) after education/heute fixes.

POST-ANALYSIS only — NOT a blind test / NOT a 99% claim.
Does NOT overwrite frozen Phase-A predictions or PHASE_B results.
Writes under tests/docpick_blind_de_en_v2/post_analysis_round8/.
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

PDF_DIR = ROOT / "tests/docpick_blind_de_en_v2/phase_a_pdfs"
OUT = ROOT / "tests/docpick_blind_de_en_v2/post_analysis_round8"
PRED_DIR = OUT / "predictions"
# Never touch:
FROZEN_DIR = ROOT / "tests/docpick_blind_de_en_v2/frozen_predictions"


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _peak_rss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def main() -> int:
    os.environ.setdefault("KARRIEREKRAKE_CV_LLM_BASE", "http://127.0.0.1:8765/v1")
    from core.cv_docpick_import import CvImportError, DEFAULT_LLM_BASE, DEFAULT_MODEL, import_cv_docpick

    assert FROZEN_DIR.is_dir(), "frozen preds must remain untouched"
    OUT.mkdir(parents=True, exist_ok=True)
    PRED_DIR.mkdir(parents=True, exist_ok=True)

    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except Exception:  # noqa: BLE001
        commit = ""

    pdfs = sorted(PDF_DIR.glob("NV3_*.pdf"))
    if len(pdfs) != 50:
        print(f"expected 50 PDFs, got {len(pdfs)}", file=sys.stderr)
        return 2

    meta = {
        "test_type": "POST_ANALYSIS_NV3_NOT_BLIND",
        "disclaimer": (
            "Post-Analysis re-extract after education/heute fixes. "
            "Frozen Blind F1 0.980 unchanged. No 99% claim."
        ),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "git_commit": commit,
        "llm_base": DEFAULT_LLM_BASE,
        "model": DEFAULT_MODEL,
        "det_fallback": False,
        "frozen_predictions_untouched": True,
        "parser_sha256": _sha256_file(ROOT / "core/cv_docpick_import.py"),
    }
    (OUT / "POST_ANALYSIS_META.json").write_text(
        json.dumps(meta, indent=2) + "\n", encoding="utf-8"
    )

    predictions = []
    timings: dict[str, float] = {}
    t0 = time.perf_counter()
    peak = _peak_rss_mb()
    n_ok = 0

    for pdf in pdfs:
        did = pdf.stem
        out_path = PRED_DIR / f"{did}.json"
        if out_path.is_file() and "--force" not in sys.argv:
            existing = json.loads(out_path.read_text(encoding="utf-8"))
            if not existing.get("tech_error"):
                predictions.append(
                    {
                        "id": did,
                        "prediction_file": str(out_path.relative_to(ROOT)),
                        "sha256": _sha256_file(out_path),
                        "elapsed_s": 0.0,
                        "ok": True,
                        "resumed": True,
                    }
                )
                n_ok += 1
                timings[did] = 0.0
                print(f"{did} skip-existing", flush=True)
                continue
        s = time.perf_counter()
        try:
            pred = import_cv_docpick(pdf)
            pred["post_analysis"] = True
            pred["blind_doc_id"] = did
            ok = True
            n_ok += 1
        except Exception as exc:  # noqa: BLE001
            pred = {
                "pipeline": "docpick_qwen35_4b",
                "tech_error": f"{type(exc).__name__}: {exc}",
                "post_analysis": True,
                "blind_doc_id": did,
            }
            ok = False
        elapsed = time.perf_counter() - s
        timings[did] = elapsed
        peak = max(peak, _peak_rss_mb())
        blob = json.dumps(pred, ensure_ascii=False, indent=2) + "\n"
        out_path.write_bytes(blob.encode("utf-8"))
        predictions.append(
            {
                "id": did,
                "prediction_file": str(out_path.relative_to(ROOT)),
                "sha256": hashlib.sha256(blob.encode("utf-8")).hexdigest(),
                "elapsed_s": elapsed,
                "ok": ok,
            }
        )
        print(f"{did} ok={ok} {elapsed:.1f}s", flush=True)

    wall = time.perf_counter() - t0
    seal = {
        **meta,
        "n_documents": len(predictions),
        "n_ok": n_ok,
        "predictions": predictions,
        "performance": {
            "wall_s": wall,
            "avg_s_per_cv": wall / max(len(predictions), 1),
            "peak_rss_mb": peak,
            "per_doc_s": timings,
        },
    }
    seal_path = OUT / "POST_ANALYSIS_EXTRACT_SEAL.json"
    seal_path.write_text(json.dumps(seal, indent=2) + "\n", encoding="utf-8")
    print(
        f"Wrote {seal_path} n_ok={n_ok}/{len(predictions)} wall={wall:.1f}s peak={peak:.0f}MB",
        flush=True,
    )
    return 0 if n_ok == len(predictions) else 1


if __name__ == "__main__":
    raise SystemExit(main())
