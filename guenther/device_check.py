"""Offline resource recommendations, not an inference benchmark.

DASLab sizes from the upstream model cards (2026-10-11):
https://huggingface.co/ISTA-DASLab/Qwen3.8-27B-GSQ-RCO-GGUF
https://huggingface.co/ISTA-DASLab/Qwen3.5-4B-GGUF-GSQ
https://huggingface.co/ISTA-DASLab/Qwen3-8B-GGUF-GSQ
Memory budgets include 4 GiB for context/runtime; keep 2 GiB available for UI/OS.
27B variants are recommendations only until their runtime/HR acceptance passes.

Class minimums, the OS reserve and the total-RAM class gates come from
``guenther.model_budgets`` (shared with ``guenther.setup_models``). A
candidate's own ``runtime_gib`` can only make it stricter, never looser.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import shutil

from guenther.model_budgets import (
    CLASS_4B, CLASS_8B, CLASS_27B, DISK_RESERVE_BYTES, class_ram_min_gib, ram_fits,
)


@dataclass(frozen=True)
class Candidate:
    name: str
    disk_gb: float
    runtime_gib: float
    ready: bool = False
    model_class: str = CLASS_4B
    # Setup catalog id when this candidate is the artifact the wizard installs.
    setup_model_id: str | None = None

    @property
    def required_gib(self) -> float:
        """Effective minimum RAM: own estimate, floored by the shared class budget."""
        return class_ram_min_gib(self.model_class, self.runtime_gib)


CANDIDATES = (
    Candidate("Qwen3.5-4B Q4_K_M", 2.6, 6.0, True, CLASS_4B),
    # Smaller upstream GSQ releases are not GSQ-RCO models. Runtime budgets
    # are conservative estimates, not measured HR acceptance results.
    Candidate("DASLab Qwen3.5-4B GSQ Q2_K_XL", 1.94, 6.0, False, CLASS_4B, "qwen3.5-4b-gsq"),
    Candidate("DASLab Qwen3-8B GSQ Q2_K", 3.28, 8.0, False, CLASS_8B),
    Candidate("DASLab Qwen3-8B GSQ Q3_K_M", 4.12, 9.0, False, CLASS_8B, "qwen3-8b-gsq"),
    # 27B: the shared class minimum (14.0 GiB) is stricter than the former
    # per-variant 12.0/13.0 values, so those variants now need 14.0 GiB.
    Candidate("DASLab Qwen3.8-27B GSQ-RCO IQ2_XS", 8.4, 12.0, False, CLASS_27B, "qwen3.8-27b-gsq-rco"),
    Candidate("DASLab Qwen3.8-27B GSQ-RCO IQ2_S", 9.3, 13.0, False, CLASS_27B),
    Candidate("DASLab Qwen3.8-27B GSQ-RCO IQ3_XXS", 10.1, 14.0, False, CLASS_27B),
    Candidate("DASLab Qwen3.8-27B GSQ-RCO IQ3_S", 11.8, 16.0, False, CLASS_27B),
)


@dataclass(frozen=True)
class DeviceCheck:
    total_gib: float
    available_gib: float
    physical_cores: int
    free_disk_gb: float
    fitting: tuple[Candidate, ...]

    def message(self) -> str:
        lines = [f"RAM: {self.total_gib:.1f} GiB gesamt, {self.available_gib:.1f} GiB frei",
                 f"CPU: {self.physical_cores} physische Kerne · Speicherplatz: {self.free_disk_gb:.1f} GB frei"]
        ready = next((c for c in self.fitting if c.ready), None)
        lines.append(f"Empfehlung für schnelle Nutzung: {ready.name}" if ready else
                     "Aktuell zu wenig freier RAM/Speicherplatz. Andere Programme schließen.")
        optional = [c.name for c in self.fitting if not c.ready]
        if optional:
            lines.append("Nach geschätztem Speicherbedarf zusätzlich passend:\n" + "\n".join(optional))
            lines.append("DASLab-Alternativen: Laufzeitkompatibilität und HR-Qualität noch nicht freigegeben; kein automatischer Wechsel.")
            lines.append("4B/8B verwenden GSQ, die 27B-Varianten GSQ-RCO.")
        lines.append("Speicherprüfung, kein Geschwindigkeitstest. Inferenztempo hängt auch von CPU, GPU und Kontext ab.")
        return "\n".join(lines)


def _disk_fits(candidate: Candidate, free_disk_gb: float) -> bool:
    if candidate.setup_model_id is not None:
        # Use the exact catalog byte size so this check matches setup_models.
        from guenther.setup_models import SETUP_MODEL_CATALOG
        needed = SETUP_MODEL_CATALOG[candidate.setup_model_id]["approx_bytes"] + DISK_RESERVE_BYTES
        return needed <= free_disk_gb * 1_000_000_000
    return candidate.disk_gb + 0.5 <= free_disk_gb


def candidate_fits(candidate: Candidate, *, total_gib: float, available_gib: float,
                   free_disk_gb: float) -> bool:
    """Device-only check: class gate and headroom on total RAM (same rule as
    setup_models ``fits``), class budget on free RAM, disk."""
    return (ram_fits(candidate.model_class, total_gib=total_gib, available_gib=available_gib,
                     own_gib=candidate.runtime_gib)
            and _disk_fits(candidate, free_disk_gb))


def recommend(*, total_gib: float, available_gib: float, physical_cores: int,
              free_disk_gb: float) -> DeviceCheck:
    fitting = tuple(c for c in CANDIDATES
                    if candidate_fits(c, total_gib=total_gib, available_gib=available_gib,
                                      free_disk_gb=free_disk_gb))
    return DeviceCheck(total_gib, available_gib, physical_cores, free_disk_gb, fitting)


def check_device(model_directory: Path) -> DeviceCheck:
    import psutil

    memory = psutil.virtual_memory()
    existing = model_directory
    while not existing.exists() and existing.parent != existing:
        existing = existing.parent
    return recommend(total_gib=memory.total / 1024**3,
                     available_gib=memory.available / 1024**3,
                     physical_cores=psutil.cpu_count(logical=False) or os.cpu_count() or 1,
                     free_disk_gb=shutil.disk_usage(existing).free / 1_000_000_000)
