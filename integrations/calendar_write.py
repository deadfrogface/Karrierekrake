"""Approved calendar event creation — separate from slot proposal (PR31).

Never creates events without explicit user approval.
Failed create does NOT mark the case as SCHEDULED.
Writes are idempotent by client_request_id / uid.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Protocol

from core.lifecycle import CaseEventType, CaseStatus
from core.models import utc_now_iso
from integrations.calendar_scheduling import RankedSlot, SchedulingProposal
from integrations.calendar_timezone import isoformat_offset, isoformat_z, to_utc

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


# "Ort: Firma, Straße 3, 3. OG, Raum X," + next line "00000 Stadt. Bitte ..."
# -> everything up to the postcode and city.
_LOCATION_LABEL_RE = re.compile(r"^\s*(?:ort|adresse|anschrift|treffpunkt|location)\s*:\s*(.+)$", re.IGNORECASE | re.MULTILINE)
# City: one capitalised word, optionally "am Main" / "(Saale)"; a following sentence is not part of it.
_POSTCODE_CITY_RE = re.compile(r"\b\d{4,5}\s+[A-ZÄÖÜ][\wäöüß\-]*(?:\s+am\s+[A-ZÄÖÜ][\wäöüß\-]*|\s+\([^)]*\))?")


def interview_location(text: str) -> str:
    """Location as the employer wrote it after an 'Ort:' label (no guessing)."""
    match = _LOCATION_LABEL_RE.search(text or "")
    if not match:
        return ""
    paragraph = re.split(r"\n\s*\n", (text or "")[match.start(1):], maxsplit=1)[0]
    flat = " ".join(line.strip() for line in paragraph.splitlines() if line.strip())
    city = _POSTCODE_CITY_RE.search(flat)
    value = flat[: city.end()] if city else flat.split(". ", 1)[0]
    return value.strip().rstrip(".,;")


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
        location=location or interview_location(proposal.proposal_text),
        modality=slot.modality,
        timezone=slot.timezone,
        approved=False,
        created=False,
    )


def draft_to_ics(draft: CalendarEventDraft) -> str:
    """ICS export for the draft (user can import manually without API write).

    Start/end are written in the draft's time zone (DTSTART;TZID=Europe/Berlin:...)
    with a VTIMEZONE, so the local time the employer offered stays visible.
    """
    from zoneinfo import ZoneInfo

    from icalendar import Calendar, Event

    zone = ZoneInfo(draft.timezone or "Europe/Berlin")
    start = datetime.fromisoformat(draft.start)
    end = datetime.fromisoformat(draft.end) if draft.end else None
    if start.tzinfo is None or (end is not None and end.tzinfo is None):
        raise ValueError("naive_event_time")
    cal = Calendar()
    cal.add("prodid", "-//Karrierekrake//DE")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("method", "PUBLISH")
    event = Event()
    event.add("uid", draft.uid)
    event.add("dtstamp", to_utc(datetime.now(zone)))
    event.add("dtstart", start.astimezone(zone))
    if end is not None:
        event.add("dtend", end.astimezone(zone))
    # Availability-safe default title — never leak private calendar titles outward.
    event.add("summary", draft.title or "Interview (Karrierekrake)")
    if draft.description:
        event.add("description", draft.description)
    if draft.location:
        event.add("location", draft.location)
    cal.add_component(event)
    cal.add_missing_timezones()
    return cal.to_ical().decode("utf-8")


def export_approved_ics(draft: CalendarEventDraft, destination: "Path") -> "Path":
    """Explicit, offline export for importing into Outlook, iCloud or Google.

    Export is not proof of calendar insertion; never set draft.created here.
    """
    from pathlib import Path

    if not draft.approved:
        raise PermissionError("Bitte den Termin vor dem Export bestätigen.")
    from integrations.calendar_timezone import parse_iso_datetime

    start = parse_iso_datetime(draft.start)
    end = parse_iso_datetime(draft.end)
    if start is None or end is None or end <= start:
        raise ValueError("Ungültige Terminzeiten.")
    path = Path(destination)
    if path.suffix.lower() != ".ics":
        raise ValueError("Nur .ics-Dateien sind erlaubt.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(draft_to_ics(draft), encoding="utf-8", newline="")
    return path


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


# --------------------------------------------------------------------------
# Cancellation of an existing appointment (T01.10 M9).
#
# When an employer cancels an appointment that is already in the user's
# calendar, Karrierekrake only PROPOSES an update of that same event:
# same UID, SEQUENCE + 1, STATUS:CANCELLED. Nothing is written or exported
# until the user approves (CalendarWriteGate.approve / draft.approved).
# --------------------------------------------------------------------------

_DATE_IN_TEXT = re.compile(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b")
_TIME_IN_TEXT = re.compile(r"\b(\d{1,2}):(\d{2})\b")


@dataclass
class CalendarCancellationDraft:
    """Proposed CANCELLED update of an existing event — not written until approved."""

    uid: str
    sequence: int
    original_sequence: int
    summary: str
    start: datetime
    end: datetime | None
    location: str = ""
    approved: bool = False
    created_at: str = field(default_factory=utc_now_iso)


def _event_start_end(event: Any) -> tuple[datetime | None, datetime | None]:
    start = event.decoded("DTSTART") if event.get("DTSTART") is not None else None
    end = event.decoded("DTEND") if event.get("DTEND") is not None else None
    if not isinstance(start, datetime):
        return None, None
    return start, end if isinstance(end, datetime) else None


def propose_cancellation_update(
    calendar_ics: str | bytes,
    mail_text: str,
    *,
    now: datetime,
) -> list[CalendarCancellationDraft]:
    """Find the existing, still active event a cancellation mail refers to.

    The mail must name the appointment date (dd.mm.yyyy); if it also names a
    start time, the event must start then. Only future, non-cancelled events
    count. Exactly one match yields one proposal; none or several yield none
    (never guess which appointment was meant).
    """
    from icalendar import Calendar

    dates = {(int(y), int(m), int(d)) for d, m, y in _DATE_IN_TEXT.findall(mail_text or "")}
    times = {(int(h), int(mi)) for h, mi in _TIME_IN_TEXT.findall(mail_text or "")}
    if not dates:
        return []
    cal = Calendar.from_ical(calendar_ics)
    matches: list[Any] = []
    for event in cal.walk("VEVENT"):
        if str(event.get("STATUS", "")).upper() == "CANCELLED" or event.get("RRULE") is not None:
            continue
        start, _end = _event_start_end(event)
        if start is None or start.tzinfo is None or start < now:
            continue
        if (start.year, start.month, start.day) not in dates:
            continue
        if times and (start.hour, start.minute) not in times:
            continue
        matches.append(event)
    if len(matches) != 1:
        return []
    event = matches[0]
    start, end = _event_start_end(event)
    original = int(event.get("SEQUENCE", 0) or 0)
    return [
        CalendarCancellationDraft(
            uid=str(event.get("UID")),
            sequence=original + 1,
            original_sequence=original,
            summary=str(event.get("SUMMARY", "")),
            start=start,
            end=end,
            location=str(event.get("LOCATION", "")),
        )
    ]


def cancellation_to_ics(drafts: list[CalendarCancellationDraft]) -> str:
    """VCALENDAR with one CANCELLED VEVENT per draft (same UID, higher SEQUENCE).

    Start/end keep their original time zone (DTSTART;TZID=...). No attendees
    or organizer are added.
    """
    from icalendar import Calendar, Event

    cal = Calendar()
    cal.add("prodid", "-//Karrierekrake//DE")
    cal.add("version", "2.0")
    cal.add("method", "PUBLISH")
    for d in drafts:
        ev = Event()
        ev.add("uid", d.uid)
        ev.add("dtstamp", to_utc(datetime.now(d.start.tzinfo)))
        ev.add("sequence", d.sequence)
        ev.add("status", "CANCELLED")
        ev.add("summary", d.summary)
        ev.add("dtstart", d.start)
        if d.end is not None:
            ev.add("dtend", d.end)
        if d.location:
            ev.add("location", d.location)
        cal.add_component(ev)
    return cal.to_ical().decode("utf-8")


def export_approved_cancellation_ics(draft: CalendarCancellationDraft, destination: str | Path) -> Path:
    """Offline export of an approved cancellation update; refuses without approval."""
    if not draft.approved:
        raise PermissionError("Bitte die Terminabsage vor dem Export bestätigen.")
    if draft.sequence <= draft.original_sequence:
        raise ValueError("SEQUENCE must increase for an update.")
    path = Path(destination)
    if path.suffix.lower() != ".ics":
        raise ValueError("Nur .ics-Dateien sind erlaubt.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(cancellation_to_ics([draft]), encoding="utf-8", newline="")
    return path
