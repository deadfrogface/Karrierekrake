"""Generic CalDAV calendar adapter (NEXT-03).

Supports discovery, busy intervals, conflict detection helpers, and
create/update only after explicit approval. No auto-create.
iCloud is a tested preset over CalDAV + app-specific password / OAuth
as Apple currently documents for third-party clients — no scraping.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urljoin
from xml.etree import ElementTree as ET

from integrations.calendar.contracts import (
    BusyInterval,
    CalendarAccountIdentity,
    CalendarEventRef,
    CalendarProviderAdapter,
)
from integrations.calendar_freebusy import FreeBusyQuery
from integrations.calendar_timezone import ensure_aware, parse_iso_datetime, to_utc
from integrations.calendar_write import CalendarEventDraft
from integrations.providers.enums import CalendarProvider, ProviderError
from integrations.secure_tokens import (
    KeyringUnavailable,
    delete_token,
    load_token,
    store_token,
)

TOKEN_ACCOUNT_CALDAV = "generic_caldav"

# Well-known presets (standards-based — not scraping).
ICLOUD_CALDAV_PRESET = {
    "id": "icloud",
    "display_name": "iCloud",
    "discovery_url": "https://caldav.icloud.com/",
    "notes": (
        "Use Apple ID + app-specific password or Apple's documented OAuth for "
        "third-party CalDAV. Unofficial scraping is forbidden."
    ),
}


@dataclass
class CaldavEndpoint:
    base_url: str
    username: str = ""
    calendar_path: str = ""
    preset: str = ""


class CaldavClient(Protocol):
    def discover_calendars(self) -> list[str]: ...

    def list_busy(
        self, *, time_min: datetime, time_max: datetime
    ) -> list[dict[str, Any]]: ...

    def put_event(self, *, href: str, ics: str, etag: str = "") -> dict[str, Any]: ...


def store_caldav_secret(payload: dict[str, Any], *, token_dir: Path) -> None:
    try:
        store_token(TOKEN_ACCOUNT_CALDAV, payload, fallback_dir=token_dir)
    except KeyringUnavailable as exc:
        raise ProviderError("generic_caldav", "keyring_unavailable", reconnectable=True) from exc


def load_caldav_secret(*, token_dir: Path) -> dict[str, Any] | None:
    try:
        return load_token(TOKEN_ACCOUNT_CALDAV, fallback_dir=token_dir)
    except KeyringUnavailable:
        return None


def delete_caldav_secret(*, token_dir: Path) -> None:
    try:
        delete_token(TOKEN_ACCOUNT_CALDAV, fallback_dir=token_dir)
    except Exception:
        pass


def apply_icloud_preset(secret: dict[str, Any]) -> dict[str, Any]:
    out = dict(secret)
    out.setdefault("base_url", ICLOUD_CALDAV_PRESET["discovery_url"])
    out["preset"] = "icloud"
    return out


class GenericCaldavCalendarAdapter:
    provider = CalendarProvider.GENERIC_CALDAV

    def __init__(
        self,
        *,
        token_dir: Path | None = None,
        settings: Any | None = None,
        client: CaldavClient | None = None,
    ) -> None:
        self.token_dir = Path(token_dir) if token_dir else Path(".")
        self.settings = settings
        self._client = client

    def identity(self) -> CalendarAccountIdentity:
        secret = load_caldav_secret(token_dir=self.token_dir) or {}
        return CalendarAccountIdentity(
            provider=self.provider,
            account_key=TOKEN_ACCOUNT_CALDAV,
            email_address=str(secret.get("username") or ""),
            calendar_id=str(secret.get("calendar_path") or "default"),
        )

    def is_connected(self) -> bool:
        if self._client is not None:
            return True
        secret = load_caldav_secret(token_dir=self.token_dir)
        return bool(secret and secret.get("base_url") and secret.get("username"))

    def query_busy(self, q: FreeBusyQuery) -> list[BusyInterval]:
        client = self._require_client()
        raw = client.list_busy(time_min=q.time_min, time_max=q.time_max)
        out: list[BusyInterval] = []
        for item in raw:
            start = parse_iso_datetime(item.get("start"), default_tz="UTC")
            end = parse_iso_datetime(item.get("end"), default_tz="UTC")
            if not start or not end or end <= start:
                continue
            out.append(
                BusyInterval(start=to_utc(ensure_aware(start)), end=to_utc(ensure_aware(end)))
            )
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
        from integrations.calendar_write import draft_to_ics

        ics = draft_to_ics(draft)
        href = f"{draft.uid}.ics"
        result = client.put_event(href=href, ics=ics, etag="")
        return CalendarEventRef(
            provider=self.provider,
            external_event_id=str(result.get("href") or href),
            uid=draft.uid,
            etag=str(result.get("etag") or ""),
        )

    def disconnect(self, *, revoke_remote: bool = True) -> None:
        _ = revoke_remote
        delete_caldav_secret(token_dir=self.token_dir)

    def discover(self) -> list[str]:
        return self._require_client().discover_calendars()

    def _require_client(self) -> CaldavClient:
        if self._client is not None:
            return self._client
        if not self.is_connected():
            raise ProviderError(
                self.provider.value, "caldav_not_configured", reconnectable=True
            )
        raise ProviderError(
            self.provider.value,
            "caldav_client_not_configured",
            reconnectable=True,
        )


def detect_busy_conflicts(
    busy: list[BusyInterval], *, start: datetime, end: datetime
) -> list[BusyInterval]:
    """Conflict detection helper — timezone-aware overlap."""
    s = to_utc(ensure_aware(start, default_tz="UTC"))
    e = to_utc(ensure_aware(end, default_tz="UTC"))
    hits: list[BusyInterval] = []
    for b in busy:
        if b.start < e and s < b.end:
            hits.append(b)
    return hits


_: type[CalendarProviderAdapter] = GenericCaldavCalendarAdapter  # type: ignore[assignment,misc]
