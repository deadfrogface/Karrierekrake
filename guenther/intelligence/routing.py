"""Architecture routing — sole production model is Qwen3.8-27B GSQ-RCO.

Historical mode names (PHI_ALL, TWO_TIER, …) are aliases and all resolve to
the same production weight. No Phi runtime path.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from guenther.model_manager import PRODUCTION_MODEL_ID


class ArchitectureMode(str, Enum):
    # Historical aliases retained for config/test compatibility — all map to Qwen.
    QWEN_ONLY = "qwen_only"
    PHI_ALL = "phi_all"  # legacy name; routes to PRODUCTION_MODEL_ID
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
    """Always route to the sole production Qwen weight. Legacy prefs coerced."""
    mode = (
        architecture
        if isinstance(architecture, ArchitectureMode)
        else ArchitectureMode(str(architecture))
    )
    pref = (model_pref or "auto").strip().lower()
    if pref in {"phi4-mini", "phi-4-mini", "qwen3-1.7b", "qwen3-4b", "qwen_only"}:
        return RoutingDecision(
            mode, PRIMARY_MODEL, capability, "legacy_pref_coerced_to_qwen"
        )
    if pref not in {"", "auto", PRIMARY_MODEL}:
        return RoutingDecision(
            mode, PRIMARY_MODEL, capability, "non_production_pref_coerced_to_qwen"
        )
    if mode == ArchitectureMode.PHI_ALL:
        return RoutingDecision(mode, PRIMARY_MODEL, capability, "arch_legacy_phi_all_to_qwen")
    if mode in {ArchitectureMode.TWO_TIER, ArchitectureMode.QWEN_ONLY, ArchitectureMode.AUTO}:
        return RoutingDecision(
            mode, PRIMARY_MODEL, capability, "production_qwen_only"
        )
    return RoutingDecision(mode, PRIMARY_MODEL, capability, "production_qwen_only")
