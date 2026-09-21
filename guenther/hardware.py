"""Hardware tier detection — LIGHT / STANDARD / POWER.

NEXT-02: Production recommends Phi-4-mini only. No Qwen hardware fallback.
Insufficient RAM → Phi may be unavailable (GUENTHER_UNAVAILABLE), not another LLM.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum

from guenther.model_manager import PRODUCTION_MODEL_ID


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
    # Linux
    try:
        with open("/proc/meminfo", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("MemTotal:"):
                    kb = float(line.split()[1])
                    return kb / (1024 * 1024)
    except OSError:
        pass
    # Windows / fallback via env override for tests
    override = os.environ.get("KARRIEREKRAKE_RAM_GB")
    if override:
        try:
            return float(override)
        except ValueError:
            pass
    return 8.0


def detect_hardware() -> HardwareProfile:
    ram = _ram_gb()
    cpus = os.cpu_count() or 2
    # Phi peak ~5.6GB observed; require comfortable headroom for STANDARD.
    if ram < 8.0 or cpus <= 2:
        return HardwareProfile(
            tier=HardwareTier.LIGHT,
            ram_gb=ram,
            cpu_count=cpus,
            recommended_model_id=PRODUCTION_MODEL_ID,
            notes=(
                "low_ram_or_cpu",
                "phi_only_may_be_unavailable",
                "no_qwen_fallback",
            ),
        )
    if ram >= 24.0:
        return HardwareProfile(
            tier=HardwareTier.POWER,
            ram_gb=ram,
            cpu_count=cpus,
            recommended_model_id=PRODUCTION_MODEL_ID,
            notes=("high_ram", "phi_sole_production"),
        )
    return HardwareProfile(
        tier=HardwareTier.STANDARD,
        ram_gb=ram,
        cpu_count=cpus,
        recommended_model_id=PRODUCTION_MODEL_ID,
        notes=("phi_sole_production",),
    )


def resolve_production_model(preferred: str = "auto") -> str:
    """Always return the sole production Phi model. Ignore Qwen / auto prefs."""
    _ = preferred  # legacy settings values are coerced
    return PRODUCTION_MODEL_ID


def graceful_model_fallback(tier: HardwareTier, preferred: str) -> str:
    """NEXT-02: no model switching. Always Phi. Kept name for call-site stability."""
    _ = tier
    return resolve_production_model(preferred)


def can_run_phi(tier: HardwareTier, ram_gb: float | None = None) -> bool:
    """Conservative Phi gate — LIGHT may still attempt load; caller handles failure."""
    if ram_gb is not None and ram_gb < 5.0:
        return False
    if tier == HardwareTier.LIGHT and ram_gb is not None and ram_gb < 8.0:
        # Soft gate: UI may warn; load failure → GUENTHER_UNAVAILABLE (no alternate LLM).
        return False
    return True
