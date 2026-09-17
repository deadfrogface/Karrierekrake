"""Architecture routing — Phi-4-mini PRIMARY, Qwen3-1.7B LIGHT FALLBACK.

Model tournament closed for this cycle. Explicit user model_pref is always respected.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ArchitectureMode(str, Enum):
    QWEN_ONLY = "qwen_only"  # forced light path / test baseline
    PHI_ALL = "phi_all"  # Phi for all capabilities
    TWO_TIER = "two_tier"  # light safety path Qwen; strong generative Phi
    AUTO = "auto"  # recommended: Phi primary when hardware allows


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

LIGHT_MODEL = "qwen3-1.7b"
PRIMARY_MODEL = "phi4-mini"
STRONG_MODEL = PRIMARY_MODEL  # back-compat alias


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
    mode = (
        architecture
        if isinstance(architecture, ArchitectureMode)
        else ArchitectureMode(str(architecture))
    )
    # Explicit user/model preference always wins (safe migration).
    if model_pref and model_pref not in {"auto", ""}:
        return RoutingDecision(mode, model_pref, capability, "explicit_pref")
    if mode == ArchitectureMode.PHI_ALL:
        return RoutingDecision(mode, PRIMARY_MODEL, capability, "arch_a_phi_all")
    if mode == ArchitectureMode.TWO_TIER:
        if capability in STRONG_CAPABILITIES:
            return RoutingDecision(mode, PRIMARY_MODEL, capability, "arch_b_strong_phi")
        return RoutingDecision(mode, LIGHT_MODEL, capability, "arch_b_light_qwen")
    if mode == ArchitectureMode.QWEN_ONLY:
        return RoutingDecision(mode, LIGHT_MODEL, capability, "baseline_qwen")
    # AUTO: Phi is primary/recommended; hardware fallback applied by caller.
    if capability in STRONG_CAPABILITIES or capability in LIGHT_CAPABILITIES:
        return RoutingDecision(mode, PRIMARY_MODEL, capability, "auto_default_phi_primary")
    return RoutingDecision(mode, PRIMARY_MODEL, capability, "auto_default_phi_primary")
