"""ApplicationCase lifecycle foundation.

Status taxonomy adapted from trackjobapplications (MIT) and STATUS_RANK ideas
from ai-job-tracker packages/core (MIT, Claude path rejected). German lifecycle
wording aligned with PBP stellen_zustand (MIT).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

from core.models import utc_now_iso
from core.text_normalize import clean_company, clean_text


class CaseStatus(str, Enum):
    """Lifecycle states for a single vacancy application case."""

    TO_APPLY = "to_apply"
    APPLIED = "applied"
    CONFIRMATION = "confirmation"
    ASSESSMENT = "assessment"
    INTERVIEW = "interview"
    OFFER = "offer"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"
    GHOSTED = "ghosted"  # suggested / soft — never auto-sent
    CLOSED = "closed"


# Statuses that must never re-enter search as "new" discoveries.
KNOWN_SUPPRESS_STATUSES: frozenset[str] = frozenset(
    {
        CaseStatus.APPLIED.value,
        CaseStatus.CONFIRMATION.value,
        CaseStatus.ASSESSMENT.value,
        CaseStatus.INTERVIEW.value,
        CaseStatus.OFFER.value,
        CaseStatus.REJECTED.value,
        CaseStatus.WITHDRAWN.value,
        CaseStatus.GHOSTED.value,
        CaseStatus.CLOSED.value,
    }
)

# Rank prevents automatic downgrades (e.g. late confirmation must not
# move Interview → Applied). Adapted from ai-job-tracker STATUS_RANK idea.
STATUS_RANK: dict[str, int] = {
    CaseStatus.TO_APPLY.value: 0,
    CaseStatus.APPLIED.value: 1,
    CaseStatus.CONFIRMATION.value: 2,
    CaseStatus.ASSESSMENT.value: 3,
    CaseStatus.INTERVIEW.value: 4,
    CaseStatus.OFFER.value: 5,
    CaseStatus.GHOSTED.value: 2,  # soft side-state; do not outrank interview
    CaseStatus.REJECTED.value: 6,
    CaseStatus.WITHDRAWN.value: 6,
    CaseStatus.CLOSED.value: 7,
}

TERMINAL_STATUSES: frozenset[str] = frozenset(
    {
        CaseStatus.REJECTED.value,
        CaseStatus.WITHDRAWN.value,
        CaseStatus.CLOSED.value,
        CaseStatus.OFFER.value,
    }
)


class CaseEventType(str, Enum):
    CREATED = "created"
    STATUS_CHANGED = "status_changed"
    EMAIL_LINKED = "email_linked"
    EMAIL_AMBIGUOUS = "email_ambiguous"
    INTERVIEW_SCHEDULED = "interview_scheduled"
    FOLLOW_UP_SUGGESTED = "follow_up_suggested"
    REPLY_DRAFTED = "reply_drafted"
    REPLY_SENT = "reply_sent"
    REPLY_SEND_FAILED = "reply_send_failed"
    NOTE = "note"
    PREP_BUILT = "prep_built"


@dataclass
class ApplicationCase:
    id: str = ""
    job_id: str = ""
    company: str = ""
    position: str = ""
    status: str = CaseStatus.TO_APPLY.value
    source: str = ""
    url: str = ""
    application_url: str = ""
    contact_email: str = ""
    contact_name: str = ""
    contact_phone: str = ""
    applied_at: str = ""
    updated_at: str = field(default_factory=utc_now_iso)
    created_at: str = field(default_factory=utc_now_iso)
    notes: str = ""
    company_key: str = ""
    title_key: str = ""
    url_key: str = ""

    def __post_init__(self) -> None:
        self.company = clean_company(self.company)
        self.position = clean_text(self.position)
        self.contact_email = clean_text(self.contact_email).lower()
        self.contact_name = clean_text(self.contact_name)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ApplicationCase":
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in known})


@dataclass
class CaseEvent:
    id: str = ""
    case_id: str = ""
    event_type: str = CaseEventType.NOTE.value
    payload_json: str = "{}"
    created_at: str = field(default_factory=utc_now_iso)
    confidence: float = 1.0


def can_transition(current: str, proposed: str, *, force: bool = False) -> bool:
    """Return True if proposed status may replace current.

    Automatic paths never downgrade by rank unless ``force`` (user override).
    """
    if force:
        return True
    if current == proposed:
        return True
    cur = STATUS_RANK.get(current, 0)
    nxt = STATUS_RANK.get(proposed, 0)
    # Terminal rejected/withdrawn/closed stay unless force.
    if current in TERMINAL_STATUSES and proposed not in TERMINAL_STATUSES:
        return False
    return nxt >= cur


def email_category_to_status(category: str) -> str | None:
    """Map classifier category → case status (local rules, no LLM).

    Accepts legacy operational labels and PR28 lifecycle class names.
    UNKNOWN / review / noise / general never auto-map to a status.
    """
    mapping = {
        "confirmation": CaseStatus.CONFIRMATION.value,
        "eingangsbestaetigung": CaseStatus.CONFIRMATION.value,
        "application_received": CaseStatus.CONFIRMATION.value,
        "under_review": CaseStatus.CONFIRMATION.value,
        "assessment": CaseStatus.ASSESSMENT.value,
        "interview": CaseStatus.INTERVIEW.value,
        "interview_invite": CaseStatus.INTERVIEW.value,
        "interview_reschedule": CaseStatus.INTERVIEW.value,
        "offer": CaseStatus.OFFER.value,
        "angebot": CaseStatus.OFFER.value,
        "rejection": CaseStatus.REJECTED.value,
        "abgelehnt": CaseStatus.REJECTED.value,
        "ghosted": CaseStatus.GHOSTED.value,
        # Explicit non-mappings: review, unknown, noise, general,
        # general_recruiter_message, document_request → None
    }
    return mapping.get((category or "").strip().lower())
