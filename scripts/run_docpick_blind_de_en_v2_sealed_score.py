#!/usr/bin/env python3
"""Blind DE/EN v2 Phase B — verify seal then score (no parser changes)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "tests" / "docpick_blind_de_en_v2"
SEAL = OUT / "PHASE_A_EXTRACTION_SEAL.json"
GT = OUT / "phase_b_solutions" / "expected_results_full_v3.json"


def main() -> int:
    if not SEAL.is_file():
        print(
            "Blind DE/EN v2 Phase B: kein Seal.\n"
            "Zuerst Phase A mit neuem Korpus (siehe README.md).",
            file=sys.stderr,
        )
        return 2
    if not GT.is_file():
        print(f"fehlende GT: {GT}", file=sys.stderr)
        return 2
    print(
        "Seal+GT vorhanden — Score analog zu "
        "run_docpick_blind_de_en_v1_sealed_score.py verdrahten nach Datenlieferung.",
        file=sys.stderr,
    )
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
