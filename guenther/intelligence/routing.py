"""Architecture routing for measurable A vs B comparison.

A: Phi-4-mini for all capabilities
B: Qwen3-1.7B for light/safety path; Phi-4-mini for strong generative path
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ArchitectureMode(str, Enum):
    QWEN_ONLY = "qwen_only"  # baseline / current default path
    PHI_ALL = "phi_all"  # Architecture A
    TWO_TIER = "two_tier"  # Architecture B
    AUTO = "auto"  # respect model_pref without forcing split


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
    }
)

LIGHT_MODEL = "qwen3-1.7b"
STRONG_MODEL = "phi4-mini"


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
    if mode == ArchitectureMode.PHI_ALL:
        return RoutingDecision(mode, STRONG_MODEL, capability, "arch_a_phi_all")
    if mode == ArchitectureMode.TWO_TIER:
        if capability in STRONG_CAPABILITIES:
            return RoutingDecision(mode, STRONG_MODEL, capability, "arch_b_strong_phi")
        return RoutingDecision(mode, LIGHT_MODEL, capability, "arch_b_light_qwen")
    if mode == ArchitectureMode.QWEN_ONLY:
        return RoutingDecision(mode, LIGHT_MODEL, capability, "baseline_qwen")
    # AUTO: honor explicit pref; auto stays light-safe default (qwen) — do not hard-code Phi
    if model_pref and model_pref not in {"auto", ""}:
        return RoutingDecision(mode, model_pref, capability, "explicit_pref")
    return RoutingDecision(mode, LIGHT_MODEL, capability, "auto_default_qwen_light")
