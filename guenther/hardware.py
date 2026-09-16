"""Hardware tier detection — LIGHT / STANDARD / POWER only."""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum


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
    if ram < 8.0 or cpus <= 2:
        return HardwareProfile(
            tier=HardwareTier.LIGHT,
            ram_gb=ram,
            cpu_count=cpus,
            recommended_model_id="qwen3-1.7b",
            notes=("low_ram_or_cpu",),
        )
    if ram >= 24.0:
        return HardwareProfile(
            tier=HardwareTier.POWER,
            ram_gb=ram,
            cpu_count=cpus,
            recommended_model_id="qwen3-4b",
            notes=("high_ram",),
        )
    return HardwareProfile(
        tier=HardwareTier.STANDARD,
        ram_gb=ram,
        cpu_count=cpus,
        recommended_model_id="qwen3-4b",
        notes=(),
    )


def graceful_model_fallback(tier: HardwareTier, preferred: str) -> str:
    """If preferred unavailable, degrade toward LIGHT."""
    light = "qwen3-1.7b"
    standard = "qwen3-4b"
    if preferred in {light, standard, "phi4-mini", "auto"}:
        if preferred == "auto":
            return light if tier == HardwareTier.LIGHT else standard
        if tier == HardwareTier.LIGHT and preferred != light:
            return light
        return preferred if preferred != "auto" else standard
    return light
