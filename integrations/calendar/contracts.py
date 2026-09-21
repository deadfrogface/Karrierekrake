"""Normalized calendar contracts — independent of Google types (NEXT-03)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from integrations.calendar_availability import TimeWindow
from integrations.calendar_freebusy import FreeBusyQuery
from integrations.calendar_write import CalendarEventDraft
from integrations.providers.enums import CalendarProvider


@dataclass
class CalendarAccountIdentity:
    provider: CalendarProvider
    account_key: str
    email_address: str = ""
    display_name: str = ""
    provider_user_id: str = ""
    calendar_id: str = "primary"

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider.value,
            "account_key": self.account_key,
            "email_address": self.email_address,
            "display_name": self.display_name,
            "provider_user_id": self.provider_user_id,
            "calendar_id": self.calendar_id,
        }


@dataclass(frozen=True)
class BusyInterval:
    """Opaque busy window — never carries third-party event titles."""

    start: datetime
    end: datetime

    def to_time_window(self) -> TimeWindow:
        return TimeWindow(start=self.start, end=self.end)


@dataclass
class CalendarEventRef:
    provider: CalendarProvider
    external_event_id: str
    uid: str = ""
    calendar_id: str = "primary"
    etag: str = ""


@dataclass
class CalendarProposal:
    """User-facing proposal before approval — maps to CalendarEventDraft."""

    case_id: str
    title: str
    start: str
    end: str
    timezone: str = "Europe/Berlin"
    location: str = ""
    modality: str = "remote"
    description: str = ""
    client_request_id: str = ""

    def to_draft(self) -> CalendarEventDraft:
        import hashlib

        from core.models import utc_now_iso

        cid = self.client_request_id or f"{self.case_id}:{self.start}"
        digest = hashlib.sha256(cid.encode("utf-8")).hexdigest()[:24]
        return CalendarEventDraft(
            case_id=self.case_id,
            title=self.title,
            start=self.start,
            end=self.end,
            uid=f"kk-{digest}",
            client_request_id=cid,
            description=self.description,
            location=self.location,
            modality=self.modality,
            timezone=self.timezone,
            created_at=utc_now_iso(),
        )


class CalendarProviderAdapter(Protocol):
    """Explicit adapter for one CalendarProvider. No cross-provider failover."""

    provider: CalendarProvider

    def identity(self) -> CalendarAccountIdentity: ...

    def is_connected(self) -> bool: ...

    def query_busy(self, q: FreeBusyQuery) -> list[BusyInterval]: ...

    def create_event(self, draft: CalendarEventDraft) -> CalendarEventRef: ...

    def disconnect(self, *, revoke_remote: bool = True) -> None: ...
