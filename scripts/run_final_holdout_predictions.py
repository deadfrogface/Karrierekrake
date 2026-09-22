#!/usr/bin/env python3
"""Final Holdout — Phase A: blind sealed predictions.

Reads ONLY: tests/final_holdout/cvs/
Must NOT read: tests/final_holdout/expected_results.json

Usage:
  python scripts/run_final_holdout_predictions.py
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import resource
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

HOLDOUT = ROOT / "tests" / "final_holdout"
CVS = HOLDOUT / "cvs"
OUT = ROOT / "artifacts" / "final_holdout"
PRED_DIR = OUT / "frozen_predictions"
META_PATH = OUT / "FROZEN_METADATA.json"
HASHES_PATH = OUT / "FROZEN_HASHES.json"
SEAL_MARKER = OUT / "PHASE_A_COMPLETE.json"

FORBIDDEN_NAMES = {
    "expected_results.json",
    "expected_results_full.json",
    "solution_sheet.csv",
}


def _refuse_gt() -> None:
    gt = HOLDOUT / "expected_results.json"
    if gt.is_file():
        # Existence is OK for Phase B later; Phase A must never open it.
        pass


def _open_guard(path: Path, mode: str = "r", **kwargs: Any):
    name = path.name.lower()
    if name in {n.lower() for n in FORBIDDEN_NAMES}:
        raise RuntimeError(
            f"Phase A leakage guard: refusing to open ground-truth file {path}"
        )
    return open(path, mode, **kwargs)


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


def _peak_rss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def _list_cvs() -> list[Path]:
    if not CVS.is_dir():
        raise SystemExit(
            f"Missing {CVS}. Place 30–50 holdout CVs there before running Phase A."
        )
    files = sorted(
        p
        for p in CVS.iterdir()
        if p.is_file() and p.suffix.lower() in {".pdf", ".docx", ".txt", ".rtf", ".odt"}
    )
    if len(files) < 1:
        raise SystemExit(f"No CV files found under {CVS}")
    return files


def run_phase_a() -> dict[str, Any]:
    _refuse_gt()
    # Hard guard: ensure helper never opens GT via this module
    gt_path = HOLDOUT / "expected_results.json"
    if gt_path.is_file():
        try:
            _open_guard(gt_path)
            raise SystemExit("leakage guard failed: opened GT")
        except RuntimeError:
            pass

    from core.cv_parser import import_cv

    files = _list_cvs()
    OUT.mkdir(parents=True, exist_ok=True)
    PRED_DIR.mkdir(parents=True, exist_ok=True)

    # Clear previous predictions for a clean seal
    for old in PRED_DIR.glob("*"):
        if old.is_file():
            old.unlink()

    git = _git_meta()
    t0 = time.perf_counter()
    rss0 = _peak_rss_mb()
    per_doc: list[dict[str, Any]] = []
    file_hashes: dict[str, str] = {}

    for path in files:
        # Filename must not steer extraction — pass path only, no GT
        st = time.perf_counter()
        parsed = import_cv(path, guenther_enabled=False)
        elapsed = time.perf_counter() - st
        assert parsed.get("phi_extract_call_count", 0) == 0
        assert parsed.get("phi_invoked", False) is False
        rec = {
            "document": path.name,
            "elapsed_s": elapsed,
            "prediction": _serialize(parsed),
        }
        out_path = PRED_DIR / f"{path.stem}.json"
        payload = json.dumps(rec, ensure_ascii=False, indent=2, sort_keys=True)
        out_path.write_text(payload + "\n", encoding="utf-8")
        file_hashes[str(out_path.relative_to(OUT))] = _sha256_bytes(
            (payload + "\n").encode("utf-8")
        )
        per_doc.append(
            {
                "document": path.name,
                "elapsed_s": elapsed,
                "cv_sha256": _sha256_file(path),
            }
        )

    wall = time.perf_counter() - t0
    rss1 = _peak_rss_mb()

    # Parser / pipeline identity
    try:
        from core import cv_parser, cv_sections, cv_intelligence

        parser_hash = _sha256_bytes(
            (ROOT / "core" / "cv_parser.py").read_bytes()
            + (ROOT / "core" / "cv_sections.py").read_bytes()
            + (ROOT / "core" / "cv_intelligence.py").read_bytes()
        )
    except Exception:  # noqa: BLE001
        parser_hash = ""

    meta = {
        "phase": "A",
        "protocol": "FINAL_HOLDOUT_V1",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "git": git,
        "pipeline": {
            "name": "DET_parse_cv_text",
            "version": "production_det_only",
            "phi_extract": False,
            "c1_fallback": False,
            "parser_content_sha256": parser_hash,
        },
        "config": {
            "guenther_enabled": False,
            "document_backend": "current",
        },
        "hardware": {
            "platform": platform.platform(),
            "python": sys.version.split()[0],
            "machine": platform.machine(),
            "processor": platform.processor(),
        },
        "performance": {
            "n_documents": len(files),
            "wall_s": wall,
            "avg_s_per_doc": wall / max(len(files), 1),
            "rss_start_mb": rss0,
            "rss_peak_mb": max(rss0, rss1),
        },
        "documents": per_doc,
        "dependencies": {
            "note": "CV import requires no Phi model; optional writer deps unused",
        },
        "warnings": [
            "Historical evaluation artifact protocol.",
            "Not part of the current production extraction path packaging.",
        ],
    }
    META_PATH.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    file_hashes[str(META_PATH.relative_to(OUT))] = _sha256_file(META_PATH)

    hashes_doc = {
        "schema_version": 1,
        "sealed_at_utc": meta["timestamp_utc"],
        "git_commit": git["commit"],
        "git_dirty": git["dirty"],
        "files": [{"path": k, "sha256": v} for k, v in sorted(file_hashes.items())],
        "aggregate_sha256": _sha256_bytes(
            json.dumps(file_hashes, sort_keys=True).encode("utf-8")
        ),
    }
    HASHES_PATH.write_text(
        json.dumps(hashes_doc, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    seal = {
        "phase_a_complete": True,
        "sealed": True,
        "hashes_path": str(
            HASHES_PATH.relative_to(ROOT)
            if HASHES_PATH.is_relative_to(ROOT)
            else HASHES_PATH
        ),
        "n_predictions": len(files),
        "commit": git["commit"],
        "dirty": git["dirty"],
        "timestamp_utc": meta["timestamp_utc"],
        "note": "Do not modify frozen_predictions after sealing. Phase B verifies hashes.",
    }
    SEAL_MARKER.write_text(
        json.dumps(seal, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"Phase A sealed: {len(files)} predictions → {PRED_DIR}")
    print(f"Hashes: {HASHES_PATH}")
    return seal


def main() -> int:
    # Prevent accidental GT import via env misuse
    if os.environ.get("FINAL_HOLDOUT_FORCE_READ_GT") == "1":
        raise SystemExit("Refusing FINAL_HOLDOUT_FORCE_READ_GT in Phase A")
    run_phase_a()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
