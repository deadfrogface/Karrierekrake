"""Fake calendar adapter — SAME registry boundary as real providers (NEXT-06)."""

from __future__ import annotations

from typing import Any

from integrations.calendar.contracts import (
    BusyInterval,
    CalendarAccountIdentity,
    CalendarEventRef,
)
from integrations.calendar_freebusy import FreeBusyQuery
from integrations.calendar_write import CalendarEventDraft
from integrations.mail.fake.adapter import fake_providers_allowed
from integrations.providers.enums import CalendarProvider, ProviderError


class FakeInProcessCalendarAdapter:
    provider = CalendarProvider.FAKE_INPROCESS

    def __init__(
        self,
        *,
        token_dir: Any = None,
        settings: Any = None,
    ) -> None:
        if not fake_providers_allowed():
            raise ProviderError(
                "calendar",
                "fake_inprocess_requires_KARRIEREKRAKE_ALLOW_FAKE_PROVIDERS=1",
                reconnectable=False,
            )
        self._connected = True
        self._created: list[CalendarEventDraft] = []
        self._busy: list[BusyInterval] = []

    def identity(self) -> CalendarAccountIdentity:
        return CalendarAccountIdentity(
            provider=self.provider,
            account_key="fake",
            email_address="fake-cal@example.test",
            display_name="Fake In-Process Calendar",
        )

    def is_connected(self) -> bool:
        return self._connected

    def query_busy(self, q: FreeBusyQuery) -> list[BusyInterval]:
        del q
        return list(self._busy)

    def create_event(self, draft: CalendarEventDraft) -> CalendarEventRef:
        # Idempotent by client_request_id
        for existing in self._created:
            if existing.client_request_id and existing.client_request_id == draft.client_request_id:
                return CalendarEventRef(
                    provider=self.provider,
                    external_event_id=f"fake-dup-{draft.client_request_id}",
                    uid=draft.uid,
                )
        self._created.append(draft)
        return CalendarEventRef(
            provider=self.provider,
            external_event_id=f"fake-{len(self._created)}",
            uid=draft.uid or f"kk-fake-{len(self._created)}",
        )

    def disconnect(self, *, revoke_remote: bool = True) -> None:
        del revoke_remote
        self._connected = False
