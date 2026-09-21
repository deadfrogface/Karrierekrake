"""Microsoft Graph mail adapter (NEXT-03).

Uses delegated Mail.Read. Live Graph calls require stored PKCE tokens.
Tests inject ``graph_client`` doubles.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from integrations.mail.contracts import (
    MailAccountIdentity,
    MailProviderAdapter,
    MailSyncCursor,
    MailSyncResult,
    NormalizedEmail,
)
from integrations.mail.microsoft.oauth_pkce import (
    TOKEN_ACCOUNT_MAIL,
    delete_ms_token,
    load_ms_token,
)
from integrations.providers.enums import MailProvider, ProviderError


class GraphMailClient(Protocol):
    def list_messages(self, *, delta_link: str = "") -> tuple[list[dict[str, Any]], str]: ...

    def get_profile(self) -> dict[str, Any]: ...


class MicrosoftGraphMailAdapter:
    provider = MailProvider.MICROSOFT_GRAPH

    def __init__(
        self,
        *,
        token_dir: Path | None = None,
        settings: Any | None = None,
        graph_client: GraphMailClient | None = None,
    ) -> None:
        self.token_dir = Path(token_dir) if token_dir else Path(".")
        self.settings = settings
        self._client = graph_client

    def identity(self) -> MailAccountIdentity:
        email = ""
        oid = ""
        if self._client is not None:
            try:
                prof = self._client.get_profile()
                email = str(prof.get("mail") or prof.get("userPrincipalName") or "")
                oid = str(prof.get("id") or "")
            except Exception:
                pass
        return MailAccountIdentity(
            provider=self.provider,
            account_key=TOKEN_ACCOUNT_MAIL,
            email_address=email,
            provider_user_id=oid,
        )

    def is_connected(self) -> bool:
        if self._client is not None:
            return True
        tok = load_ms_token(TOKEN_ACCOUNT_MAIL, token_dir=self.token_dir)
        return bool(tok and (tok.get("access_token") or tok.get("refresh_token")))

    def sync(self, *, cursor: MailSyncCursor | None = None) -> MailSyncResult:
        client = self._client
        if client is None:
            if not self.is_connected():
                raise ProviderError(
                    self.provider.value,
                    "microsoft_mail_not_connected",
                    reconnectable=True,
                )
            raise ProviderError(
                self.provider.value,
                "microsoft_graph_client_not_configured",
                reconnectable=True,
            )
        delta = (cursor.cursor_token if cursor else "") or ""
        raw_messages, new_delta = client.list_messages(delta_link=delta)
        messages = [_normalize_graph_message(m) for m in raw_messages]
        return MailSyncResult(
            provider=self.provider,
            mode="delta" if delta else "full",
            fetched=len(messages),
            processed=len(messages),
            new_cursor_token=new_delta,
            messages=messages,
        )

    def disconnect(self, *, revoke_remote: bool = True) -> None:
        _ = revoke_remote
        delete_ms_token(TOKEN_ACCOUNT_MAIL, token_dir=self.token_dir)


def _normalize_graph_message(raw: dict[str, Any]) -> NormalizedEmail:
    mid = str(raw.get("id") or "")
    from_addr = ""
    fr = raw.get("from") or {}
    if isinstance(fr, dict):
        ea = fr.get("emailAddress") or {}
        if isinstance(ea, dict):
            from_addr = str(ea.get("address") or "")
    body = raw.get("body") or {}
    body_text = ""
    if isinstance(body, dict):
        body_text = str(body.get("content") or "")
    return NormalizedEmail(
        provider=MailProvider.MICROSOFT_GRAPH,
        external_message_id=mid,
        thread_id=str(raw.get("conversationId") or ""),
        subject=str(raw.get("subject") or ""),
        sender=from_addr,
        snippet=str(raw.get("bodyPreview") or ""),
        body_text=body_text,
        internal_date=str(raw.get("receivedDateTime") or ""),
        provider_message_id=mid,
    )


_: type[MailProviderAdapter] = MicrosoftGraphMailAdapter  # type: ignore[assignment,misc]
