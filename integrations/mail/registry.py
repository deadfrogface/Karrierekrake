"""Mail provider registry — explicit resolution only (NEXT-03).

HARD RULE: never try Gmail → Outlook → IMAP. One selected provider or error.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from integrations.mail.contracts import MailProviderAdapter
from integrations.providers.enums import (
    AutoFallbackForbidden,
    MailProvider,
    ProviderError,
    parse_mail_provider,
)


def resolve_mail_adapter(
    provider: str | MailProvider | None,
    *,
    token_dir: Path | None = None,
    settings: Any | None = None,
    allow_none: bool = False,
) -> MailProviderAdapter | None:
    """Return the adapter for the *chosen* provider only.

    Raises ProviderError if the provider is unset (unless allow_none) or unknown.
    Never silently substitutes another provider.
    """
    chosen = parse_mail_provider(provider)
    if chosen is MailProvider.NONE:
        if allow_none:
            return None
        raise ProviderError(
            "mail",
            "mail_provider_not_selected",
            reconnectable=False,
        )

    if chosen is MailProvider.GOOGLE_GMAIL:
        from integrations.mail.google.adapter import GoogleGmailAdapter

        return GoogleGmailAdapter(token_dir=token_dir, settings=settings)

    if chosen is MailProvider.MICROSOFT_GRAPH:
        from integrations.mail.microsoft.adapter import MicrosoftGraphMailAdapter

        return MicrosoftGraphMailAdapter(token_dir=token_dir, settings=settings)

    if chosen is MailProvider.GENERIC_IMAP:
        from integrations.mail.imap.adapter import GenericImapMailAdapter

        return GenericImapMailAdapter(token_dir=token_dir, settings=settings)

    if chosen is MailProvider.FAKE_INPROCESS:
        from integrations.mail.fake.adapter import FakeInProcessMailAdapter

        return FakeInProcessMailAdapter(token_dir=token_dir, settings=settings)

    raise ProviderError("mail", f"unsupported_mail_provider:{chosen.value}", reconnectable=False)


def forbid_auto_fallback(*, attempted: list[str] | tuple[str, ...] | None = None) -> None:
    """Call from any path that would chain providers — always raises."""
    detail = "auto_provider_fallback_forbidden"
    if attempted:
        detail = f"{detail}:{','.join(attempted)}"
    raise AutoFallbackForbidden(detail)
