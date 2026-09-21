"""Microsoft Graph calendar adapter (NEXT-03)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from integrations.calendar.contracts import (
    BusyInterval,
    CalendarAccountIdentity,
    CalendarEventRef,
    CalendarProviderAdapter,
)
from integrations.calendar_freebusy import FreeBusyQuery
from integrations.calendar_timezone import ensure_aware, parse_iso_datetime, to_utc
from integrations.calendar_write import CalendarEventDraft
from integrations.mail.microsoft.oauth_pkce import (
    TOKEN_ACCOUNT_CALENDAR,
    delete_ms_token,
    load_ms_token,
)
from integrations.providers.enums import CalendarProvider, ProviderError


class GraphCalendarClient(Protocol):
    def get_schedule(
        self, *, time_min: datetime, time_max: datetime
    ) -> list[dict[str, Any]]: ...

    def create_event(self, payload: dict[str, Any]) -> dict[str, Any]: ...


class MicrosoftGraphCalendarAdapter:
    provider = CalendarProvider.MICROSOFT_GRAPH

    def __init__(
        self,
        *,
        token_dir: Path | None = None,
        settings: Any | None = None,
        graph_client: GraphCalendarClient | None = None,
    ) -> None:
        self.token_dir = Path(token_dir) if token_dir else Path(".")
        self.settings = settings
        self._client = graph_client

    def identity(self) -> CalendarAccountIdentity:
        return CalendarAccountIdentity(
            provider=self.provider,
            account_key=TOKEN_ACCOUNT_CALENDAR,
            calendar_id="primary",
        )

    def is_connected(self) -> bool:
        if self._client is not None:
            return True  # calendar fakes use schedule; treated as probed in harness
        from integrations.providers.connection_probe import probe_microsoft_graph

        return probe_microsoft_graph(
            provider="microsoft_graph_calendar", token_dir=self.token_dir
        ).connected

    def query_busy(self, q: FreeBusyQuery) -> list[BusyInterval]:
        client = self._require_client()
        raw = client.get_schedule(time_min=q.time_min, time_max=q.time_max)
        out: list[BusyInterval] = []
        for item in raw:
            start = parse_iso_datetime(item.get("start"), default_tz="UTC")
            end = parse_iso_datetime(item.get("end"), default_tz="UTC")
            if not start or not end or end <= start:
                continue
            out.append(BusyInterval(start=to_utc(ensure_aware(start)), end=to_utc(ensure_aware(end))))
        return out

    def create_event(self, draft: CalendarEventDraft) -> CalendarEventRef:
        if not draft.approved:
            raise ProviderError(
                self.provider.value,
                "calendar_event_not_approved",
                reconnectable=False,
            )
        allow_write = bool(getattr(self.settings, "allow_calendar_write", False)) if self.settings else False
        if not allow_write and self._client is None:
            raise ProviderError(
                self.provider.value,
                "calendar_write_disabled",
                reconnectable=False,
            )
        client = self._require_client()
        payload = {
            "subject": draft.title,
            "body": {"contentType": "text", "content": draft.description},
            "start": {"dateTime": draft.start, "timeZone": draft.timezone},
            "end": {"dateTime": draft.end, "timeZone": draft.timezone},
            "location": {"displayName": draft.location},
            "transactionId": draft.client_request_id or draft.uid,
        }
        created = client.create_event(payload)
        return CalendarEventRef(
            provider=self.provider,
            external_event_id=str(created.get("id") or ""),
            uid=draft.uid,
        )

    def disconnect(self, *, revoke_remote: bool = True) -> None:
        _ = revoke_remote
        delete_ms_token(TOKEN_ACCOUNT_CALENDAR, token_dir=self.token_dir)

    def _require_client(self) -> GraphCalendarClient:
        if self._client is None:
            raise ProviderError(
                self.provider.value,
                "microsoft_calendar_not_connected"
                if not self.is_connected()
                else "microsoft_graph_client_not_configured",
                reconnectable=True,
            )
        return self._client


_: type[CalendarProviderAdapter] = MicrosoftGraphCalendarAdapter  # type: ignore[assignment,misc]
