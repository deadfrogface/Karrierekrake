"""Full-product E2E / chaos megapass — synthetic fixtures only, no real network."""

from __future__ import annotations

SCHEMA_VERSION = "1.0.0"
FACTORY_SEED = 45_001
E2E_MARKER = "e2e"

__all__ = ["SCHEMA_VERSION", "FACTORY_SEED", "E2E_MARKER"]
