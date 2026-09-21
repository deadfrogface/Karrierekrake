"""NEXT-06 — Real Windows black-box human E2E (packaged EXE + UIA).

HARD RULES
==========
- Do NOT import Karrierekrake application modules (core/desktop/integrations)
  from this package for final acceptance.
- Synthetic offline suite lives in ``tests/e2e`` — it is NOT real acceptance.
- Final acceptance drives the packaged EXE via pywinauto (UIA backend).

Evidence classes
----------------
SYNTHETIC_OFFLINE_E2E_REGRESSION  → tests/e2e (KEEP; not product acceptance)
REAL_WINDOWS_BLACKBOX_ACCEPTANCE → this package (Windows + EXE required)
"""

from __future__ import annotations

EVIDENCE_CLASS = "real_windows_blackbox_human_e2e"
SCHEMA_VERSION = "1.0.0"

# Binding: never restore "OVERALL PRODUCT E2E PASS" from synthetic alone.
FORBIDDEN_CLAIMS = (
    "OVERALL PRODUCT E2E PASS",
    "REAL PRODUCT ACCEPTANCE READY: YES",
)

SYNTHETIC_SUITE_PATH = "tests/e2e"
SYNTHETIC_LABEL = "SYNTHETIC / OFFLINE E2E REGRESSION SUITE"

__all__ = [
    "EVIDENCE_CLASS",
    "SCHEMA_VERSION",
    "FORBIDDEN_CLAIMS",
    "SYNTHETIC_SUITE_PATH",
    "SYNTHETIC_LABEL",
]
