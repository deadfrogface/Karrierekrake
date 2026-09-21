"""Architecture routing — sole production model is Phi-4-mini (NEXT-02).

Qwen / two-tier / light-fallback modes are historical only and resolve to Phi.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from guenther.model_manager import PRODUCTION_MODEL_ID


class ArchitectureMode(str, Enum):
    # Historical aliases retained for config/test compatibility — all map to Phi.
    QWEN_ONLY = "qwen_only"
    PHI_ALL = "phi_all"
    TWO_TIER = "two_tier"
    AUTO = "auto"


LIGHT_CAPABILITIES = frozenset(
    {
        "email_class",
        "association",
        "cv_extract",
        "job_analysis",
    }
)
STRONG_CAPABILITIES = frozenset(
    {
        "writing",
        "interview_prep",
        "evidence_assist",
        "writing_plan",
        "writing_critique",
    }
)

PRIMARY_MODEL = PRODUCTION_MODEL_ID
STRONG_MODEL = PRIMARY_MODEL
# Deprecated alias — must not be used as a production runtime target.
LIGHT_MODEL = PRODUCTION_MODEL_ID


@dataclass(frozen=True)
class RoutingDecision:
    architecture: ArchitectureMode
    model_id: str
    capability: str
    reason: str


def resolve_model_for_capability(
    *,
    architecture: ArchitectureMode | str,
    capability: str,
    model_pref: str = "auto",
) -> RoutingDecision:
    """Always route to Phi. Explicit Qwen prefs are ignored (no production path)."""
    mode = (
        architecture
        if isinstance(architecture, ArchitectureMode)
        else ArchitectureMode(str(architecture))
    )
    pref = (model_pref or "auto").strip().lower()
    if pref in {"qwen3-1.7b", "qwen3-4b", "qwen_only"}:
        return RoutingDecision(
            mode, PRIMARY_MODEL, capability, "qwen_pref_coerced_to_phi"
        )
    if pref not in {"", "auto", PRIMARY_MODEL}:
        # Unknown prefs also coerce to Phi — never load a non-production id.
        return RoutingDecision(
            mode, PRIMARY_MODEL, capability, "non_phi_pref_coerced_to_phi"
        )
    if mode == ArchitectureMode.PHI_ALL:
        return RoutingDecision(mode, PRIMARY_MODEL, capability, "arch_phi_all")
    if mode in {ArchitectureMode.TWO_TIER, ArchitectureMode.QWEN_ONLY, ArchitectureMode.AUTO}:
        return RoutingDecision(
            mode, PRIMARY_MODEL, capability, "production_phi_only"
        )
    return RoutingDecision(mode, PRIMARY_MODEL, capability, "production_phi_only")
