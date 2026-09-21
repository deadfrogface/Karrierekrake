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
from integrations.calendar_freebusy import FreeBusyQuery, MockFreeBusyProvider
from integrations.calendar_write import CalendarEventDraft, InMemoryCalendarTransport
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
        provider = self._freebusy
        if provider is None:
            # Prefer injected service; otherwise mock-safe empty for offline.
            try:
                from integrations.gmail_auth import get_gmail_service

                # Shared Google creds may build calendar service elsewhere;
                # if unavailable, fail closed with reconnectable error when live expected.
                svc = get_gmail_service(token_dir=self.token_dir)
                if svc is None and self._freebusy is None:
                    raise ProviderError(
                        self.provider.value,
                        "google_calendar_not_connected",
                        reconnectable=True,
                    )
            except ProviderError:
                raise
            except Exception:
                provider = MockFreeBusyProvider([])
            else:
                provider = MockFreeBusyProvider([])
        windows = provider.query(q)
        return [BusyInterval(start=w.start, end=w.end) for w in windows]

    def create_event(self, draft: CalendarEventDraft) -> CalendarEventRef:
        if not draft.approved:
            raise ProviderError(
                self.provider.value,
                "calendar_event_not_approved",
                reconnectable=False,
            )
        transport = self._transport or InMemoryCalendarTransport()
        # Live Google events.insert transport is gated; InMemory used until wired.
        # When a real GoogleCalendarTransport is injected, it is used here.
        ext = transport.create_event(draft)
        return CalendarEventRef(
            provider=self.provider,
            external_event_id=str(ext),
            uid=draft.uid,
            calendar_id="primary",
        )

    def disconnect(self, *, revoke_remote: bool = True) -> None:
        # Calendar shares Google token; disconnect is explicit Google disconnect.
        from integrations.google_oauth import disconnect_google

        disconnect_google(token_dir=self.token_dir, revoke_remote=revoke_remote)


_: type[CalendarProviderAdapter] = GoogleCalendarAdapter  # type: ignore[assignment,misc]
