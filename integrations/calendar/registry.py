"""Calendar provider registry — explicit resolution only (NEXT-03).

HARD RULE: never try Google → Microsoft → CalDAV. One selected provider or error.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from integrations.calendar.contracts import CalendarProviderAdapter
from integrations.providers.enums import (
    AutoFallbackForbidden,
    CalendarProvider,
    ProviderError,
    parse_calendar_provider,
)


def resolve_calendar_adapter(
    provider: str | CalendarProvider | None,
    *,
    token_dir: Path | None = None,
    settings: Any | None = None,
    allow_none: bool = False,
) -> CalendarProviderAdapter | None:
    chosen = parse_calendar_provider(provider)
    if chosen is CalendarProvider.NONE:
        if allow_none:
            return None
        raise ProviderError(
            "calendar",
            "calendar_provider_not_selected",
            reconnectable=False,
        )

    if chosen is CalendarProvider.GOOGLE_CALENDAR:
        from integrations.calendar.google.adapter import GoogleCalendarAdapter

        return GoogleCalendarAdapter(token_dir=token_dir, settings=settings)

    if chosen is CalendarProvider.MICROSOFT_GRAPH:
        from integrations.calendar.microsoft.adapter import MicrosoftGraphCalendarAdapter

        return MicrosoftGraphCalendarAdapter(token_dir=token_dir, settings=settings)

    if chosen is CalendarProvider.GENERIC_CALDAV:
        from integrations.calendar.caldav.adapter import GenericCaldavCalendarAdapter

        return GenericCaldavCalendarAdapter(token_dir=token_dir, settings=settings)

    if chosen is CalendarProvider.FAKE_INPROCESS:
        from integrations.calendar.fake.adapter import FakeInProcessCalendarAdapter

        return FakeInProcessCalendarAdapter(token_dir=token_dir, settings=settings)

    raise ProviderError(
        "calendar", f"unsupported_calendar_provider:{chosen.value}", reconnectable=False
    )


def forbid_auto_fallback(*, attempted: list[str] | tuple[str, ...] | None = None) -> None:
    detail = "auto_provider_fallback_forbidden"
    if attempted:
        detail = f"{detail}:{','.join(attempted)}"
    raise AutoFallbackForbidden(detail)
