"""Hardware tier detection — LIGHT / STANDARD / POWER.

Sole production model is Qwen3.8-27B GSQ-RCO. Insufficient RAM → GUENTHER_UNAVAILABLE,
not another LLM weight.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum

from guenther.model_manager import MODEL_CATALOG, PRODUCTION_MODEL_ID

MIN_MODEL_RAM_GIB = float(MODEL_CATALOG[PRODUCTION_MODEL_ID]["ram_gb_min"])


class HardwareTier(str, Enum):
    LIGHT = "light"
    STANDARD = "standard"
    POWER = "power"


@dataclass(frozen=True)
class HardwareProfile:
    tier: HardwareTier
    ram_gb: float
    cpu_count: int
    recommended_model_id: str
    notes: tuple[str, ...] = ()


def _ram_gb() -> float:
    override = os.environ.get("KARRIEREKRAKE_RAM_GB")
    if override:
        try:
            return float(override)
        except ValueError:
            pass
    try:
        import psutil

        return float(psutil.virtual_memory().total) / (1024**3)
    except Exception:
        return 8.0


def detect_hardware() -> HardwareProfile:
    ram = _ram_gb()
    try:
        cpu = int(os.cpu_count() or 2)
    except Exception:
        cpu = 2
    # 8.42 GB mmap weights plus runtime/context and OS; latency is unqualified.
    if ram < MIN_MODEL_RAM_GIB:
        return HardwareProfile(
            tier=HardwareTier.LIGHT,
            ram_gb=ram,
            cpu_count=cpu,
            recommended_model_id=PRODUCTION_MODEL_ID,
            notes=("ram_below_min_for_qwen",),
        )
    if ram < 16.0:
        return HardwareProfile(
            tier=HardwareTier.LIGHT,
            ram_gb=ram,
            cpu_count=cpu,
            recommended_model_id=PRODUCTION_MODEL_ID,
            notes=("ram_tight_for_qwen",),
        )
    if ram >= 16.0:
        return HardwareProfile(
            tier=HardwareTier.POWER,
            ram_gb=ram,
            cpu_count=cpu,
            recommended_model_id=PRODUCTION_MODEL_ID,
        )
    return HardwareProfile(
        tier=HardwareTier.STANDARD,
        ram_gb=ram,
        cpu_count=cpu,
        recommended_model_id=PRODUCTION_MODEL_ID,
    )


def resolve_production_model(preferred: str = "auto") -> str:
    """Always return the sole dual-use production model (Qwen3.8-27B GSQ-RCO)."""
    _ = preferred  # legacy settings values are coerced
    return PRODUCTION_MODEL_ID


def graceful_model_fallback(tier: HardwareTier, preferred: str) -> str:
    """No model switching. Always the sole production weight."""
    _ = tier
    return resolve_production_model(preferred)


def can_run_phi(tier: HardwareTier, ram_gb: float | None = None) -> bool:
    """Legacy name: gate for loading the sole production GGUF (16 GB installed RAM target)."""
    if ram_gb is not None and ram_gb < MIN_MODEL_RAM_GIB:
        return False
    if tier == HardwareTier.LIGHT and ram_gb is not None and ram_gb < MIN_MODEL_RAM_GIB:
        return False
    return True


# Preferred alias for new call sites.
can_run_production_model = can_run_phi
