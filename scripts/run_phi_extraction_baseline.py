#!/usr/bin/env python3
"""Measure CV extraction baseline (deterministic vs Phi) with field metrics.

Writes machine-readable JSON under artifacts/phi_extraction/.

Usage:
  python scripts/run_phi_extraction_baseline.py
  python scripts/run_phi_extraction_baseline.py --phi
  python scripts/run_phi_extraction_baseline.py --both --json artifacts/phi_extraction/baseline.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from core.cv_metrics import aggregate, classify_failures  # noqa: E402
from core.cv_parser import import_cv  # noqa: E402
from run_cv_sollwerte_corpus import PDFS, SOLL, CORPUS, parse_sollwerte  # noqa: E402


def _run_mode(*, phi: bool, extractor_path: str = "current_pypdf") -> dict[str, Any]:
    soll = parse_sollwerte(SOLL)
    docs = []
    t0 = time.perf_counter()
    for name in PDFS:
        path = CORPUS / name
        exp = soll.get(name)
        if not path.is_file() or not exp:
            continue
        started = time.perf_counter()
        parsed = import_cv(path, guenther_enabled=phi)
        elapsed = time.perf_counter() - started
        phi_inv = bool(parsed.get("phi_invoked")) or (
            parsed.get("intelligence_status") == "phi_invoked"
        )
        dm = classify_failures(
            name,
            parsed,
            exp,
            phi_involved=phi_inv,
            extractor_path=extractor_path + ("+phi" if phi else "+deterministic"),
        )
        dm.elapsed_s = elapsed
        docs.append(dm)
    metrics = aggregate(docs)
    metrics["mode"] = "phi" if phi else "deterministic"
    metrics["wall_s"] = time.perf_counter() - t0
    metrics["extractor_path"] = extractor_path
    return metrics


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phi", action="store_true", help="Run with Guenther/Phi enabled")
    ap.add_argument("--both", action="store_true", help="Run deterministic and Phi")
    ap.add_argument(
        "--json",
        type=Path,
        default=ROOT / "artifacts" / "phi_extraction" / "baseline.json",
    )
    args = ap.parse_args()
    out: dict[str, Any] = {"schema_version": 1, "corpus": "CV_Parser_Sollwerte_Vollstaendig"}
    if args.both:
        out["deterministic"] = _run_mode(phi=False)
        out["phi"] = _run_mode(phi=True)
    elif args.phi:
        out["phi"] = _run_mode(phi=True)
    else:
        out["deterministic"] = _run_mode(phi=False)

    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    def _line(label: str, m: dict[str, Any]) -> None:
        c = m["counts"]
        print(
            f"{label}: perfect={m['perfect_documents']}/{m['documents']} "
            f"acc={m['field_accuracy']:.4f} P={m['precision']:.4f} R={m['recall']:.4f} "
            f"F1={m['f1']:.4f} "
            f"ok={c['correct']} wrong={c['wrong']} miss={c['missing']} "
            f"hallu={c['hallucinated']} wcat={c['wrong_category']} "
            f"t={m['wall_s']:.1f}s"
        )

    if "deterministic" in out:
        _line("DET", out["deterministic"])
    if "phi" in out:
        _line("PHI", out["phi"])
    print(f"wrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
