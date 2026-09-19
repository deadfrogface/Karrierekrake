"""Pydantic structured contracts for Günther outputs (LLM = untrusted)."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ConfidenceLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class EvidenceSupport(str, Enum):
    DIRECT = "DIRECT"
    RELATED = "RELATED"
    NOT_SUPPORTED = "NOT_SUPPORTED"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ClaimAnchor(StrictModel):
    """A claim must be anchored to profile/job text — never invented."""

    text: str = Field(min_length=1, max_length=400)
    source: Literal["profile", "cv", "job", "email", "evidence", "manual"] = "profile"
    quote: str = Field(default="", max_length=400)


class CVExtractSuggestion(StrictModel):
    full_name: str = ""
    emails: list[str] = Field(default_factory=list, max_length=5)
    phones: list[str] = Field(default_factory=list, max_length=5)
    skills: list[str] = Field(default_factory=list, max_length=40)
    languages: list[str] = Field(default_factory=list, max_length=20)
    experience_titles: list[str] = Field(default_factory=list, max_length=30)
    education: list[str] = Field(default_factory=list, max_length=20)
    certificates: list[str] = Field(default_factory=list, max_length=20)
    confidence: ConfidenceLevel = ConfidenceLevel.LOW
    notes: list[str] = Field(default_factory=list, max_length=10)
    invented_flag: bool = False  # validator sets True if anchors fail


class JobRequirementItem(StrictModel):
    requirement: str = Field(min_length=1, max_length=300)
    kind: Literal["hard", "desirable", "unknown"] = "unknown"
    confidence: ConfidenceLevel = ConfidenceLevel.LOW


class JobAnalysisSuggestion(StrictModel):
    title_normalized: str = ""
    requirements: list[JobRequirementItem] = Field(default_factory=list, max_length=40)
    red_flags: list[str] = Field(default_factory=list, max_length=15)
    summary: str = Field(default="", max_length=800)
    confidence: ConfidenceLevel = ConfidenceLevel.LOW


class EvidenceAssistItem(StrictModel):
    claim: str = Field(min_length=1, max_length=300)
    support: EvidenceSupport = EvidenceSupport.NOT_SUPPORTED
    note: str = Field(default="", max_length=400)
    anchors: list[ClaimAnchor] = Field(default_factory=list, max_length=5)


class EvidenceAssistSuggestion(StrictModel):
    items: list[EvidenceAssistItem] = Field(default_factory=list, max_length=40)
    confidence: ConfidenceLevel = ConfidenceLevel.LOW


class EmailClassSuggestion(StrictModel):
    category: Literal[
        "confirmation",
        "interview",
        "interview_cancelled",
        "offer",
        "rejection",
        "assessment",
        "document_request",
        "employer_question",
        "recruiter_outreach",
        "noise",
        "other",
        "ghosted",
        "review",
    ] = "other"
    confidence: ConfidenceLevel = ConfidenceLevel.LOW
    reasons: list[str] = Field(default_factory=list, max_length=8)
    false_rejection_risk: bool = False
    evidence: list[str] = Field(default_factory=list, max_length=8)


class AssociationSuggestion(StrictModel):
    case_id: str | None = None
    confidence: ConfidenceLevel = ConfidenceLevel.LOW
    ambiguous: bool = True
    candidate_case_ids: list[str] = Field(default_factory=list, max_length=8)
    reason: str = Field(default="", max_length=400)
    match_status: Literal[
        "linked",
        "ambiguous",
        "no_safe_match",
        "review",
    ] = "no_safe_match"


class WritingSuggestion(StrictModel):
    subject: str = Field(default="", max_length=200)
    body: str = Field(default="", max_length=6000)
    anchors_used: list[ClaimAnchor] = Field(default_factory=list, max_length=30)
    invented_flag: bool = False
    confidence: ConfidenceLevel = ConfidenceLevel.LOW


class ReplyActionSuggestion(StrictModel):
    """Günther may only polish an existing typed ReplyAction draft.

    Never invents company/job/contact/dates/salary. Never sets auto_send.
    Binding actions always require_explicit_review=True.
    """

    action: Literal[
        "CONFIRM_INTERVIEW",
        "PROPOSE_SLOTS",
        "RESCHEDULE",
        "DOCUMENT_REPLY",
        "THANK_YOU",
        "FOLLOWUP",
        "WITHDRAW",
        "DECLINE_OFFER",
        "GENERAL_REPLY",
    ] = "GENERAL_REPLY"
    case_id: str = Field(default="", max_length=80)
    subject: str = Field(default="", max_length=200)
    body: str = Field(default="", max_length=6000)
    used_facts: list[str] = Field(default_factory=list, max_length=20)
    invented_flag: bool = False
    draft_only: bool = True
    auto_send: bool = False
    requires_explicit_review: bool = False
    confidence: ConfidenceLevel = ConfidenceLevel.LOW


class InterviewPrepSuggestion(StrictModel):
    questions: list[str] = Field(default_factory=list, max_length=20)
    talking_points: list[str] = Field(default_factory=list, max_length=20)
    gap_notes: list[str] = Field(default_factory=list, max_length=15)
    anchors_used: list[ClaimAnchor] = Field(default_factory=list, max_length=30)
    invented_flag: bool = False
    confidence: ConfidenceLevel = ConfidenceLevel.LOW


class GuentherEnvelope(StrictModel):
    """Wrapper for any intelligence result with fail-closed metadata."""

    ok: bool
    capability: str
    suggestion: dict[str, Any] = Field(default_factory=dict)
    fallback_reason: str = ""
    provider_status: str = ""
    model_id: str = ""
    validated: bool = False
    safety_notes: list[str] = Field(default_factory=list)
    # Grounding / bounded self-correction metadata (optional; empty for legacy paths)
    architecture: str = ""
    validator_errors: list[dict[str, Any]] = Field(default_factory=list, max_length=40)
    repair_history: dict[str, Any] = Field(default_factory=dict)
    grounding_report: dict[str, Any] = Field(default_factory=dict)


SCHEMA_BY_NAME: dict[str, type[BaseModel]] = {
    "cv_extract": CVExtractSuggestion,
    "job_analysis": JobAnalysisSuggestion,
    "evidence_assist": EvidenceAssistSuggestion,
    "email_class": EmailClassSuggestion,
    "association": AssociationSuggestion,
    "writing": WritingSuggestion,
    "reply_action": ReplyActionSuggestion,
    "interview_prep": InterviewPrepSuggestion,
}

# Quality-loop schemas (imported after WritingSuggestion to avoid cycles).
from guenther.intelligence.quality_loop.schemas import (  # noqa: E402
    QualityCritique,
    WritingPlan,
)

SCHEMA_BY_NAME["writing_plan"] = WritingPlan
SCHEMA_BY_NAME["writing_critique"] = QualityCritique


def _schema_by_name() -> dict[str, type[BaseModel]]:
    return dict(SCHEMA_BY_NAME)
