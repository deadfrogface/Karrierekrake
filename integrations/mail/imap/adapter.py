"""Generic IMAP mail adapter (NEXT-03).

Secrets ONLY in OS credential store. No plaintext password config.
Sending is NOT implied — drafts may stay local.
"""

from __future__ import annotations

import imaplib
import ssl
from dataclasses import dataclass
from email import message_from_bytes
from email.header import decode_header, make_header
from email.utils import parseaddr
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
from integrations.secure_tokens import (
    KeyringUnavailable,
    delete_token,
    load_token,
    store_token,
)

TOKEN_ACCOUNT_IMAP = "generic_imap"


@dataclass
class ImapEndpoint:
    host: str
    port: int = 993
    username: str = ""
    use_ssl: bool = True
    # oauth2_access_token optional — when present, uses AUTHENTICATE XOAUTH2
    oauth2: bool = False


def store_imap_secret(payload: dict[str, Any], *, token_dir: Path) -> None:
    """Persist IMAP credentials in keyring only (password or oauth token)."""
    try:
        store_token(TOKEN_ACCOUNT_IMAP, payload, fallback_dir=token_dir)
    except KeyringUnavailable as exc:
        raise ProviderError("generic_imap", "keyring_unavailable", reconnectable=True) from exc


def load_imap_secret(*, token_dir: Path) -> dict[str, Any] | None:
    try:
        return load_token(TOKEN_ACCOUNT_IMAP, fallback_dir=token_dir)
    except KeyringUnavailable:
        return None


def delete_imap_secret(*, token_dir: Path) -> None:
    try:
        delete_token(TOKEN_ACCOUNT_IMAP, fallback_dir=token_dir)
    except Exception:
        pass


class GenericImapMailAdapter:
    provider = MailProvider.GENERIC_IMAP

    def __init__(
        self,
        *,
        token_dir: Path | None = None,
        settings: Any | None = None,
        mailbox: Any | None = None,
    ) -> None:
        self.token_dir = Path(token_dir) if token_dir else Path(".")
        self.settings = settings
        self._mailbox = mailbox  # injectable fake for tests

    def identity(self) -> MailAccountIdentity:
        secret = load_imap_secret(token_dir=self.token_dir) or {}
        return MailAccountIdentity(
            provider=self.provider,
            account_key=TOKEN_ACCOUNT_IMAP,
            email_address=str(secret.get("username") or ""),
        )

    def is_connected(self) -> bool:
        if self._mailbox is not None:
            return True
        secret = load_imap_secret(token_dir=self.token_dir)
        return bool(secret and secret.get("host") and secret.get("username"))

    def sync(self, *, cursor: MailSyncCursor | None = None) -> MailSyncResult:
        if self._mailbox is not None:
            messages = list(self._mailbox.list_normalized())
            return MailSyncResult(
                provider=self.provider,
                mode="imap",
                fetched=len(messages),
                processed=len(messages),
                new_cursor_token=(cursor.cursor_token if cursor else "") or "",
                messages=messages,
            )
        secret = load_imap_secret(token_dir=self.token_dir)
        if not secret:
            raise ProviderError(
                self.provider.value, "imap_not_configured", reconnectable=True
            )
        endpoint = ImapEndpoint(
            host=str(secret.get("host") or ""),
            port=int(secret.get("port") or 993),
            username=str(secret.get("username") or ""),
            use_ssl=bool(secret.get("use_ssl", True)),
            oauth2=bool(secret.get("oauth2", False)),
        )
        messages = _fetch_imap_messages(endpoint, secret)
        return MailSyncResult(
            provider=self.provider,
            mode="imap",
            fetched=len(messages),
            processed=len(messages),
            new_cursor_token=(cursor.cursor_token if cursor else "") or "",
            messages=messages,
        )

    def disconnect(self, *, revoke_remote: bool = True) -> None:
        _ = revoke_remote
        delete_imap_secret(token_dir=self.token_dir)


def _decode_header_value(raw: str | None) -> str:
    if not raw:
        return ""
    try:
        return str(make_header(decode_header(raw)))
    except Exception:
        return str(raw)


def _fetch_imap_messages(endpoint: ImapEndpoint, secret: dict[str, Any]) -> list[NormalizedEmail]:
    if not endpoint.host or not endpoint.username:
        raise ProviderError("generic_imap", "imap_endpoint_incomplete", reconnectable=True)
    try:
        if endpoint.use_ssl:
            conn = imaplib.IMAP4_SSL(endpoint.host, endpoint.port)
        else:
            context = ssl.create_default_context()
            conn = imaplib.IMAP4(endpoint.host, endpoint.port)
            conn.starttls(ssl_context=context)
        password = str(secret.get("password") or secret.get("app_password") or "")
        if endpoint.oauth2:
            token = str(secret.get("access_token") or "")
            # XOAUTH2 bare auth string — provider-specific; fail closed if empty.
            if not token:
                raise ProviderError("generic_imap", "imap_oauth_token_missing", reconnectable=True)
            auth_string = f"user={endpoint.username}\x01auth=Bearer {token}\x01\x01"
            conn.authenticate("XOAUTH2", lambda _: auth_string.encode("utf-8"))
        else:
            if not password:
                raise ProviderError("generic_imap", "imap_password_missing", reconnectable=True)
            conn.login(endpoint.username, password)
        conn.select("INBOX", readonly=True)
        typ, data = conn.search(None, "ALL")
        if typ != "OK":
            raise ProviderError("generic_imap", "imap_search_failed", reconnectable=True)
        ids = (data[0] or b"").split()
        # Cap for safety — full sync strategy is cursor-driven later.
        ids = ids[-50:]
        out: list[NormalizedEmail] = []
        for mid in ids:
            typ, msg_data = conn.fetch(mid, "(RFC822)")
            if typ != "OK" or not msg_data or not msg_data[0]:
                continue
            raw = msg_data[0][1]
            if not isinstance(raw, (bytes, bytearray)):
                continue
            msg = message_from_bytes(bytes(raw))
            subject = _decode_header_value(msg.get("Subject"))
            sender = parseaddr(msg.get("From") or "")[1]
            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/plain":
                        payload = part.get_payload(decode=True) or b""
                        body = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
                        break
            else:
                payload = msg.get_payload(decode=True) or b""
                if isinstance(payload, bytes):
                    body = payload.decode(msg.get_content_charset() or "utf-8", errors="replace")
            uid = mid.decode("ascii", errors="replace")
            out.append(
                NormalizedEmail(
                    provider=MailProvider.GENERIC_IMAP,
                    external_message_id=f"imap:{endpoint.host}:{uid}",
                    subject=subject,
                    sender=sender,
                    body_text=body,
                    provider_message_id=uid,
                )
            )
        try:
            conn.logout()
        except Exception:
            pass
        return out
    except ProviderError:
        raise
    except Exception as exc:
        raise ProviderError(
            "generic_imap", f"imap_runtime_error:{type(exc).__name__}", reconnectable=True
        ) from exc


_: type[MailProviderAdapter] = GenericImapMailAdapter  # type: ignore[assignment,misc]
