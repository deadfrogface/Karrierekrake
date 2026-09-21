"""SYNTHETIC / OFFLINE E2E REGRESSION SUITE

This package is the **synthetic offline product E2E / chaos regression** suite
(fake providers, isolated AppData, offscreen Qt).

It is valuable and must stay green.

It is **NOT** full real-product acceptance.
It is **NOT** Windows black-box EXE acceptance.
It is **NOT** live Gmail/Calendar/Maps/ATS proof.

Real acceptance: ``tests/blackbox`` + ``scripts/run_windows_blackbox_e2e.py`` (NEXT-06).
Do **not** restore ``OVERALL PRODUCT E2E PASS`` from synthetic alone.
"""

from __future__ import annotations

SCHEMA_VERSION = "1.0.0"
FACTORY_SEED = 45_001
E2E_MARKER = "e2e"
EVIDENCE_CLASS = "synthetic_offline_e2e_regression"
SUITE_LABEL = "SYNTHETIC / OFFLINE E2E REGRESSION SUITE"

__all__ = [
    "SCHEMA_VERSION",
    "FACTORY_SEED",
    "E2E_MARKER",
    "EVIDENCE_CLASS",
    "SUITE_LABEL",
]
