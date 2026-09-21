"""Google Gmail adapter — wraps existing gmail_sync / gmail_auth (NEXT-03)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from integrations.mail.contracts import (
    MailAccountIdentity,
    MailProviderAdapter,
    MailSyncCursor,
    MailSyncResult,
    NormalizedEmail,
)
from integrations.providers.enums import MailProvider, ProviderError


class GoogleGmailAdapter:
    provider = MailProvider.GOOGLE_GMAIL

    def __init__(
        self,
        *,
        token_dir: Path | None = None,
        settings: Any | None = None,
        service: Any | None = None,
    ) -> None:
        self.token_dir = Path(token_dir) if token_dir else Path(".")
        self.settings = settings
        self._service = service

    def identity(self) -> MailAccountIdentity:
        return MailAccountIdentity(
            provider=self.provider,
            account_key="gmail_readonly",
            email_address="",
        )

    def is_connected(self) -> bool:
        from integrations.gmail_auth import gmail_connected

        return bool(gmail_connected(token_dir=self.token_dir))

    def _service_or_raise(self) -> Any:
        if self._service is not None:
            return self._service
        from integrations.gmail_auth import get_gmail_service

        svc = get_gmail_service(token_dir=self.token_dir)
        if svc is None:
            raise ProviderError(
                self.provider.value,
                "google_gmail_not_connected",
                reconnectable=True,
            )
        return svc

    def sync(self, *, cursor: MailSyncCursor | None = None) -> MailSyncResult:
        from integrations.gmail_sync import SyncCursor, run_robust_sync

        service = self._service_or_raise()
        legacy = SyncCursor(
            history_id=(cursor.cursor_token if cursor else "") or "",
            account_key=(cursor.account_key if cursor else "default"),
            resume_page_token=(cursor.resume_page_token if cursor else "") or "",
            sync_mode=(cursor.sync_mode if cursor else "") or "",
            pending_message_ids=list(cursor.pending_message_ids) if cursor else [],
        )

        class _Mem:
            def __init__(self, c: SyncCursor) -> None:
                self._c = c

            def load(self) -> SyncCursor:
                return self._c

            def save(self, c: SyncCursor) -> None:
                self._c = c

        store = _Mem(legacy)
        result = run_robust_sync(service, cursor_store=store)
        # run_robust_sync returns SyncResult without messages list in some paths —
        # expose normalized empty list; callers that need bodies use parse helpers.
        messages: list[NormalizedEmail] = []
        return MailSyncResult(
            provider=self.provider,
            mode=getattr(result, "mode", "") or "",
            fetched=int(getattr(result, "fetched", 0) or 0),
            processed=int(getattr(result, "processed", 0) or 0),
            skipped_duplicates=int(getattr(result, "skipped_duplicates", 0) or 0),
            new_cursor_token=str(getattr(result, "new_history_id", "") or store.load().history_id),
            resumed=bool(getattr(result, "resumed", False)),
            partial=bool(getattr(result, "partial", False)),
            errors=list(getattr(result, "errors", []) or []),
            needs_reauth=bool(getattr(result, "needs_reauth", False)),
            messages=messages,
        )

    def disconnect(self, *, revoke_remote: bool = True) -> None:
        from integrations.gmail_auth import disconnect_gmail

        disconnect_gmail(token_dir=self.token_dir, revoke_remote=revoke_remote)


def normalized_from_parsed_email(parsed: Any) -> NormalizedEmail:
    """Map legacy gmail_sync.ParsedEmail → NormalizedEmail."""
    mid = str(getattr(parsed, "id", "") or "")
    return NormalizedEmail(
        provider=MailProvider.GOOGLE_GMAIL,
        external_message_id=mid,
        thread_id=str(getattr(parsed, "thread_id", "") or ""),
        subject=str(getattr(parsed, "subject", "") or ""),
        sender=str(getattr(parsed, "sender", "") or ""),
        snippet=str(getattr(parsed, "snippet", "") or ""),
        body_text=str(getattr(parsed, "body_text", "") or ""),
        internal_date=str(getattr(parsed, "internal_date", "") or ""),
        label_ids=list(getattr(parsed, "label_ids", []) or []),
        provider_message_id=mid,
    )


# Protocol satisfaction hint for type checkers
_: type[MailProviderAdapter] = GoogleGmailAdapter  # type: ignore[assignment,misc]
