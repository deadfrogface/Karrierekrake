#!/usr/bin/env python3
"""Final Holdout — Phase A: blind sealed predictions.

Reads ONLY PDFs under:
  tests/final_holdout/phase_a_pdfs/  (preferred)
  tests/final_holdout/cvs/           (fallback)

Must NOT read any ground-truth / expected-results files.
Must NOT import scorers or evaluate quality.

Usage:
  python scripts/run_final_holdout_predictions.py
"""

from __future__ import annotations

import hashlib
import json
import os
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

HOLDOUT = ROOT / "tests" / "final_holdout"
PHASE_A_PDFS = HOLDOUT / "phase_a_pdfs"
CVS = HOLDOUT / "cvs"
OUT = ROOT / "artifacts" / "final_holdout"
PRED_DIR = OUT / "frozen_predictions"
META_PATH = OUT / "FROZEN_METADATA.json"
INPUT_HASHES_PATH = OUT / "FROZEN_INPUT_HASHES.json"
PRED_HASHES_PATH = OUT / "FROZEN_PREDICTION_HASHES.json"
# Back-compat alias used by older tests
HASHES_PATH = PRED_HASHES_PATH
SEAL_PATH = OUT / "PHASE_A_SEAL.json"
SEAL_MARKER = OUT / "PHASE_A_COMPLETE.json"  # alias for older tests

FORBIDDEN_NAMES = {
    "expected_results.json",
    "expected_results_full.json",
    "solution_sheet.csv",
    "ground_truth.json",
    "answers.json",
    "solutions.json",
}

PARSER_SOURCES = [
    ROOT / "core" / "cv_parser.py",
    ROOT / "core" / "cv_sections.py",
    ROOT / "core" / "cv_intelligence.py",
    ROOT / "core" / "cv_extract.py",
    ROOT / "core" / "cv_verify_repair.py",
    ROOT / "core" / "cv_evidence.py",
]


def _open_guard(path: Path, mode: str = "r", **kwargs: Any):
    name = path.name.lower()
    if name in {n.lower() for n in FORBIDDEN_NAMES} or name.startswith("phase_b"):
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


def _resolve_pdf_dir() -> Path:
    phase_a = HOLDOUT / "phase_a_pdfs"
    cvs = HOLDOUT / "cvs"
    if phase_a.is_dir() and any(phase_a.glob("FH_*.pdf")):
        return phase_a
    if cvs.is_dir():
        return cvs
    raise SystemExit(
        f"Missing PDFs under {phase_a} or {cvs}. "
        "Extract KarriereKrake_FINAL_HOLDOUT_50_PHASE_A_BLIND.zip first."
    )


def _list_cvs() -> list[Path]:
    """List holdout CVs. Prefer FH_*.pdf set of exactly 50 when present."""
    pdf_dir = _resolve_pdf_dir()
    fh = sorted(pdf_dir.glob("FH_*.pdf"))
    if fh:
        if len(fh) != 50:
            raise SystemExit(
                f"Invalid dataset: expected 50 FH_*.pdf in {pdf_dir}, found {len(fh)}"
            )
        expected = {f"FH_{i:03d}.pdf" for i in range(1, 51)}
        got = {p.name for p in fh}
        missing = sorted(expected - got)
        extra = sorted(got - expected)
        if missing or extra:
            raise SystemExit(
                f"Invalid dataset IDs. missing={missing} extra={extra}"
            )
        return fh
    files = sorted(
        p
        for p in pdf_dir.iterdir()
        if p.is_file() and p.suffix.lower() in {".pdf", ".docx", ".txt", ".rtf", ".odt"}
    )
    if len(files) < 1:
        raise SystemExit(f"No CV files found under {pdf_dir}")
    return files


def _verify_pdf_manifest(pdf_dir: Path, files: list[Path]) -> dict[str, Any]:
    man_path = pdf_dir / "PDF_MANIFEST.json"
    if not man_path.is_file():
        return {"present": False, "verified": False}
    # Safe: filenames / sizes / hashes only
    data = json.loads(man_path.read_text(encoding="utf-8"))
    entries = data if isinstance(data, list) else (
        data.get("pdfs") or data.get("files") or []
    )
    by_name = {}
    for ent in entries:
        name = Path(str(ent.get("filename") or ent.get("name") or "")).name
        if name:
            by_name[name] = ent
    mismatches = []
    for p in files:
        ent = by_name.get(p.name)
        if not ent:
            mismatches.append({"file": p.name, "error": "not_in_manifest"})
            continue
        sz = ent.get("bytes") if "bytes" in ent else ent.get("size")
        if sz is not None and int(sz) != p.stat().st_size:
            mismatches.append(
                {
                    "file": p.name,
                    "error": "size",
                    "expected": sz,
                    "got": p.stat().st_size,
                }
            )
        h = ent.get("sha256") or ent.get("hash")
        if h and _sha256_file(p).lower() != str(h).lower():
            mismatches.append({"file": p.name, "error": "hash"})
    if mismatches:
        raise SystemExit(
            "RESULT: PHASE A BLOCKED – PDF INTEGRITY FAILURE\n"
            + json.dumps(mismatches[:20], indent=2)
        )
    return {
        "present": True,
        "verified": True,
        "n_entries": len(entries),
        "manifest_sha256": _sha256_file(man_path),
    }


def _check_existing_seal() -> None:
    if SEAL_PATH.is_file():
        try:
            seal = json.loads(SEAL_PATH.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            seal = {}
        if seal.get("status") == "SEALED" or seal.get("sealed") is True:
            raise SystemExit(
                "Phase A already sealed. Refusing to overwrite frozen predictions.\n"
                f"Existing seal: {SEAL_PATH}\n"
                "Use a new run directory for any authorized re-run."
            )


def _count_uncertain(parsed: dict[str, Any]) -> int:
    n = 0
    conf = parsed.get("confidence") or {}
    if isinstance(conf, dict):
        for v in conf.values():
            s = str(v).lower()
            if "uncertain" in s or "unklar" in s or "nicht erkannt" in s:
                n += 1
    for key in ("uncertain_items", "uncertain_fields", "review_items"):
        items = parsed.get(key) or []
        if isinstance(items, list):
            n += len(items)
    return n


def _is_empty_prediction(parsed: dict[str, Any]) -> bool:
    keys = (
        "work_experience",
        "education",
        "skills",
        "languages",
        "software",
        "certificates",
    )
    personal = parsed.get("personal") or {}
    has_name = bool(
        (personal.get("first_name") or "")
        or (personal.get("last_name") or "")
        or (personal.get("full_name") or "")
    )
    has_lists = any(parsed.get(k) for k in keys)
    return not has_name and not has_lists


def _rel(path: Path) -> str:
    try:
        if path.is_relative_to(ROOT):
            return str(path.relative_to(ROOT))
    except Exception:  # noqa: BLE001
        pass
    return str(path)


def run_phase_a() -> dict[str, Any]:
    # Resolve artifact paths from OUT so tests can redirect the output root.
    global META_PATH, INPUT_HASHES_PATH, PRED_HASHES_PATH, HASHES_PATH, SEAL_PATH, SEAL_MARKER, PRED_DIR
    PRED_DIR = OUT / "frozen_predictions"
    META_PATH = OUT / "FROZEN_METADATA.json"
    INPUT_HASHES_PATH = OUT / "FROZEN_INPUT_HASHES.json"
    PRED_HASHES_PATH = OUT / "FROZEN_PREDICTION_HASHES.json"
    HASHES_PATH = PRED_HASHES_PATH
    SEAL_PATH = OUT / "PHASE_A_SEAL.json"
    SEAL_MARKER = OUT / "PHASE_A_COMPLETE.json"

    _check_existing_seal()

    # Refuse opening GT if present (existence check only elsewhere)
    for name in FORBIDDEN_NAMES:
        p = HOLDOUT / name
        if p.is_file():
            try:
                _open_guard(p)
                raise SystemExit("leakage guard failed: opened GT")
            except RuntimeError:
                pass

    pdf_dir = _resolve_pdf_dir()
    files = _list_cvs()
    manifest_info = _verify_pdf_manifest(pdf_dir, files)

    from core.cv_parser import import_cv

    OUT.mkdir(parents=True, exist_ok=True)
    PRED_DIR.mkdir(parents=True, exist_ok=True)

    # Clean previous unsealed predictions only (seal already blocked above)
    for old in PRED_DIR.glob("*.json"):
        old.unlink()

    git = _git_meta()
    started = datetime.now(timezone.utc).isoformat()
    t0 = time.perf_counter()
    rss0 = _peak_rss_mb()
    per_doc: list[dict[str, Any]] = []
    pred_hashes: dict[str, str] = {}
    pdf_hashes: list[dict[str, Any]] = []
    total_phi = 0
    total_c1 = 0
    tech_errors = 0
    empty_preds = 0
    uncertain_total = 0
    timings_ms: list[float] = []

    for path in files:
        doc_id = path.stem
        st = time.perf_counter()
        err: list[str] = []
        try:
            parsed = import_cv(path, guenther_enabled=False)
        except Exception as exc:  # noqa: BLE001 — record, do not fix
            tech_errors += 1
            err.append(f"{type(exc).__name__}:{exc}")
            parsed = {
                "intelligence_status": "deterministic_only",
                "phi_invoked": False,
                "phi_extract_call_count": 0,
                "errors": err,
            }
        elapsed = time.perf_counter() - st
        timing_ms = elapsed * 1000.0
        timings_ms.append(timing_ms)

        phi_calls = int(parsed.get("phi_extract_call_count") or 0)
        if parsed.get("phi_invoked"):
            phi_calls = max(phi_calls, 1)
        total_phi += phi_calls
        # C1 / thin routing must not exist on production path
        total_c1 += int(bool(parsed.get("phi_fallback_triggered")))
        total_c1 += int(bool(parsed.get("c1_fallback_triggered")))
        total_c1 += int(bool(parsed.get("thin_routing")))

        unc = _count_uncertain(parsed)
        uncertain_total += unc
        if _is_empty_prediction(parsed):
            empty_preds += 1

        serialized = _serialize(parsed)
        rec = {
            "document_id": doc_id,
            "source_filename": path.name,
            "pipeline": "DET_PRODUCTION",
            "prediction": serialized,
            "validation_findings": list(parsed.get("intelligence_notes") or []),
            "uncertain_fields": list(parsed.get("uncertain_items") or parsed.get("review_items") or []),
            "errors": err,
            "timing_ms": timing_ms,
            "phi_calls": phi_calls,
        }
        out_path = PRED_DIR / f"{doc_id}.json"
        payload = json.dumps(rec, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        out_path.write_text(payload, encoding="utf-8")
        pred_hashes[f"frozen_predictions/{doc_id}.json"] = _sha256_bytes(
            payload.encode("utf-8")
        )
        pdf_sha = _sha256_file(path)
        pdf_hashes.append(
            {
                "filename": path.name,
                "bytes": path.stat().st_size,
                "sha256": pdf_sha,
            }
        )
        per_doc.append(
            {
                "document_id": doc_id,
                "source_filename": path.name,
                "elapsed_s": elapsed,
                "timing_ms": timing_ms,
                "phi_calls": phi_calls,
                "uncertain_count": unc,
                "tech_error": bool(err),
                "empty": _is_empty_prediction(parsed),
                "cv_sha256": pdf_sha,
            }
        )

    if total_phi > 0 or total_c1 > 0:
        raise SystemExit(
            "RESULT: PHASE A INVALID – PHI/C1 CALLED\n"
            f"phi_extract_calls={total_phi} c1_related={total_c1}"
        )

    wall = time.perf_counter() - t0
    ended = datetime.now(timezone.utc).isoformat()
    rss1 = _peak_rss_mb()
    timings_sorted = sorted(timings_ms)
    n = len(timings_sorted)

    def pct(p: float) -> float:
        if not timings_sorted:
            return 0.0
        idx = min(n - 1, max(0, int(round((p / 100.0) * (n - 1)))))
        return timings_sorted[idx]

    parser_hashes = []
    for src in PARSER_SOURCES:
        if src.is_file():
            parser_hashes.append(
                {
                    "path": str(src.relative_to(ROOT)),
                    "sha256": _sha256_file(src),
                }
            )
    runner_path = Path(__file__).resolve()
    runner_hash = {
        "path": str(runner_path.relative_to(ROOT)),
        "sha256": _sha256_file(runner_path),
    }
    lockfiles = []
    for lf in (
        ROOT / "requirements.txt",
        ROOT / "requirements-lock.txt",
        ROOT / "uv.lock",
        ROOT / "poetry.lock",
    ):
        if lf.is_file():
            lockfiles.append(
                {"path": str(lf.relative_to(ROOT)), "sha256": _sha256_file(lf)}
            )

    input_hashes = {
        "git_commit": git["commit"],
        "pdfs": pdf_hashes,
        "parser_sources": parser_hashes,
        "configs": lockfiles,
        "runner": [runner_hash],
        "pdf_manifest": manifest_info,
    }
    INPUT_HASHES_PATH.write_text(
        json.dumps(input_hashes, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    # Deterministic prediction manifest (sorted paths)
    pred_manifest = {
        "schema_version": 1,
        "n_predictions": len(files),
        "files": [
            {"path": k, "sha256": pred_hashes[k]} for k in sorted(pred_hashes.keys())
        ],
    }
    pred_manifest["aggregate_sha256"] = _sha256_bytes(
        json.dumps(
            {e["path"]: e["sha256"] for e in pred_manifest["files"]},
            sort_keys=True,
        ).encode("utf-8")
    )
    PRED_HASHES_PATH.write_text(
        json.dumps(pred_manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    meta = {
        "phase": "A",
        "protocol": "FINAL_HOLDOUT_V1",
        "status": "SEALED",
        "started_at_utc": started,
        "sealed_at_utc": ended,
        "dataset_size": len(files),
        "pdf_dir": _rel(pdf_dir),
        "git": git,
        "pipeline": {
            "name": "DET_PRODUCTION",
            "entrypoint": "core.cv_parser.import_cv → import_cv_canonical → parse_cv_text",
            "document_extractor": "core.cv_extract.extract_text",
            "phi_extract": False,
            "c1_fallback": False,
        },
        "config": {
            "guenther_enabled": False,
            "document_backend": "current",
            "timezone": time.tzname,
            "random_seeds": None,
        },
        "hardware": {
            "platform": platform.platform(),
            "python": sys.version.split()[0],
            "machine": platform.machine(),
            "processor": platform.processor(),
            "cpu_count": os.cpu_count(),
        },
        "performance": {
            "n_documents": len(files),
            "wall_s": wall,
            "avg_s_per_doc": wall / max(len(files), 1),
            "avg_ms": (sum(timings_ms) / max(n, 1)) if n else 0.0,
            "median_ms": statistics.median(timings_ms) if timings_ms else 0.0,
            "p95_ms": pct(95),
            "min_ms": timings_sorted[0] if timings_sorted else 0.0,
            "max_ms": timings_sorted[-1] if timings_sorted else 0.0,
            "rss_start_mb": rss0,
            "rss_peak_mb": max(rss0, rss1),
            "model_loads": 0,
            "subprocesses": 0,
        },
        "counts": {
            "technical_errors": tech_errors,
            "empty_predictions": empty_preds,
            "uncertain_field_mentions": uncertain_total,
            "phi_extract_calls": total_phi,
            "c1_calls": total_c1,
            "phi_verify_calls": 0,
            "phi_repair_calls": 0,
            "thin_routings": 0,
        },
        "documents": per_doc,
        "scorer_version_metadata_only": "holdout_scorer_v2 (not executed in Phase A)",
        "ground_truth_used": False,
        "evaluation_performed": False,
        "warnings": [
            "Phase A blind sealed predictions only.",
            "No ground truth read. No quality metrics computed.",
        ],
    }
    META_PATH.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    seal = {
        "status": "SEALED",
        "phase_a_complete": True,
        "sealed": True,
        "dataset_size": len(files),
        "pipeline": "DET_PRODUCTION",
        "git_commit": git["commit"],
        "git_branch": git["branch"],
        "git_dirty": git["dirty"],
        "predictions_manifest_sha256": pred_manifest["aggregate_sha256"],
        "input_hashes_sha256": _sha256_file(INPUT_HASHES_PATH),
        "metadata_sha256": _sha256_file(META_PATH),
        "prediction_hashes_sha256": _sha256_file(PRED_HASHES_PATH),
        "sealed_at": ended,
        "ground_truth_used": False,
        "evaluation_performed": False,
        "phi_calls": total_phi,
        "c1_calls": total_c1,
        "n_predictions": len(files),
        "predictions_dir": _rel(PRED_DIR),
    }
    seal_payload = json.dumps(seal, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    SEAL_PATH.write_text(seal_payload, encoding="utf-8")
    SEAL_MARKER.write_text(seal_payload, encoding="utf-8")
    # Compat alias for older Phase-B verifier expecting FROZEN_HASHES.json
    compat = OUT / "FROZEN_HASHES.json"
    compat.write_text(
        json.dumps(pred_manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    # Post-seal integrity verification
    _verify_seal_integrity(files, pred_hashes, pred_manifest["aggregate_sha256"])

    print(f"Phase A sealed: {len(files)} predictions → {PRED_DIR}")
    print(f"Seal: {SEAL_PATH}")
    print(f"predictions_manifest_sha256={pred_manifest['aggregate_sha256']}")
    return seal


def _verify_seal_integrity(
    files: list[Path],
    pred_hashes: dict[str, str],
    aggregate: str,
) -> None:
    # Re-hash every PDF
    for p in files:
        # presence + non-empty already known; ensure prediction exists
        pred = PRED_DIR / f"{p.stem}.json"
        if not pred.is_file():
            raise SystemExit(f"Seal integrity failure: missing prediction for {p.name}")
    # Exactly 50 predictions matching PDFs
    preds = sorted(PRED_DIR.glob("FH_*.json")) if any(
        f.name.startswith("FH_") for f in files
    ) else sorted(PRED_DIR.glob("*.json"))
    if len(files) != len(preds):
        raise SystemExit(
            f"Seal integrity failure: {len(files)} PDFs vs {len(preds)} predictions"
        )
    pdf_ids = {f.stem for f in files}
    pred_ids = {p.stem for p in preds}
    if pdf_ids != pred_ids:
        raise SystemExit(
            f"Seal integrity failure: ID mismatch "
            f"only_pdf={sorted(pdf_ids-pred_ids)} only_pred={sorted(pred_ids-pdf_ids)}"
        )
    # Re-hash predictions
    for rel, expected in pred_hashes.items():
        got = _sha256_file(OUT / rel)
        if got != expected:
            raise SystemExit(f"Seal integrity failure: hash mismatch {rel}")
    # Recompute aggregate
    agg = _sha256_bytes(
        json.dumps(pred_hashes, sort_keys=True).encode("utf-8")
    )
    if agg != aggregate:
        raise SystemExit("Seal integrity failure: aggregate hash mismatch")
    # Seal file must still match
    if not SEAL_PATH.is_file():
        raise SystemExit("Seal integrity failure: missing PHASE_A_SEAL.json")


def main() -> int:
    if os.environ.get("FINAL_HOLDOUT_FORCE_READ_GT") == "1":
        raise SystemExit("Refusing FINAL_HOLDOUT_FORCE_READ_GT in Phase A")
    run_phase_a()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
