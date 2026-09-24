#!/usr/bin/env python3
"""Sealed Phase-A extract for Docpick Blind DE/EN v1 (PDF only, no GT)."""

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

OUT = ROOT / "tests" / "docpick_blind_de_en_v1"
MANIFEST = OUT / "EXTRACTION_MANIFEST_PDF_ONLY.json"
PRED_DIR = OUT / "frozen_predictions"
SEAL = OUT / "PHASE_A_EXTRACTION_SEAL.json"


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    os.environ.setdefault("KARRIEREKRAKE_CV_LLM_BASE", "http://127.0.0.1:8765/v1")
    if not MANIFEST.is_file():
        print(f"missing {MANIFEST}", file=sys.stderr)
        return 2
    from core.cv_docpick_import import (
        CV_IMPORT_BUDGET_COLD_S,
        CV_IMPORT_BUDGET_WARM_S,
        DEFAULT_LLM_BASE,
        DEFAULT_MODEL,
        import_cv_docpick,
    )

    PRED_DIR.mkdir(parents=True, exist_ok=True)
    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except Exception:
        commit = ""
    model_path = Path(DEFAULT_MODEL)
    freeze = {
        "seal_type": "PARSER_FREEZE_BLIND_DE_EN_V1",
        "test_type": "INDEPENDENT_BLIND_DE_EN",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "git_commit": commit,
        "det_fallback": False,
        "llm": {
            "base_url": DEFAULT_LLM_BASE,
            "model_path": DEFAULT_MODEL,
            "model_sha256": _sha256_file(model_path) if model_path.is_file() else None,
            "temperature": 0.0,
            "max_tokens_env_default": os.environ.get("KARRIEREKRAKE_CV_LLM_MAX_TOKENS", "1024"),
        },
        "runtime_budget_s": {"warm": CV_IMPORT_BUDGET_WARM_S, "cold": CV_IMPORT_BUDGET_COLD_S},
        "file_sha256": {
            "core/cv_docpick_import.py": _sha256_file(ROOT / "core/cv_docpick_import.py"),
            "core/cv_intelligence.py": _sha256_file(ROOT / "core/cv_intelligence.py"),
        },
        "manifest_sha256": _sha256_file(MANIFEST),
        "gt_not_loaded": True,
    }
    (OUT / "PARSER_FREEZE.json").write_text(json.dumps(freeze, indent=2) + "\n", encoding="utf-8")

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert manifest.get("gt_not_loaded") is True
    preds = []
    timings = {}
    t0 = time.perf_counter()
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0
    n_ok = 0
    for meta in manifest["documents"]:
        pdf = ROOT / meta["path"]
        key = f"{meta['corpus_id']}__{meta['id']}"
        s = time.perf_counter()
        try:
            pred = import_cv_docpick(pdf)
            pred["blind_doc_id"] = meta["id"]
            pred["blind_lang"] = meta["lang"]
            ok = True
            n_ok += 1
        except Exception as exc:  # noqa: BLE001
            pred = {"tech_error": f"{type(exc).__name__}: {exc}", "pipeline": "docpick_qwen35_4b"}
            ok = False
        elapsed = time.perf_counter() - s
        timings[meta["id"]] = elapsed
        peak = max(peak, resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0)
        outp = PRED_DIR / f"{key}.json"
        blob = json.dumps(pred, ensure_ascii=False, indent=2) + "\n"
        outp.write_text(blob, encoding="utf-8")
        preds.append(
            {
                "id": meta["id"],
                "lang": meta["lang"],
                "pdf": meta["path"],
                "prediction_file": str(outp.relative_to(ROOT)),
                "sha256": hashlib.sha256(blob.encode()).hexdigest(),
                "elapsed_s": elapsed,
                "ok": ok,
            }
        )
        print(f"{key} ok={ok} {elapsed:.1f}s", flush=True)

    wall = time.perf_counter() - t0
    warm_ids = [p["id"] for p in preds[1:] if p["ok"]]
    warm_avg = (
        sum(timings[i] for i in warm_ids) / len(warm_ids) if warm_ids else None
    )
    seal = {
        "seal_type": "PHASE_A_BLIND_DE_EN_V1",
        "test_type": "INDEPENDENT_BLIND_DE_EN",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "parser_freeze": freeze,
        "gt_not_loaded": True,
        "n_documents": len(preds),
        "n_ok": n_ok,
        "predictions": preds,
        "performance": {
            "wall_s": wall,
            "avg_s_per_cv": wall / max(len(preds), 1),
            "peak_rss_mb": peak,
            "cold_s": timings.get(preds[0]["id"]) if preds else None,
            "warm_avg_s": warm_avg,
            "per_doc_s": timings,
            "budget_warm_s": CV_IMPORT_BUDGET_WARM_S,
            "budget_cold_s": CV_IMPORT_BUDGET_COLD_S,
            "warm_within_budget": bool(warm_avg is not None and warm_avg <= CV_IMPORT_BUDGET_WARM_S),
        },
    }
    SEAL.write_text(json.dumps(seal, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(seal["performance"], indent=2))
    print(f"Wrote {SEAL}")
    return 0 if n_ok == len(preds) else 1


if __name__ == "__main__":
    raise SystemExit(main())
