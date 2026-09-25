#!/usr/bin/env python3
"""Blind DE/EN v3 Phase B — score sealed predictions once (requires solutions)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "tests" / "docpick_blind_de_en_v3"
SEAL = CORPUS / "PHASE_A_EXTRACTION_SEAL.json"
SOLUTIONS = CORPUS / "phase_b_solutions" / "SOLUTION_SHEET.json"


def main() -> int:
    if not SEAL.is_file():
        print("No Phase A seal — run extract after corpus delivery.", file=sys.stderr)
        return 2
    if not SOLUTIONS.is_file():
        print(
            "PHASE_B_SOLUTIONS missing (need SOLUTION_SHEET.json). "
            "Deliver after Phase A seal only.",
            file=sys.stderr,
        )
        return 2
    print(
        "Solutions present. Score with COMPLETE_GT_ONLY_V3_1_DATE_NORM "
        "exactly once (mirror run_docpick_blind_de_en_v2_sealed_score.py)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
