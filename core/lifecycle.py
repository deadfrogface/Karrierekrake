"""ApplicationCase lifecycle foundation + event-sourced status reducer (PR30).

Status taxonomy adapted from trackjobapplications (MIT) and STATUS_RANK ideas
from ai-job-tracker packages/core (MIT, Claude path rejected). German lifecycle
wording aligned with PBP stellen_zustand (MIT).

Status is never mutated from LLM/classifier output directly. Callers append
``LifecycleEvent`` rows; ``reduce_lifecycle_events`` derives status purely and
deterministically. Classifier labels map to events only (PR28).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Iterable, Sequence

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


CANONICAL_CASE_STATUSES: frozenset[str] = frozenset(s.value for s in CaseStatus)

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

STATUS_RANK: dict[str, int] = {
    CaseStatus.TO_APPLY.value: 0,
    CaseStatus.APPLIED.value: 1,
    CaseStatus.CONFIRMATION.value: 2,
    CaseStatus.ASSESSMENT.value: 3,
    CaseStatus.INTERVIEW.value: 4,
    CaseStatus.OFFER.value: 5,
    CaseStatus.GHOSTED.value: 2,
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

SOFT_STATUSES: frozenset[str] = frozenset({CaseStatus.GHOSTED.value})

TERMINAL_HARDENING: dict[str, frozenset[str]] = {
    CaseStatus.OFFER.value: frozenset(
        {
            CaseStatus.REJECTED.value,
            CaseStatus.WITHDRAWN.value,
            CaseStatus.CLOSED.value,
        }
    ),
    CaseStatus.REJECTED.value: frozenset({CaseStatus.CLOSED.value}),
    CaseStatus.WITHDRAWN.value: frozenset({CaseStatus.CLOSED.value}),
    CaseStatus.CLOSED.value: frozenset(),
}


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
    LIFECYCLE_EVENT = "lifecycle_event"
    MANUAL_OVERRIDE = "manual_override"


class LifecycleEventType(str, Enum):
    APPLICATION_CREATED = "APPLICATION_CREATED"
    APPLICATION_SENT = "APPLICATION_SENT"
    APPLICATION_RECEIVED = "APPLICATION_RECEIVED"
    UNDER_REVIEW = "UNDER_REVIEW"
    DOCUMENT_REQUESTED = "DOCUMENT_REQUESTED"
    ASSESSMENT_RECEIVED = "ASSESSMENT_RECEIVED"
    INTERVIEW_REQUESTED = "INTERVIEW_REQUESTED"
    INTERVIEW_SCHEDULED = "INTERVIEW_SCHEDULED"
    INTERVIEW_RESCHEDULED = "INTERVIEW_RESCHEDULED"
    INTERVIEW_CANCELLED = "INTERVIEW_CANCELLED"
    INTERVIEW_COMPLETED = "INTERVIEW_COMPLETED"
    OFFER_RECEIVED = "OFFER_RECEIVED"
    REJECTION_RECEIVED = "REJECTION_RECEIVED"
    FOLLOWUP_SENT = "FOLLOWUP_SENT"
    WITHDRAWN = "WITHDRAWN"
    GHOSTED = "GHOSTED"
    ARCHIVED = "ARCHIVED"
    MANUAL_OVERRIDE = "MANUAL_OVERRIDE"


EVENT_STATUS_TARGET: dict[str, str | None] = {
    LifecycleEventType.APPLICATION_CREATED.value: CaseStatus.TO_APPLY.value,
    LifecycleEventType.APPLICATION_SENT.value: CaseStatus.APPLIED.value,
    LifecycleEventType.APPLICATION_RECEIVED.value: CaseStatus.CONFIRMATION.value,
    LifecycleEventType.UNDER_REVIEW.value: CaseStatus.CONFIRMATION.value,
    LifecycleEventType.DOCUMENT_REQUESTED.value: CaseStatus.CONFIRMATION.value,
    LifecycleEventType.ASSESSMENT_RECEIVED.value: CaseStatus.ASSESSMENT.value,
    LifecycleEventType.INTERVIEW_REQUESTED.value: CaseStatus.INTERVIEW.value,
    LifecycleEventType.INTERVIEW_SCHEDULED.value: CaseStatus.INTERVIEW.value,
    LifecycleEventType.INTERVIEW_RESCHEDULED.value: CaseStatus.INTERVIEW.value,
    LifecycleEventType.INTERVIEW_CANCELLED.value: CaseStatus.INTERVIEW.value,
    LifecycleEventType.INTERVIEW_COMPLETED.value: CaseStatus.INTERVIEW.value,
    LifecycleEventType.OFFER_RECEIVED.value: CaseStatus.OFFER.value,
    LifecycleEventType.REJECTION_RECEIVED.value: CaseStatus.REJECTED.value,
    LifecycleEventType.FOLLOWUP_SENT.value: None,
    LifecycleEventType.WITHDRAWN.value: CaseStatus.WITHDRAWN.value,
    LifecycleEventType.GHOSTED.value: CaseStatus.GHOSTED.value,
    LifecycleEventType.ARCHIVED.value: CaseStatus.CLOSED.value,
    LifecycleEventType.MANUAL_OVERRIDE.value: None,
}

STATUS_TO_SEED_EVENT: dict[str, str] = {
    CaseStatus.TO_APPLY.value: LifecycleEventType.APPLICATION_CREATED.value,
    CaseStatus.APPLIED.value: LifecycleEventType.APPLICATION_SENT.value,
    CaseStatus.CONFIRMATION.value: LifecycleEventType.APPLICATION_RECEIVED.value,
    CaseStatus.ASSESSMENT.value: LifecycleEventType.ASSESSMENT_RECEIVED.value,
    CaseStatus.INTERVIEW.value: LifecycleEventType.INTERVIEW_REQUESTED.value,
    CaseStatus.OFFER.value: LifecycleEventType.OFFER_RECEIVED.value,
    CaseStatus.REJECTED.value: LifecycleEventType.REJECTION_RECEIVED.value,
    CaseStatus.WITHDRAWN.value: LifecycleEventType.WITHDRAWN.value,
    CaseStatus.GHOSTED.value: LifecycleEventType.GHOSTED.value,
    CaseStatus.CLOSED.value: LifecycleEventType.ARCHIVED.value,
}

_CATEGORY_TO_EVENT: dict[str, str] = {
    "confirmation": LifecycleEventType.APPLICATION_RECEIVED.value,
    "eingangsbestaetigung": LifecycleEventType.APPLICATION_RECEIVED.value,
    "application_received": LifecycleEventType.APPLICATION_RECEIVED.value,
    "under_review": LifecycleEventType.UNDER_REVIEW.value,
    "assessment": LifecycleEventType.ASSESSMENT_RECEIVED.value,
    "document_request": LifecycleEventType.DOCUMENT_REQUESTED.value,
    "interview": LifecycleEventType.INTERVIEW_REQUESTED.value,
    "interview_invite": LifecycleEventType.INTERVIEW_REQUESTED.value,
    "interview_reschedule": LifecycleEventType.INTERVIEW_RESCHEDULED.value,
    "interview_cancelled": LifecycleEventType.INTERVIEW_CANCELLED.value,
    "offer": LifecycleEventType.OFFER_RECEIVED.value,
    "angebot": LifecycleEventType.OFFER_RECEIVED.value,
    "rejection": LifecycleEventType.REJECTION_RECEIVED.value,
    "abgelehnt": LifecycleEventType.REJECTION_RECEIVED.value,
    "ghosted": LifecycleEventType.GHOSTED.value,
}

_STATUS_TO_EVENT: dict[str, str] = dict(STATUS_TO_SEED_EVENT)


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
    legacy_status: str = ""

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


@dataclass(frozen=True)
class LifecycleEvent:
    event_type: str
    occurred_at: str = ""
    idempotency_key: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    id: str = ""
    case_id: str = ""
    recorded_at: str = ""
    source: str = ""
    confidence: float = 1.0

    def with_defaults(self) -> "LifecycleEvent":
        now = utc_now_iso()
        return LifecycleEvent(
            event_type=self.event_type,
            occurred_at=self.occurred_at or now,
            idempotency_key=self.idempotency_key or "",
            payload=dict(self.payload or {}),
            id=self.id,
            case_id=self.case_id,
            recorded_at=self.recorded_at or now,
            source=self.source or "",
            confidence=float(self.confidence),
        )


@dataclass(frozen=True)
class ReduceResult:
    status: str
    applied: tuple[str, ...] = ()
    ignored: tuple[tuple[str, str], ...] = ()


def can_transition(current: str, proposed: str, *, force: bool = False) -> bool:
    if force:
        return True
    if current == proposed:
        return True
    if current in TERMINAL_STATUSES:
        if proposed not in TERMINAL_STATUSES:
            return False
        return proposed in TERMINAL_HARDENING.get(current, frozenset())
    cur = STATUS_RANK.get(current, 0)
    nxt = STATUS_RANK.get(proposed, 0)
    return nxt >= cur


def email_category_to_lifecycle_event(category: str) -> str | None:
    return _CATEGORY_TO_EVENT.get((category or "").strip().lower())


def email_category_to_status(category: str) -> str | None:
    """Map classifier category → case status via lifecycle events (no LLM).

    UNKNOWN / review / noise / general never auto-map to a status.
    """
    event = email_category_to_lifecycle_event(category)
    if not event:
        return None
    return EVENT_STATUS_TARGET.get(event)


def status_to_lifecycle_event(status: str) -> str | None:
    return _STATUS_TO_EVENT.get((status or "").strip().lower())


def seed_event_for_status(status: str) -> str | None:
    key = (status or "").strip().lower()
    if key not in CANONICAL_CASE_STATUSES:
        return None
    return STATUS_TO_SEED_EVENT.get(key)


def _event_sort_key(ev: LifecycleEvent) -> tuple[str, str, str]:
    return (ev.occurred_at or "", ev.recorded_at or "", ev.id or "")


def _dedupe_by_idempotency(events: Sequence[LifecycleEvent]) -> list[LifecycleEvent]:
    ordered = sorted(events, key=_event_sort_key)
    seen: set[str] = set()
    out: list[LifecycleEvent] = []
    for ev in ordered:
        key = (ev.idempotency_key or "").strip()
        if key:
            if key in seen:
                continue
            seen.add(key)
        out.append(ev)
    return out


def _override_target(payload: dict[str, Any] | None) -> str | None:
    if not payload:
        return None
    for key in ("to", "status", "target_status", "new_status"):
        val = payload.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip().lower()
    return None


def reduce_lifecycle_events(
    events: Iterable[LifecycleEvent],
    *,
    initial_status: str = CaseStatus.TO_APPLY.value,
) -> ReduceResult:
    """Pure, deterministic status fold over lifecycle events."""
    normalized = [e.with_defaults() if not e.occurred_at else e for e in events]
    stream = _dedupe_by_idempotency(normalized)
    status = (initial_status or CaseStatus.TO_APPLY.value).strip().lower()
    applied: list[str] = []
    ignored: list[tuple[str, str]] = []

    for ev in stream:
        et = (ev.event_type or "").strip()
        if et == LifecycleEventType.MANUAL_OVERRIDE.value:
            target = _override_target(ev.payload)
            if not target:
                ignored.append((et, "override_missing_target"))
                continue
            if target not in CANONICAL_CASE_STATUSES:
                ignored.append((et, "override_unknown_status"))
                continue
            status = target
            applied.append(et)
            continue

        if et == LifecycleEventType.FOLLOWUP_SENT.value:
            ignored.append((et, "audit_only"))
            continue

        if et not in EVENT_STATUS_TARGET:
            ignored.append((et, "unknown_event"))
            continue

        proposed = EVENT_STATUS_TARGET[et]
        if proposed is None:
            ignored.append((et, "no_status_effect"))
            continue

        if status in TERMINAL_STATUSES and proposed != status:
            if proposed not in TERMINAL_HARDENING.get(status, frozenset()):
                ignored.append((et, "terminal_protection"))
                continue

        if not can_transition(status, proposed, force=False):
            ignored.append((et, "rank_or_terminal_blocked"))
            continue

        if status == proposed:
            applied.append(et)
            continue

        status = proposed
        applied.append(et)

    return ReduceResult(status=status, applied=tuple(applied), ignored=tuple(ignored))


def project_status(
    events: Iterable[LifecycleEvent],
    *,
    initial_status: str = CaseStatus.TO_APPLY.value,
) -> str:
    return reduce_lifecycle_events(events, initial_status=initial_status).status
