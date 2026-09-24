#!/usr/bin/env python3
"""Blind DE/EN v2 Phase A — sealed extract (GT must stay unread).

Stops with exit 2 until a NEW independent corpus is provided under
tests/docpick_blind_de_en_v2/ (see README.md). Never reuses known CVs.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "tests" / "docpick_blind_de_en_v2"
MANIFEST = OUT / "EXTRACTION_MANIFEST_PDF_ONLY.json"
PDF_DIR = OUT / "phase_a_pdfs"


def main() -> int:
    if not MANIFEST.is_file() or not PDF_DIR.is_dir() or not any(PDF_DIR.glob("*.pdf")):
        print(
            "Blind DE/EN v2: kein neuer Datensatz.\n"
            f"Erwarte Manifest {MANIFEST.relative_to(ROOT)} und PDFs in "
            f"{PDF_DIR.relative_to(ROOT)}/.\n"
            "Siehe tests/docpick_blind_de_en_v2/README.md — bekannte CVs nicht "
            "als Blindkorpus wiederverwenden. Bitte ≥20 DE/EN-CVs mit voller "
            "V3-GT liefern.",
            file=sys.stderr,
        )
        return 2
    print(
        "Manifest gefunden — implementiere/run sealed extract analog zu "
        "run_docpick_blind_de_en_v1_sealed_extract.py (noch nicht verdrahtet, "
        "weil Datensatz aussteht).",
        file=sys.stderr,
    )
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
