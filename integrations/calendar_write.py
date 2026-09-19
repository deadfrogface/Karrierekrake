"""Approved calendar event creation — separate from slot proposal (PR31).

Never creates events without explicit user approval.
Failed create does NOT mark the case as SCHEDULED.
Writes are idempotent by client_request_id / uid.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Protocol

from core.lifecycle import CaseEventType, CaseStatus
from core.models import utc_now_iso
from integrations.calendar_scheduling import RankedSlot, SchedulingProposal
from integrations.calendar_timezone import isoformat_offset, isoformat_z, to_utc
from integrations.ics_export import build_meetings_ics

logger = logging.getLogger("karrierekrake.calendar")


@dataclass
class CalendarEventDraft:
    """Draft calendar event — not written until approved."""

    case_id: str
    title: str
    start: str
    end: str
    uid: str
    client_request_id: str
    description: str = ""
    location: str = ""
    modality: str = "remote"
    timezone: str = "Europe/Berlin"
    approved: bool = False
    created: bool = False
    create_error: str = ""
    external_event_id: str = ""
    created_at: str = field(default_factory=utc_now_iso)
    # Lifecycle: only set to interview/SCHEDULED path after successful create.
    lifecycle_status_on_success: str = CaseStatus.INTERVIEW.value

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "title": self.title,
            "start": self.start,
            "end": self.end,
            "uid": self.uid,
            "client_request_id": self.client_request_id,
            "description": self.description,
            "location": self.location,
            "modality": self.modality,
            "timezone": self.timezone,
            "approved": self.approved,
            "created": self.created,
            "create_error": self.create_error,
            "external_event_id": self.external_event_id,
            "created_at": self.created_at,
            "lifecycle_status_on_success": self.lifecycle_status_on_success,
        }


class CalendarTransport(Protocol):
    def create_event(self, draft: CalendarEventDraft) -> str:
        """Create event; return external id. Raise on failure."""


class InMemoryCalendarTransport:
    """Test double — stores events by uid; idempotent re-creates."""

    def __init__(self) -> None:
        self.events: dict[str, dict[str, Any]] = {}
        self.create_calls = 0
        self.fail_next = False

    def create_event(self, draft: CalendarEventDraft) -> str:
        self.create_calls += 1
        if self.fail_next:
            self.fail_next = False
            raise RuntimeError("calendar_transport_failed")
        if draft.uid in self.events:
            return str(self.events[draft.uid]["external_event_id"])
        ext = f"ext-{draft.uid}"
        self.events[draft.uid] = {
            **draft.to_dict(),
            "external_event_id": ext,
            # Never store private third-party titles from FreeBusy — draft title is ours.
        }
        return ext


def _stable_uid(*, case_id: str, start: str, client_request_id: str) -> str:
    digest = hashlib.sha256(
        f"{case_id}|{start}|{client_request_id}".encode("utf-8")
    ).hexdigest()[:24]
    return f"kk-interview-{digest}@karrierekrake.local"


def draft_from_ranked_slot(
    proposal: SchedulingProposal,
    *,
    slot_index: int | None = None,
    title: str = "Interview (Karrierekrake)",
    client_request_id: str = "",
    description: str = "",
    location: str = "",
) -> CalendarEventDraft:
    """Build a draft from a selected ranked slot. Does not write."""
    idx = proposal.selected_slot_index if slot_index is None else slot_index
    if idx is None or idx < 0 or idx >= len(proposal.ranked_slots):
        raise ValueError("no_slot_selected")
    slot: RankedSlot = proposal.ranked_slots[idx]
    req = (client_request_id or "").strip() or f"{proposal.case_id}:{isoformat_z(slot.start)}"
    uid = _stable_uid(case_id=proposal.case_id, start=isoformat_z(slot.start), client_request_id=req)
    return CalendarEventDraft(
        case_id=proposal.case_id,
        title=title or "Interview (Karrierekrake)",
        start=isoformat_offset(slot.start),
        end=isoformat_offset(slot.end),
        uid=uid,
        client_request_id=req,
        description=description,
        location=location,
        modality=slot.modality,
        timezone=slot.timezone,
        approved=False,
        created=False,
    )


def draft_to_ics(draft: CalendarEventDraft) -> str:
    """ICS export for the draft (user can import manually without API write)."""
    return build_meetings_ics(
        [
            {
                "uid": draft.uid,
                "title": draft.title,
                "scheduled_at": draft.start,
                "end": draft.end,
                "description": draft.description,
            }
        ]
    )


class CalendarWriteGate:
    """Approval-before-create + failure safety. Default refuses real write."""

    def __init__(self, *, allow_write: bool = False) -> None:
        self.allow_write = bool(allow_write)
        self._seen_request_ids: set[str] = set()
        self._results_by_request: dict[str, CalendarEventDraft] = {}

    def approve(self, draft: CalendarEventDraft) -> CalendarEventDraft:
        draft.approved = True
        return draft

    def attempt_create(
        self,
        draft: CalendarEventDraft,
        *,
        transport: CalendarTransport | Callable[[CalendarEventDraft], str],
    ) -> CalendarEventDraft:
        """Create only when approved and allow_write.

        On failure: create_error set, created=False — caller must NOT transition
        to SCHEDULED / interview_scheduled.
        Idempotent: same client_request_id returns prior success without duplicate.
        """
        # Idempotency: successful prior create
        prior = self._results_by_request.get(draft.client_request_id)
        if prior and prior.created:
            draft.created = True
            draft.external_event_id = prior.external_event_id
            draft.create_error = ""
            draft.approved = True
            return draft

        if not self.allow_write:
            draft.create_error = "write_disabled: calendar write requires allow_calendar_write"
            draft.created = False
            return draft
        if not draft.approved:
            draft.create_error = "not_approved"
            draft.created = False
            return draft

        try:
            if callable(transport) and not hasattr(transport, "create_event"):
                ext_id = transport(draft)  # type: ignore[operator]
            else:
                ext_id = transport.create_event(draft)  # type: ignore[union-attr]
            draft.created = True
            draft.external_event_id = str(ext_id)
            draft.create_error = ""
            self._seen_request_ids.add(draft.client_request_id)
            self._results_by_request[draft.client_request_id] = draft
            return draft
        except Exception as exc:
            logger.error("Calendar create failed: %s", type(exc).__name__)
            draft.created = False
            draft.external_event_id = ""
            draft.create_error = f"create_failed:{type(exc).__name__}"
            return draft

    @staticmethod
    def lifecycle_event_on_result(draft: CalendarEventDraft) -> str:
        """Which CaseEventType to emit — never SCHEDULED on failure."""
        if draft.created:
            return CaseEventType.CALENDAR_WRITE_APPROVED.value
        return CaseEventType.CALENDAR_WRITE_FAILED.value

    @staticmethod
    def may_mark_scheduled(draft: CalendarEventDraft) -> bool:
        """COMMERCIAL: Failed create != SCHEDULED."""
        return bool(draft.created and not draft.create_error)
