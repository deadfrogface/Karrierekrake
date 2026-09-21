"""Fake mail adapter — SAME registry boundary as real providers (NEXT-06).

Activated only when:
  mail_provider == fake_inprocess
  AND KARRIEREKRAKE_ALLOW_FAKE_PROVIDERS=1

Never injects UI widget rows. Lifecycle consumes NormalizedEmail like production.
"""

from __future__ import annotations

import os
from typing import Any

from integrations.mail.contracts import (
    MailAccountIdentity,
    MailSyncCursor,
    MailSyncResult,
    NormalizedEmail,
)
from integrations.providers.enums import MailProvider, ProviderError


def fake_providers_allowed() -> bool:
    return os.environ.get("KARRIEREKRAKE_ALLOW_FAKE_PROVIDERS", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


class FakeInProcessMailAdapter:
    """In-process corpus mail — for destructive/chaos black-box only."""

    provider = MailProvider.FAKE_INPROCESS

    def __init__(
        self,
        *,
        token_dir: Any = None,
        settings: Any = None,
        messages: list[NormalizedEmail] | None = None,
    ) -> None:
        if not fake_providers_allowed():
            raise ProviderError(
                "mail",
                "fake_inprocess_requires_KARRIEREKRAKE_ALLOW_FAKE_PROVIDERS=1",
                reconnectable=False,
            )
        self._messages = list(messages or [])
        self._connected = True
        self._settings = settings

    def identity(self) -> MailAccountIdentity:
        return MailAccountIdentity(
            provider=self.provider,
            account_key="fake",
            email_address="fake-mailbox@example.test",
            display_name="Fake In-Process Mailbox",
        )

    def is_connected(self) -> bool:
        return self._connected

    def sync(self, *, cursor: MailSyncCursor | None = None) -> MailSyncResult:
        return MailSyncResult(
            provider=self.provider,
            mode="full",
            fetched=len(self._messages),
            processed=len(self._messages),
            messages=list(self._messages),
            new_cursor_token="fake-cursor-1",
        )

    def disconnect(self, *, revoke_remote: bool = True) -> None:
        del revoke_remote
        self._connected = False

    def seed(self, messages: list[NormalizedEmail]) -> None:
        """Test/harness only — not a UI inject."""
        self._messages = list(messages)
