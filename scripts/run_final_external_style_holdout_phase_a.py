#!/usr/bin/env python3
"""FINAL_EXTERNAL_STYLE_HOLDOUT — Phase A blind prediction runner (generic).

Expects 50–100 PDFs in a directory. Ground truth is NOT read in Phase A.
No assumptions about filenames, document IDs, language, layout, page count,
section order, persons, or known software/skill names.

Usage (when a new unknown dataset is available):

  python scripts/run_final_external_style_holdout_phase_a.py \\
      --pdf-dir /path/to/pdfs \\
      --out-dir artifacts/final_external_style_holdout

Without --pdf-dir / without PDFs the runner exits ready but produces no predictions.

Phase B evaluation is a separate script/step and must not run here.
Frozen seals must not be overwritten.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import resource
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DATASET_ID = "FINAL_EXTERNAL_STYLE_HOLDOUT"
PROTOCOL = "FINAL_EXTERNAL_STYLE_HOLDOUT_PHASE_A"
MIN_PDFS = 50
MAX_PDFS = 100

PARSER_SOURCES = [
    ROOT / "core" / "cv_parser.py",
    ROOT / "core" / "cv_sections.py",
    ROOT / "core" / "cv_intelligence.py",
    ROOT / "core" / "cv_extract.py",
    ROOT / "core" / "cv_verify_repair.py",
    ROOT / "core" / "cv_evidence.py",
]

FORBIDDEN_NAMES = {
    "expected_results.json",
    "expected_results_full.json",
    "solution_sheet.csv",
    "ground_truth.json",
    "answers.json",
    "solutions.json",
    "precheck_report.json",
    "PRECHECK_REPORT.json",
}


def _git_meta() -> dict[str, Any]:
    def run(args: list[str]) -> str:
        try:
            return subprocess.check_output(args, cwd=ROOT, text=True).strip()
        except Exception:  # noqa: BLE001
            return ""

    dirty = run(["git", "status", "--porcelain"])
    return {
        "commit": run(["git", "rev-parse", "HEAD"]),
        "branch": run(["git", "rev-parse", "--abbrev-ref", "HEAD"]),
        "dirty": bool(dirty),
        "dirty_summary": dirty[:2000],
    }


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _parser_source_hash() -> str:
    h = hashlib.sha256()
    for p in PARSER_SOURCES:
        if p.is_file():
            h.update(p.read_bytes())
            h.update(b"\0")
    return h.hexdigest()


def _peak_rss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def _serialize(parsed: dict[str, Any]) -> dict[str, Any]:
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


def _refuse_gt(path: Path) -> None:
    name = path.name.lower()
    if name in {n.lower() for n in FORBIDDEN_NAMES} or name.startswith("phase_b"):
        raise RuntimeError(f"Phase A leakage guard: refusing {path}")


def _list_pdfs(pdf_dir: Path) -> list[Path]:
    files = sorted(
        p for p in pdf_dir.iterdir() if p.is_file() and p.suffix.lower() == ".pdf"
    )
    return files


def _doc_id_for(path: Path) -> str:
    """Content-addressed ID — independent of original filename conventions."""
    digest = _sha256_file(path)[:12]
    return f"EXT_{digest}"


def _write_pdf_manifest(pdf_dir: Path, files: list[Path], out: Path) -> dict[str, Any]:
    entries = []
    for p in files:
        entries.append(
            {
                "filename": p.name,
                "bytes": p.stat().st_size,
                "sha256": _sha256_file(p),
                "doc_id": _doc_id_for(p),
            }
        )
    payload = {
        "dataset_id": DATASET_ID,
        "n": len(entries),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "pdfs": entries,
    }
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload


def _import_one(path: Path) -> tuple[dict[str, Any], list[str]]:
    from core.cv_parser import import_cv

    err: list[str] = []
    try:
        parsed = import_cv(path, guenther_enabled=False)
    except Exception as exc:  # noqa: BLE001
        err.append(f"{type(exc).__name__}:{exc}")
        parsed = {
            "intelligence_status": "deterministic_only",
            "phi_invoked": False,
            "phi_extract_call_count": 0,
            "c1_invoked": False,
            "errors": err,
        }
    return parsed, err


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--pdf-dir",
        type=Path,
        default=None,
        help="Directory with 50–100 blind PDFs (required to generate predictions)",
    )
    ap.add_argument(
        "--out-dir",
        type=Path,
        default=ROOT / "artifacts" / "final_external_style_holdout",
    )
    ap.add_argument(
        "--repeat",
        type=int,
        default=1,
        help="Repeatability runs (default 1; use 2 for seal repeat check)",
    )
    ap.add_argument(
        "--dry-ready",
        action="store_true",
        help="Only verify runner readiness; do not require PDFs",
    )
    args = ap.parse_args(argv)

    out: Path = args.out_dir
    out.mkdir(parents=True, exist_ok=True)
    seal_path = out / "PHASE_A_SEAL.json"
    if seal_path.is_file():
        try:
            existing = json.loads(seal_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            existing = {}
        if existing.get("status") == "SEALED":
            print(
                "RESULT: PHASE A BLOCKED – ALREADY SEALED\n"
                f"Existing seal: {seal_path}"
            )
            return 2

    git = _git_meta()
    parser_hash = _parser_source_hash()
    ready = {
        "result": "FINAL_EXTERNAL_STYLE_HOLDOUT PHASE A RUNNER READY",
        "dataset_id": DATASET_ID,
        "protocol": PROTOCOL,
        "min_pdfs": MIN_PDFS,
        "max_pdfs": MAX_PDFS,
        "parser_commit": git["commit"],
        "parser_source_sha256": parser_hash,
        "evaluation_in_phase_a": False,
        "reads_ground_truth": False,
        "filename_assumptions": False,
        "layout_class_assumptions": False,
        "lora_training": False,
        "phi_production": False,
        "note": (
            "No predictions generated without an unknown blind PDF directory. "
            "Independent 0.99 is NOT claimed by runner readiness."
        ),
    }
    (out / "RUNNER_READY.json").write_text(
        json.dumps(ready, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    if args.dry_ready or args.pdf_dir is None:
        print(json.dumps(ready, indent=2, ensure_ascii=False))
        print(
            "\nRESULT: FINAL_EXTERNAL_STYLE_HOLDOUT PHASE A RUNNER READY – "
            "AWAITING UNKNOWN DATASET"
        )
        return 0

    pdf_dir: Path = args.pdf_dir
    if not pdf_dir.is_dir():
        print(f"RESULT: PHASE A BLOCKED – PDF DIR MISSING: {pdf_dir}")
        return 2

    # Leakage guard: refuse to open GT filenames if present beside PDFs.
    for p in pdf_dir.iterdir():
        if p.is_file():
            try:
                _refuse_gt(p)
            except RuntimeError as exc:
                print(f"RESULT: PHASE A BLOCKED – {exc}")
                return 2

    files = _list_pdfs(pdf_dir)
    if not (MIN_PDFS <= len(files) <= MAX_PDFS):
        print(
            "RESULT: PHASE A BLOCKED – INVALID PDF COUNT\n"
            f"expected {MIN_PDFS}-{MAX_PDFS}, found {len(files)} in {pdf_dir}"
        )
        return 2

    pred_dir = out / "frozen_predictions"
    pred_dir.mkdir(parents=True, exist_ok=True)
    manifest = _write_pdf_manifest(pdf_dir, files, out / "PDF_MANIFEST.json")

    wall_times: list[float] = []
    phi_total = 0
    c1_total = 0
    pred_hashes: dict[str, str] = {}
    input_hashes: dict[str, str] = {}
    t0 = time.perf_counter()

    for run_i in range(max(1, int(args.repeat))):
        run_pred_hashes: dict[str, str] = {}
        for pdf in files:
            doc_id = _doc_id_for(pdf)
            input_hashes[doc_id] = _sha256_file(pdf)
            t_doc = time.perf_counter()
            parsed, err = _import_one(pdf)
            wall_times.append(time.perf_counter() - t_doc)
            phi_total += int(parsed.get("phi_extract_call_count") or 0)
            if parsed.get("phi_invoked"):
                phi_total = max(phi_total, 1)
            c1_total += int(parsed.get("c1_extract_call_count") or 0)
            if parsed.get("c1_invoked"):
                c1_total = max(c1_total, 1)
            payload = {
                "dataset_id": DATASET_ID,
                "doc_id": doc_id,
                "source_filename": pdf.name,
                "source_sha256": input_hashes[doc_id],
                "parser_commit": git["commit"],
                "parser_source_sha256": parser_hash,
                "errors": err,
                "prediction": _serialize(parsed),
            }
            raw = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
            out_path = pred_dir / f"{doc_id}.json"
            if run_i == 0:
                out_path.write_text(raw, encoding="utf-8")
            run_pred_hashes[doc_id] = _sha256_bytes(raw.encode("utf-8"))
        if run_i == 0:
            pred_hashes = run_pred_hashes
        else:
            if run_pred_hashes != pred_hashes:
                print("RESULT: PHASE A BLOCKED – REPEATABILITY MISMATCH")
                return 3

    wall = time.perf_counter() - t0
    meta = {
        "dataset_id": DATASET_ID,
        "protocol": PROTOCOL,
        "n_documents": len(files),
        "parser_commit": git["commit"],
        "parser_branch": git["branch"],
        "parser_source_sha256": parser_hash,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "platform": platform.platform(),
        "python": sys.version,
        "performance": {
            "wall_s": wall,
            "per_doc_s_mean": statistics.mean(wall_times) if wall_times else 0,
            "per_doc_s_median": statistics.median(wall_times) if wall_times else 0,
            "peak_rss_mb": _peak_rss_mb(),
        },
        "phi_calls": phi_total,
        "c1_calls": c1_total,
        "repeat_runs": int(args.repeat),
        "evaluation_performed": False,
        "pdf_manifest_sha256": _sha256_file(out / "PDF_MANIFEST.json"),
    }
    (out / "FROZEN_METADATA.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (out / "FROZEN_INPUT_HASHES.json").write_text(
        json.dumps(input_hashes, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (out / "FROZEN_PREDICTION_HASHES.json").write_text(
        json.dumps(pred_hashes, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    seal = {
        "status": "SEALED",
        "dataset_id": DATASET_ID,
        "protocol": PROTOCOL,
        "parser_commit": git["commit"],
        "parser_source_sha256": parser_hash,
        "n_documents": len(files),
        "phi_calls": phi_total,
        "c1_calls": c1_total,
        "sealed_at": datetime.now(timezone.utc).isoformat(),
        "phase_b_evaluation": False,
        "independent_f1_claimed": False,
        "manifest": {
            "pdf": manifest.get("n"),
            "predictions": len(pred_hashes),
        },
    }
    seal_path.write_text(json.dumps(seal, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (out / "PHASE_A_COMPLETE.json").write_text(
        json.dumps({"complete": True, "seal": str(seal_path)}, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(seal, indent=2, ensure_ascii=False))
    print("RESULT: FINAL_EXTERNAL_STYLE_HOLDOUT PHASE A SEALED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
