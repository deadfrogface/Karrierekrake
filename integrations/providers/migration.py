"""Migrate legacy Google-only settings to explicit providers (NEXT-03).

Does NOT destroy tokens unless a separate security action requires it.
"""

from __future__ import annotations

from typing import Any

from integrations.providers.enums import CalendarProvider, MailProvider


def migrate_provider_settings(settings: Any) -> dict[str, str]:
    """Ensure mail_provider / calendar_provider are set from legacy flags.

    Returns a dict of fields that were changed (for logging / UI notes).
    """
    changed: dict[str, str] = {}
    mail = str(getattr(settings, "mail_provider", "") or "").strip().lower()
    cal = str(getattr(settings, "calendar_provider", "") or "").strip().lower()

    if not mail or mail in {"", "auto"}:
        if bool(getattr(settings, "gmail_sync_enabled", False)):
            settings.mail_provider = MailProvider.GOOGLE_GMAIL.value
            changed["mail_provider"] = MailProvider.GOOGLE_GMAIL.value
        else:
            # Keep none unless a Google token connection is implied by legacy default.
            settings.mail_provider = getattr(settings, "mail_provider", None) or MailProvider.NONE.value
            if not str(getattr(settings, "mail_provider", "") or ""):
                settings.mail_provider = MailProvider.NONE.value

    if not cal or cal in {"", "auto"}:
        if bool(getattr(settings, "calendar_freebusy_enabled", False)):
            settings.calendar_provider = CalendarProvider.GOOGLE_CALENDAR.value
            changed["calendar_provider"] = CalendarProvider.GOOGLE_CALENDAR.value
        else:
            if not str(getattr(settings, "calendar_provider", "") or ""):
                settings.calendar_provider = CalendarProvider.NONE.value

    # Coerce aliases
    from integrations.providers.enums import parse_calendar_provider, parse_mail_provider

    settings.mail_provider = parse_mail_provider(settings.mail_provider).value
    settings.calendar_provider = parse_calendar_provider(settings.calendar_provider).value
    return changed


def infer_google_mail_if_token_present(settings: Any, *, gmail_connected: bool) -> dict[str, str]:
    """If user already has Gmail token and provider still none → set GOOGLE_GMAIL."""
    changed: dict[str, str] = {}
    mail = parse_mail_if_needed(settings)
    if mail is MailProvider.NONE and gmail_connected:
        settings.mail_provider = MailProvider.GOOGLE_GMAIL.value
        changed["mail_provider"] = MailProvider.GOOGLE_GMAIL.value
    return changed


def parse_mail_if_needed(settings: Any) -> MailProvider:
    from integrations.providers.enums import parse_mail_provider

    return parse_mail_provider(getattr(settings, "mail_provider", None))
