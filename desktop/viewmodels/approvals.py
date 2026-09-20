"""Approval + contextual Günther action view-models.

External / consequential actions stay draft-only until explicit approve.
Widgets never call SendGate.approve or CalendarWriteGate.approve themselves —
pages invoke service helpers after the user confirms.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ApprovalKind(str, Enum):
    CALENDAR_PROPOSAL = "calendar_proposal"
    REPLY_DRAFT = "reply_draft"
    AMBIGUOUS_MAIL = "ambiguous_mail"
    EXTERNAL_ACTION = "external_action"


class GuentherActionKind(str, Enum):
    IMPROVE_COVER = "improve_cover"
    DRAFT_REPLY = "draft_reply"
    EXPLAIN_JOB = "explain_job"
    PREP_INTERVIEW = "prep_interview"


@dataclass(frozen=True)
class ApprovalActionViewModel:
    kind: ApprovalKind
    title_key: str
    body: str
    requires_approval: bool = True
    approved: bool = False
    blocked_reason: str = ""
    case_id: str = ""
    payload: dict[str, Any] = field(default_factory=dict)

    @property
    def can_execute(self) -> bool:
        if self.blocked_reason:
            return False
        if self.requires_approval and not self.approved:
            return False
        return True


@dataclass(frozen=True)
class GuentherActionViewModel:
    kind: GuentherActionKind
    title_key: str
    hint_key: str
    enabled: bool
    case_id: str = ""
    job_id: str = ""


def calendar_proposal_approval(
    *,
    case_id: str,
    summary: str,
    approved: bool = False,
    create_error: str = "",
) -> ApprovalActionViewModel:
    return ApprovalActionViewModel(
        kind=ApprovalKind.CALENDAR_PROPOSAL,
        title_key="approval.calendar_title",
        body=summary,
        requires_approval=True,
        approved=approved,
        blocked_reason=create_error,
        case_id=case_id,
        payload={"summary": summary},
    )


def reply_draft_approval(
    *,
    case_id: str,
    subject: str,
    body: str,
    approved: bool = False,
    draft_only: bool = True,
    send_error: str = "",
    requires_binding_review: bool = False,
    binding_approved: bool = False,
) -> ApprovalActionViewModel:
    blocked = send_error
    if requires_binding_review and approved and not binding_approved:
        blocked = blocked or "binding_review_required"
    return ApprovalActionViewModel(
        kind=ApprovalKind.REPLY_DRAFT,
        title_key="approval.reply_title",
        body=f"{subject}\n\n{body}",
        requires_approval=True,
        approved=approved and (binding_approved if requires_binding_review else True),
        blocked_reason=blocked,
        case_id=case_id,
        payload={
            "subject": subject,
            "draft_only": draft_only,
            "requires_binding_review": requires_binding_review,
        },
    )


def ambiguous_mail_approval(
    *,
    email_id: str,
    case_id: str,
    subject: str,
    sender: str,
) -> ApprovalActionViewModel:
    return ApprovalActionViewModel(
        kind=ApprovalKind.AMBIGUOUS_MAIL,
        title_key="approval.mail_title",
        body=f"{sender}\n{subject}",
        requires_approval=True,
        approved=False,
        case_id=case_id,
        payload={"email_id": email_id},
    )


def contextual_guenther_actions(
    *,
    guenther_enabled: bool,
    case_id: str = "",
    job_id: str = "",
    has_cover_context: bool = False,
    has_job_context: bool = False,
    has_interview_context: bool = False,
) -> tuple[GuentherActionViewModel, ...]:
    """Fixed contextual set — not a free-form chatbot surface."""
    return (
        GuentherActionViewModel(
            kind=GuentherActionKind.IMPROVE_COVER,
            title_key="guenther.action.improve_cover",
            hint_key="guenther.hint.improve_cover",
            enabled=guenther_enabled and has_cover_context,
            case_id=case_id,
            job_id=job_id,
        ),
        GuentherActionViewModel(
            kind=GuentherActionKind.DRAFT_REPLY,
            title_key="guenther.action.draft_reply",
            hint_key="guenther.hint.draft_reply",
            enabled=bool(case_id),  # deterministic draft works without LLM
            case_id=case_id,
            job_id=job_id,
        ),
        GuentherActionViewModel(
            kind=GuentherActionKind.EXPLAIN_JOB,
            title_key="guenther.action.explain_job",
            hint_key="guenther.hint.explain_job",
            enabled=guenther_enabled and has_job_context,
            case_id=case_id,
            job_id=job_id,
        ),
        GuentherActionViewModel(
            kind=GuentherActionKind.PREP_INTERVIEW,
            title_key="guenther.action.prep_interview",
            hint_key="guenther.hint.prep_interview",
            enabled=bool(case_id) and has_interview_context,
            case_id=case_id,
            job_id=job_id,
        ),
    )
