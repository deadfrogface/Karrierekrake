"""Explicit mail/calendar provider choice — NEVER auto-fallback (NEXT-03)."""

from __future__ import annotations

from enum import Enum


class MailProvider(str, Enum):
    NONE = "none"
    GOOGLE_GMAIL = "google_gmail"
    MICROSOFT_GRAPH = "microsoft_graph"
    GENERIC_IMAP = "generic_imap"


class CalendarProvider(str, Enum):
    NONE = "none"
    GOOGLE_CALENDAR = "google_calendar"
    MICROSOFT_GRAPH = "microsoft_graph"
    GENERIC_CALDAV = "generic_caldav"


class ProviderError(RuntimeError):
    """Chosen provider failed — reconnect or change provider explicitly."""

    def __init__(self, provider: str, message: str, *, reconnectable: bool = True) -> None:
        super().__init__(message)
        self.provider = provider
        self.reconnectable = reconnectable
        self.code = "PROVIDER_ERROR"


class AutoFallbackForbidden(RuntimeError):
    """Raised if any code path attempts silent provider switching."""

    def __init__(self, detail: str = "auto_provider_fallback_forbidden") -> None:
        super().__init__(detail)
        self.code = "AUTO_PROVIDER_FALLBACK_FORBIDDEN"


def parse_mail_provider(value: str | MailProvider | None) -> MailProvider:
    if value is None or value == "":
        return MailProvider.NONE
    if isinstance(value, MailProvider):
        return value
    raw = str(value).strip().lower()
    # Migration aliases
    if raw in {"gmail", "google", "google_gmail"}:
        return MailProvider.GOOGLE_GMAIL
    if raw in {"microsoft", "outlook", "microsoft_graph", "ms_graph"}:
        return MailProvider.MICROSOFT_GRAPH
    if raw in {"imap", "generic_imap", "other"}:
        return MailProvider.GENERIC_IMAP
    if raw in {"none", "off", "disabled"}:
        return MailProvider.NONE
    try:
        return MailProvider(raw)
    except ValueError as exc:
        raise ProviderError("mail", f"unknown_mail_provider:{raw}", reconnectable=False) from exc


def parse_calendar_provider(value: str | CalendarProvider | None) -> CalendarProvider:
    if value is None or value == "":
        return CalendarProvider.NONE
    if isinstance(value, CalendarProvider):
        return value
    raw = str(value).strip().lower()
    if raw in {"google", "google_calendar", "gcal"}:
        return CalendarProvider.GOOGLE_CALENDAR
    if raw in {"microsoft", "outlook", "microsoft_graph", "ms_graph"}:
        return CalendarProvider.MICROSOFT_GRAPH
    if raw in {"caldav", "generic_caldav", "icloud", "other"}:
        return CalendarProvider.GENERIC_CALDAV
    if raw in {"none", "off", "disabled", "kein"}:
        return CalendarProvider.NONE
    try:
        return CalendarProvider(raw)
    except ValueError as exc:
        raise ProviderError(
            "calendar", f"unknown_calendar_provider:{raw}", reconnectable=False
        ) from exc
