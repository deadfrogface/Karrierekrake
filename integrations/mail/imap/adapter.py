"""Generic IMAP mail adapter (NEXT-03).

Secrets ONLY in OS credential store. No plaintext password config.
Sending is NOT implied — drafts may stay local.
"""

from __future__ import annotations

import hashlib
import json
import imaplib
import ssl
from dataclasses import dataclass
from email import message_from_bytes
from email.header import decode_header, make_header
from email.utils import parseaddr, parsedate_to_datetime
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


def validate_imap_secret(secret: dict[str, Any]) -> None:
    """Authenticate without reading or sending mail before storing credentials."""
    host, user = str(secret.get("host") or "").strip(), str(secret.get("username") or "").strip()
    if not host or not user or not (secret.get("password") or secret.get("access_token")):
        raise ProviderError("generic_imap", "imap_endpoint_incomplete", reconnectable=True)
    conn = None
    try:
        conn = imaplib.IMAP4_SSL(host, int(secret.get("port") or 993), timeout=20)
        if secret.get("oauth2"):
            auth = f"user={user}\x01auth=Bearer {secret['access_token']}\x01\x01"
            conn.authenticate("XOAUTH2", lambda _: auth.encode())
        else:
            conn.login(user, str(secret["password"]))
        status, _ = conn.noop()
        if status != "OK":
            raise ProviderError("generic_imap", "imap_probe_failed", reconnectable=True)
    except ProviderError:
        raise
    except Exception:
        raise ProviderError("generic_imap", "imap_auth_failed", reconnectable=True) from None
    finally:
        if conn is not None:
            try:
                conn.logout()
            except Exception:
                try:
                    conn.shutdown()
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
        from integrations.providers.connection_probe import probe_imap

        return probe_imap(token_dir=self.token_dir).connected

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
        from integrations.mail.imap.outlook_auth import refresh_outlook
        secret = refresh_outlook(secret, token_dir=self.token_dir)
        endpoint = ImapEndpoint(
            host=str(secret.get("host") or ""),
            port=int(secret.get("port") or 993),
            username=str(secret.get("username") or ""),
            use_ssl=bool(secret.get("use_ssl", True)),
            oauth2=bool(secret.get("oauth2", False)),
        )
        progress = {}
        messages = _fetch_imap_messages(endpoint, secret, cursor_token=cursor.cursor_token if cursor else "", progress=progress)
        return MailSyncResult(
            provider=self.provider,
            mode="imap",
            fetched=len(messages),
            processed=len(messages),
            new_cursor_token=progress["cursor"],
            partial=progress["partial"],
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


def _fetch_imap_messages(endpoint: ImapEndpoint, secret: dict[str, Any], *, cursor_token="", progress=None) -> list[NormalizedEmail]:
    if not endpoint.host or not endpoint.username:
        raise ProviderError("generic_imap", "imap_endpoint_incomplete", reconnectable=True)
    conn = None
    try:
        if endpoint.use_ssl:
            conn = imaplib.IMAP4_SSL(endpoint.host, endpoint.port, timeout=20)
        else:
            context = ssl.create_default_context()
            conn = imaplib.IMAP4(endpoint.host, endpoint.port, timeout=20)
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
        typ, _ = conn.select("INBOX", readonly=True)
        if typ != "OK":
            raise ProviderError("generic_imap", "imap_select_failed", reconnectable=True)
        _, validity_data = conn.response("UIDVALIDITY")
        validity = (validity_data or [b""])[0]
        if not validity or not bytes(validity).isdigit():
            raise ProviderError("generic_imap", "imap_uidvalidity_missing", reconnectable=True)
        namespace = hashlib.sha256(
            f"{endpoint.host.lower()}:{endpoint.port}:{endpoint.username}:INBOX".encode()
        ).hexdigest()[:24]
        previous = {}
        try:
            previous = json.loads(cursor_token) if cursor_token else {}
        except (ValueError, TypeError):
            pass
        if not isinstance(previous, dict):
            previous = {}
        try:
            last = max(0, int(previous.get("uid", 0))) if previous.get("namespace") == namespace and previous.get("validity") == validity.decode() else 0
        except (ValueError, TypeError):
            last = 0
        typ, data = conn.uid("search", None, "ALL")
        if typ != "OK":
            raise ProviderError("generic_imap", "imap_search_failed", reconnectable=True)
        ids = sorted((mid for mid in (data[0] or b"").split() if int(mid) > last), key=int)
        partial = len(ids) > 50
        ids = ids[:50]
        out: list[NormalizedEmail] = []
        for mid in ids:
            typ, msg_data = conn.uid("fetch", mid, "(BODY.PEEK[])")
            if typ != "OK" or not msg_data or not msg_data[0]:
                raise ProviderError("generic_imap", "imap_fetch_failed")
            raw = next((item[1] for item in msg_data if isinstance(item, tuple) and isinstance(item[1], bytes)), None)
            if raw is None:
                raise ProviderError("generic_imap", "imap_fetch_failed")
            msg = message_from_bytes(bytes(raw))
            subject = _decode_header_value(msg.get("Subject"))
            sender = parseaddr(msg.get("From") or "")[1]
            body = message_body(msg)
            uid = mid.decode("ascii", errors="replace")
            stable_id = f"imap:{namespace}:{validity.decode()}:{uid}"
            try:
                received = parsedate_to_datetime(msg.get("Date") or "").isoformat()
            except (ValueError, TypeError, OverflowError):
                received = ""
            references = (msg.get("References") or msg.get("In-Reply-To") or msg.get("Message-ID") or "").split()
            thread_id = f"imap:{namespace}:{references[0]}" if references else ""
            out.append(
                NormalizedEmail(
                    provider=MailProvider.GENERIC_IMAP,
                    external_message_id=stable_id,
                    internal_date=received,
                    thread_id=thread_id,
                    subject=subject,
                    sender=sender,
                    body_text=body,
                    provider_message_id=stable_id,
                )
            )
        if progress is not None:
            progress.update(cursor=json.dumps({"namespace": namespace, "validity": validity.decode(), "uid": int(ids[-1]) if ids else last}), partial=partial)
        return out
    except ProviderError:
        raise
    except Exception as exc:
        raise ProviderError(
            "generic_imap", f"imap_runtime_error:{type(exc).__name__}", reconnectable=True
        ) from None
    finally:
        if conn is not None:
            try:
                conn.logout()
            except Exception:
                try:
                    conn.shutdown()
                except Exception:
                    pass


_: type[MailProviderAdapter] = GenericImapMailAdapter  # type: ignore[assignment,misc]


def message_body(msg) -> str:
    """Prefer plain text; ignore attachments and executable HTML content."""
    parts = [part for part in msg.walk() if part.get_content_disposition() != "attachment"]
    for kind in ("text/plain", "text/html"):
        for part in parts:
            if part.get_content_type() != kind:
                continue
            payload = part.get_payload(decode=True) or b""
            try:
                text = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
            except LookupError:
                text = payload.decode("utf-8", errors="replace")
            if kind == "text/html":
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(text, "html.parser")
                for item in soup(["script", "style"]):
                    item.decompose()
                text = soup.get_text(" ", strip=True)
            return text
    return ""
