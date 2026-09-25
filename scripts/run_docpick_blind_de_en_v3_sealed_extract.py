#!/usr/bin/env python3
"""Blind DE/EN v3 Phase A — seal predictions WITHOUT ground truth.

Exits 2 if the ≥50 PDF corpus is not installed.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "tests" / "docpick_blind_de_en_v3"
PDF_DIR = CORPUS / "phase_a_pdfs"
MANIFEST = CORPUS / "PDF_SHA256_MANIFEST.json"
SOLUTIONS = CORPUS / "phase_b_solutions"


def main() -> int:
    if SOLUTIONS.exists() and any(SOLUTIONS.iterdir()):
        print(
            "REFUSING Phase A: phase_b_solutions/ must be empty (GT leakage guard).",
            file=sys.stderr,
        )
        return 3
    pdfs = sorted(PDF_DIR.glob("*.pdf")) if PDF_DIR.is_dir() else []
    if len(pdfs) < 50 or not MANIFEST.is_file():
        print(
            "BLIND v3 corpus missing. Need ≥50 unseen DE/EN PDFs under "
            f"{PDF_DIR} plus {MANIFEST.name}. "
            "See tests/docpick_blind_de_en_v3/README.md",
            file=sys.stderr,
        )
        return 2
    print(
        f"Corpus present ({len(pdfs)} PDFs). Wire extract like v2 "
        "(run_docpick_blind_de_en_v2_sealed_extract.py) after freeze."
    )
    # Intentionally do not extract here until freeze commit is recorded and
    # operator confirms corpus is unseen.
    meta = {
        "status": "READY_TO_EXTRACT",
        "n_pdfs": len(pdfs),
        "note": "Call operator to confirm freeze + start extract on this corpus.",
    }
    (CORPUS / "PHASE_A_READY.json").write_text(
        json.dumps(meta, indent=2) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
