"""Google Calendar adapter — FreeBusy + write gate transport (NEXT-03)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from integrations.calendar.contracts import (
    BusyInterval,
    CalendarAccountIdentity,
    CalendarEventRef,
    CalendarProviderAdapter,
)
from integrations.calendar_freebusy import FreeBusyQuery, GoogleFreeBusyProvider
from integrations.calendar_write import CalendarEventDraft
from integrations.providers.enums import CalendarProvider, ProviderError


class GoogleCalendarAdapter:
    provider = CalendarProvider.GOOGLE_CALENDAR

    def __init__(
        self,
        *,
        token_dir: Path | None = None,
        settings: Any | None = None,
        freebusy: Any | None = None,
        transport: Any | None = None,
    ) -> None:
        self.token_dir = Path(token_dir) if token_dir else Path(".")
        self.settings = settings
        self._freebusy = freebusy
        self._transport = transport

    def identity(self) -> CalendarAccountIdentity:
        return CalendarAccountIdentity(
            provider=self.provider,
            account_key="google_calendar",
            calendar_id="primary",
        )

    def is_connected(self) -> bool:
        """NEXT-04: Verbunden only after successful FreeBusy probe."""
        from integrations.providers.connection_probe import probe_google_calendar

        return probe_google_calendar(token_dir=self.token_dir).connected

    def query_busy(self, q: FreeBusyQuery) -> list[BusyInterval]:
        provider = self._freebusy or GoogleFreeBusyProvider(self._service())
        windows = provider.query(q)
        return [BusyInterval(start=w.start, end=w.end) for w in windows]

    def create_event(self, draft: CalendarEventDraft) -> CalendarEventRef:
        if not draft.approved:
            raise ProviderError(
                self.provider.value,
                "calendar_event_not_approved",
                reconnectable=False,
            )
        if self._transport is not None:
            ext = self._transport.create_event(draft)
        else:
            if not self.settings or not self.settings.allow_calendar_write:
                raise ProviderError(self.provider.value, "calendar_write_disabled", reconnectable=False)
            from integrations.calendar_timezone import parse_iso_datetime
            start, end = parse_iso_datetime(draft.start), parse_iso_datetime(draft.end)
            if not start or not end or end <= start:
                raise ProviderError(self.provider.value, "calendar_invalid_dates", reconnectable=False)
            import hashlib
            # Google event IDs use base32hex characters. Stable ID makes retries safe.
            event_id = hashlib.sha256(draft.uid.encode()).hexdigest()
            body = {"id": event_id, "summary": draft.title, "description": draft.description,
                    "location": draft.location, "start": {"dateTime": start.isoformat()},
                    "end": {"dateTime": end.isoformat()}}
            service = self._service()
            try:
                result = service.events().insert(calendarId="primary", body=body).execute()
            except Exception as exc:
                if getattr(getattr(exc, "resp", None), "status", None) != 409:
                    raise ProviderError(self.provider.value, "calendar_write_failed", reconnectable=True) from None
                result = service.events().get(calendarId="primary", eventId=event_id).execute()
                if any(result.get(k) != body[k] for k in ("summary", "description", "location")):
                    raise ProviderError(self.provider.value, "calendar_event_conflict", reconnectable=False)
                for field in ("start", "end"):
                    if parse_iso_datetime(result.get(field, {}).get("dateTime")) != parse_iso_datetime(body[field]["dateTime"]):
                        raise ProviderError(self.provider.value, "calendar_event_conflict", reconnectable=False)
            ext = result.get("id")
            if not ext:
                raise ProviderError(self.provider.value, "calendar_write_failed", reconnectable=True)
        return CalendarEventRef(
            provider=self.provider,
            external_event_id=str(ext),
            uid=draft.uid,
            calendar_id="primary",
        )

    def _service(self):
        from integrations.google_oauth import load_google_token, creds_from_payload, build_calendar_service
        payload = load_google_token(token_dir=self.token_dir)
        if not payload:
            raise ProviderError(self.provider.value, "google_calendar_not_connected", reconnectable=True)
        try:
            return build_calendar_service(creds_from_payload(payload))
        except Exception:
            raise ProviderError(self.provider.value, "google_calendar_not_connected", reconnectable=True) from None

    def disconnect(self, *, revoke_remote: bool = True) -> None:
        # Calendar shares Google token; disconnect is explicit Google disconnect.
        from integrations.google_oauth import disconnect_google

        disconnect_google(token_dir=self.token_dir, revoke_remote=revoke_remote)


_: type[CalendarProviderAdapter] = GoogleCalendarAdapter  # type: ignore[assignment,misc]
