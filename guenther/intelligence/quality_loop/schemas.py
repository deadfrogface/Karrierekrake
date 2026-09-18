"""Structured contracts for PLAN → DRAFT → CRITIQUE → REVISE (no CoT storage)."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import Field

from guenther.contracts import ConfidenceLevel, StrictModel


class FinalResultState(str, Enum):
    READY_AUTOMATIC = "READY_AUTOMATIC"
    REVIEW_REQUIRED_QUALITY = "REVIEW_REQUIRED_QUALITY"
    REVIEW_REQUIRED_SAFETY = "REVIEW_REQUIRED_SAFETY"
    HARD_REQUIREMENT_NOT_MET = "HARD_REQUIREMENT_NOT_MET"
    GENERATION_FAILED = "GENERATION_FAILED"
    MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"


class RequirementStatus(str, Enum):
    MET_DIRECT = "MET_DIRECT"
    RELATED_ONLY = "RELATED_ONLY"
    NOT_MET = "NOT_MET"
    UNKNOWN = "UNKNOWN"


class PlanEvidenceRef(StrictModel):
    evidence_id: str = Field(min_length=1, max_length=64)
    reason: str = Field(default="", max_length=400)
    allowed_transfer_framing: str = Field(default="", max_length=400)


class PlanRequirementItem(StrictModel):
    requirement: str = Field(min_length=1, max_length=300)
    status: RequirementStatus = RequirementStatus.UNKNOWN


class WritingPlan(StrictModel):
    """Application writing plan — factual items must reference evidence IDs."""

    target_role: str = Field(default="", max_length=200)
    target_company: str = Field(default="", max_length=200)
    candidate_positioning: str = Field(default="", max_length=600)
    strongest_direct_evidence: list[PlanEvidenceRef] = Field(default_factory=list, max_length=6)
    strongest_related_evidence: list[PlanEvidenceRef] = Field(default_factory=list, max_length=6)
    do_not_claim: list[str] = Field(default_factory=list, max_length=20)
    hard_requirements: list[PlanRequirementItem] = Field(default_factory=list, max_length=20)
    desirable_requirements: list[PlanRequirementItem] = Field(default_factory=list, max_length=20)
    argument_1: str = Field(default="", max_length=500)
    argument_2: str = Field(default="", max_length=500)
    argument_3: str = Field(default="", max_length=500)
    company_reference: str = Field(default="", max_length=400)
    opening_strategy: str = Field(default="", max_length=400)
    closing_strategy: str = Field(default="", max_length=400)
    invented_flag: bool = False
    confidence: ConfidenceLevel = ConfidenceLevel.LOW


class CriticProblem(StrictModel):
    severity: Literal["low", "medium", "high"] = "medium"
    location: str = Field(default="", max_length=200)
    problem: str = Field(default="", max_length=500)
    recommended_change: str = Field(default="", max_length=600)
    evidence_id_to_use: str = Field(default="", max_length=64)


class QualityCritique(StrictModel):
    """Quality-only assessment — never overrides deterministic safety."""

    job_relevance: int = Field(default=0, ge=0, le=10)
    evidence_use: int = Field(default=0, ge=0, le=10)
    specificity: int = Field(default=0, ge=0, le=10)
    german_naturalness: int = Field(default=0, ge=0, le=10)
    persuasiveness: int = Field(default=0, ge=0, le=10)
    structure: int = Field(default=0, ge=0, le=10)
    conciseness: int = Field(default=0, ge=0, le=10)
    transferable_experience: int = Field(default=0, ge=0, le=10)
    submission_readiness: int = Field(default=0, ge=0, le=10)
    ready_as_is: bool = False
    problems: list[CriticProblem] = Field(default_factory=list, max_length=12)
    strong_parts_to_preserve: list[str] = Field(default_factory=list, max_length=10)
    invented_flag: bool = False
    confidence: ConfidenceLevel = ConfidenceLevel.LOW


# Bounds — documented hard maximums (Phase H / state machine).
MAX_PLAN_REPAIRS = 1
MAX_SAFETY_REPAIRS = 1
MAX_QUALITY_REVISIONS = 2
# PLAN + PLAN_REPAIR + DRAFT + SAFETY_REPAIR + CRITIC×2 + QUALITY_REV×2 = 8
MAX_MODEL_CALLS = 8

QUALITY_LOOP_MODES = frozenset(
    {
        "old",  # legacy single-shot + safety repair only
        "plan_draft",  # plan + draft + safety
        "critic1",  # + critic + up to 1 quality revision
        "full",  # + up to 2 quality revisions (default)
    }
)
