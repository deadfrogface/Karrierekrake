#!/usr/bin/env python3
"""Blind DE/EN v2 (NV3_50) Phase A — sealed extract. GT must stay unread.

Uses Round7 productive path: Docling + Docpick/Qwen. No DET fallback.
No scoring against ground truth in this script.
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

OUT = ROOT / "tests" / "docpick_blind_de_en_v2"
MANIFEST = OUT / "EXTRACTION_MANIFEST_PDF_ONLY.json"
SUPPLIER_MANIFEST = OUT / "PDF_SHA256_MANIFEST.json"
PRED_DIR = OUT / "frozen_predictions"
SEAL = OUT / "PHASE_A_EXTRACTION_SEAL.json"
FREEZE = OUT / "PARSER_FREEZE.json"
# Hard ban: never open Phase B solutions during Phase A.
PHASE_B_DIR = OUT / "phase_b_solutions"


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_utf8(path: Path, text: str) -> None:
    """Write UTF-8 with LF only (avoid Windows CRLF seal-hash drift)."""
    path.write_bytes(text.encode("utf-8"))


def _verify_pdf_hashes(manifest: dict) -> None:
    if not SUPPLIER_MANIFEST.is_file():
        raise SystemExit(f"missing supplier manifest {SUPPLIER_MANIFEST}")
    supplier = json.loads(SUPPLIER_MANIFEST.read_text(encoding="utf-8"))
    by_id = {d["document_id"]: d["sha256"] for d in supplier["documents"]}
    if len(by_id) != 50:
        raise SystemExit(f"supplier manifest has {len(by_id)} docs, expected 50")
    for meta in manifest["documents"]:
        expected = by_id.get(meta["id"])
        if expected is None:
            raise SystemExit(f"manifest id {meta['id']} not in supplier PDF hash list")
        pdf = ROOT / meta["path"]
        if not pdf.is_file():
            raise SystemExit(f"missing PDF {pdf}")
        actual = _sha256_file(pdf)
        if actual != expected:
            raise SystemExit(
                f"PDF hash mismatch {meta['id']}: expected {expected}, got {actual}"
            )
        if meta.get("pdf_sha256") and meta["pdf_sha256"] != expected:
            raise SystemExit(f"extraction manifest pdf_sha256 drift for {meta['id']}")


def main() -> int:
    os.environ.setdefault("KARRIEREKRAKE_CV_LLM_BASE", "http://127.0.0.1:8765/v1")
    if PHASE_B_DIR.exists() and any(PHASE_B_DIR.iterdir()):
        print(
            f"REFUSE: {PHASE_B_DIR} must be empty/absent during Phase A "
            "(no GT access).",
            file=sys.stderr,
        )
        return 4
    if not MANIFEST.is_file():
        print(f"missing {MANIFEST}", file=sys.stderr)
        return 2

    from core import cv_intelligence as ci
    from core.cv_docpick_import import (
        CV_IMPORT_BUDGET_COLD_S,
        CV_IMPORT_BUDGET_WARM_S,
        DEFAULT_LLM_BASE,
        DEFAULT_MODEL,
        CvImportError,
        import_cv_docpick,
    )

    # Fail closed if productive path lost Docpick.
    if "import_cv_docpick" not in Path(ci.__file__).read_text(encoding="utf-8"):
        print("productive path missing import_cv_docpick", file=sys.stderr)
        return 3

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if manifest.get("gt_not_loaded") is not True:
        print("manifest.gt_not_loaded must be true", file=sys.stderr)
        return 2
    if len(manifest.get("documents") or []) != 50:
        print(f"expected 50 documents, got {len(manifest.get('documents') or [])}", file=sys.stderr)
        return 2

    _verify_pdf_hashes(manifest)
    print("PDF SHA-256 manifest: 50/50 verified", flush=True)

    PRED_DIR.mkdir(parents=True, exist_ok=True)
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
    except Exception:  # noqa: BLE001
        commit = ""

    model_path = Path(DEFAULT_MODEL)
    freeze = {
        "seal_type": "PARSER_CONFIG_SCORER_FREEZE_BLIND_DE_EN_V2_NV3",
        "test_type": "INDEPENDENT_BLIND_DE_EN_NV3_50",
        "disclaimer": (
            "Independent synthetic NV3 Phase A. No GT loaded. "
            "Not a 99% claim until Phase B seal+score."
        ),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "git_commit": commit,
        "round7_baseline_commit": "bb560e4f3cab6cfbfd24aba91c4df855d72a9ee2",
        "det_fallback": False,
        "productive_import": "core.cv_docpick_import.import_cv_docpick",
        "llm": {
            "base_url": DEFAULT_LLM_BASE,
            "model_path": DEFAULT_MODEL,
            "model_sha256": _sha256_file(model_path) if model_path.is_file() else None,
            "temperature": 0.0,
            "max_tokens": int(os.environ.get("KARRIEREKRAKE_CV_LLM_MAX_TOKENS", "2048")),
            "schema_strip_default": os.environ.get("KARRIEREKRAKE_CV_SCHEMA_STRIP", "0"),
            "n_ctx_server_expected": 4096,
        },
        "runtime_budget_s": {
            "warm": CV_IMPORT_BUDGET_WARM_S,
            "cold": CV_IMPORT_BUDGET_COLD_S,
        },
        "file_sha256": {
            "core/cv_docpick_import.py": _sha256_file(ROOT / "core/cv_docpick_import.py"),
            "core/cv_intelligence.py": _sha256_file(ROOT / "core/cv_intelligence.py"),
            "scripts/holdout_scorer_v3_1_date_norm.py": _sha256_file(
                ROOT / "scripts/holdout_scorer_v3_1_date_norm.py"
            ),
            "scripts/holdout_scorer_v3_complete_gt.py": _sha256_file(
                ROOT / "scripts/holdout_scorer_v3_complete_gt.py"
            ),
            "scripts/holdout_scorer_v2.py": _sha256_file(
                ROOT / "scripts/holdout_scorer_v2.py"
            ),
        },
        "manifest_sha256": _sha256_file(MANIFEST),
        "supplier_pdf_manifest_sha256": _sha256_file(SUPPLIER_MANIFEST),
        "gt_not_loaded": True,
    }
    _write_utf8(FREEZE, json.dumps(freeze, indent=2) + "\n")

    preds: list[dict] = []
    timings: dict[str, float] = {}
    t0 = time.perf_counter()
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0
    n_ok = 0
    force = "--force" in sys.argv

    for meta in manifest["documents"]:
        pdf = ROOT / meta["path"]
        key = f"{meta['corpus_id']}__{meta['id']}"
        outp = PRED_DIR / f"{key}.json"
        # Resume only incomplete runs: never re-extract a sealed prediction.
        if outp.is_file() and not force:
            try:
                existing = json.loads(outp.read_text(encoding="utf-8"))
                if not existing.get("tech_error"):
                    blob = outp.read_bytes()
                    preds.append(
                        {
                            "id": meta["id"],
                            "lang": meta["lang"],
                            "pdf": meta["path"],
                            "pdf_sha256": meta.get("pdf_sha256"),
                            "prediction_file": str(outp.relative_to(ROOT)),
                            "sha256": hashlib.sha256(blob).hexdigest(),
                            "elapsed_s": 0.0,
                            "ok": True,
                            "resumed": True,
                        }
                    )
                    n_ok += 1
                    timings[meta["id"]] = 0.0
                    print(f"{key} skip-existing (exactly-once)", flush=True)
                    continue
            except Exception:  # noqa: BLE001
                pass

        s = time.perf_counter()
        try:
            if not pdf.is_file():
                raise CvImportError("file_missing", str(pdf))
            pred = import_cv_docpick(pdf)
            pred["blind_corpus_id"] = meta["corpus_id"]
            pred["blind_doc_id"] = meta["id"]
            pred["blind_lang"] = meta["lang"]
            pred["pdf_sha256"] = meta.get("pdf_sha256")
            ok = True
            n_ok += 1
        except Exception as exc:  # noqa: BLE001
            pred = {
                "pipeline": "docpick_qwen35_4b",
                "tech_error": f"{type(exc).__name__}: {exc}",
                "blind_corpus_id": meta["corpus_id"],
                "blind_doc_id": meta["id"],
                "blind_lang": meta["lang"],
                "pdf_sha256": meta.get("pdf_sha256"),
            }
            ok = False
        elapsed = time.perf_counter() - s
        timings[meta["id"]] = elapsed
        peak = max(peak, resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0)
        blob = json.dumps(pred, ensure_ascii=False, indent=2) + "\n"
        _write_utf8(outp, blob)
        preds.append(
            {
                "id": meta["id"],
                "lang": meta["lang"],
                "pdf": meta["path"],
                "pdf_sha256": meta.get("pdf_sha256"),
                "prediction_file": str(outp.relative_to(ROOT)),
                "sha256": hashlib.sha256(blob.encode("utf-8")).hexdigest(),
                "elapsed_s": elapsed,
                "ok": ok,
            }
        )
        print(f"{key} ok={ok} {elapsed:.1f}s", flush=True)

    wall = time.perf_counter() - t0
    measured = [p["elapsed_s"] for p in preds if p.get("elapsed_s")]
    measured_sorted = sorted(measured)
    warm_ids = [p["id"] for p in preds[1:] if p["ok"] and timings.get(p["id"], 0) > 0]
    warm_avg = (
        sum(timings[i] for i in warm_ids) / len(warm_ids) if warm_ids else None
    )
    cold_s = next((p["elapsed_s"] for p in preds if p.get("elapsed_s")), None)
    seal = {
        "seal_type": "PHASE_A_BLIND_DE_EN_V2_NV3",
        "test_type": "INDEPENDENT_BLIND_DE_EN_NV3_50",
        "disclaimer": (
            "Phase A sealed predictions only. GT not loaded. "
            "Await PHASE_B_SOLUTIONS.zip. Not a 99% claim."
        ),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "parser_freeze": freeze,
        "gt_not_loaded": True,
        "n_documents": len(preds),
        "n_ok": n_ok,
        "predictions": preds,
        "performance": {
            "wall_s": wall,
            "avg_s_per_cv": (sum(measured) / len(measured)) if measured else None,
            "p95_s": (
                measured_sorted[int(0.95 * len(measured_sorted)) - 1]
                if measured_sorted
                else None
            ),
            "peak_rss_mb": peak,
            "cold_s": cold_s,
            "warm_avg_s": warm_avg,
            "per_doc_s": timings,
            "budget_warm_s": CV_IMPORT_BUDGET_WARM_S,
            "budget_cold_s": CV_IMPORT_BUDGET_COLD_S,
            "warm_within_budget": bool(
                warm_avg is not None and warm_avg <= CV_IMPORT_BUDGET_WARM_S
            ),
            "hardware_note": "Agent-VM Xeon 4CPU ~15GB — not i3/8GB target device",
        },
    }
    seal_text = json.dumps(seal, indent=2) + "\n"
    _write_utf8(SEAL, seal_text)
    seal_hash = hashlib.sha256(seal_text.encode("utf-8")).hexdigest()
    print(json.dumps(seal["performance"], indent=2), flush=True)
    print(f"Wrote {SEAL} n_ok={n_ok}/{len(preds)} seal_sha256={seal_hash}", flush=True)
    return 0 if n_ok == len(preds) == 50 else 1


if __name__ == "__main__":
    raise SystemExit(main())
