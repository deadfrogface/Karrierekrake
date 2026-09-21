"""Normalized mail contracts — lifecycle must not depend on Gmail types (NEXT-03)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from integrations.providers.enums import MailProvider


@dataclass
class MailAccountIdentity:
    provider: MailProvider
    account_key: str
    email_address: str = ""
    display_name: str = ""
    # Provider-specific opaque id (e.g. Google sub, MS oid) — provenance only.
    provider_user_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider.value,
            "account_key": self.account_key,
            "email_address": self.email_address,
            "display_name": self.display_name,
            "provider_user_id": self.provider_user_id,
        }


@dataclass
class MailAttachmentMetadata:
    filename: str
    mime_type: str = ""
    size_bytes: int = 0
    provider_attachment_id: str = ""


@dataclass
class NormalizedEmail:
    """Provider-agnostic inbound mail for association/lifecycle."""

    provider: MailProvider
    external_message_id: str
    thread_id: str = ""
    subject: str = ""
    sender: str = ""
    snippet: str = ""
    body_text: str = ""
    internal_date: str = ""
    label_ids: list[str] = field(default_factory=list)
    attachments: list[MailAttachmentMetadata] = field(default_factory=list)
    # Provenance: original vendor id (gmail_id, graph id, IMAP UID…)
    provider_message_id: str = ""

    def to_pipeline_payload(self) -> dict[str, Any]:
        """Payload compatible with case_pipeline (gmail_id kept as alias)."""
        mid = self.provider_message_id or self.external_message_id
        return {
            "provider": self.provider.value,
            "external_message_id": self.external_message_id,
            "gmail_id": mid,  # legacy DB column alias until generalized
            "thread_id": self.thread_id,
            "subject": self.subject,
            "sender": self.sender,
            "snippet": self.snippet,
            "body_text": self.body_text,
            "internal_date": self.internal_date,
            "label_ids": list(self.label_ids),
        }


@dataclass
class MailThread:
    provider: MailProvider
    thread_id: str
    message_ids: list[str] = field(default_factory=list)
    subject: str = ""


@dataclass
class MailSyncCursor:
    provider: MailProvider
    account_key: str = "default"
    schema_version: int = 1
    cursor_token: str = ""  # historyId / deltaLink / UIDVALIDITY+UID
    resume_page_token: str = ""
    sync_mode: str = ""
    last_error: str = ""
    pending_message_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider.value,
            "account_key": self.account_key,
            "schema_version": self.schema_version,
            "cursor_token": self.cursor_token,
            "history_id": self.cursor_token,  # Gmail alias
            "resume_page_token": self.resume_page_token,
            "sync_mode": self.sync_mode,
            "last_error": self.last_error,
            "pending_message_ids": list(self.pending_message_ids),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None, *, provider: MailProvider) -> MailSyncCursor:
        if not data:
            return cls(provider=provider)
        token = str(data.get("cursor_token") or data.get("history_id") or "")
        return cls(
            provider=provider,
            account_key=str(data.get("account_key") or "default"),
            schema_version=int(data.get("schema_version") or 1),
            cursor_token=token,
            resume_page_token=str(data.get("resume_page_token") or ""),
            sync_mode=str(data.get("sync_mode") or ""),
            last_error=str(data.get("last_error") or ""),
            pending_message_ids=[
                str(x) for x in (data.get("pending_message_ids") or []) if x
            ],
        )


@dataclass
class MailSyncResult:
    provider: MailProvider
    mode: str
    fetched: int = 0
    processed: int = 0
    skipped_duplicates: int = 0
    new_cursor_token: str = ""
    resumed: bool = False
    partial: bool = False
    errors: list[str] = field(default_factory=list)
    needs_reauth: bool = False
    messages: list[NormalizedEmail] = field(default_factory=list)


class MailProviderAdapter(Protocol):
    """Explicit adapter for one MailProvider. No cross-provider failover."""

    provider: MailProvider

    def identity(self) -> MailAccountIdentity: ...

    def is_connected(self) -> bool: ...

    def sync(self, *, cursor: MailSyncCursor | None = None) -> MailSyncResult: ...

    def disconnect(self, *, revoke_remote: bool = True) -> None: ...
