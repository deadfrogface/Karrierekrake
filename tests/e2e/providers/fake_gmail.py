"""Reusable Fake Gmail provider for product E2E (no real Google)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from integrations.gmail_auth import SCOPES
from integrations.gmail_sync import SyncCursor


class FakeCreds:
    def __init__(
        self,
        *,
        valid: bool = True,
        expired: bool = False,
        refresh_token: str | None = "rt",
        token: str = "at",
        scopes: list[str] | None = None,
        client_id: str = "cid",
        client_secret: str = "csec",
        token_uri: str = "https://oauth2.googleapis.com/token",
        expiry: Any = None,
        refresh_exc: Exception | None = None,
    ):
        self.valid = valid
        self.expired = expired
        self.refresh_token = refresh_token
        self.token = token
        self.scopes = scopes or list(SCOPES)
        self.client_id = client_id
        self.client_secret = client_secret
        self.token_uri = token_uri
        self.expiry = expiry
        self._refresh_exc = refresh_exc
        self.refresh_calls = 0

    def refresh(self, _request: Any) -> None:
        self.refresh_calls += 1
        if self._refresh_exc:
            raise self._refresh_exc
        self.valid = True
        self.expired = False
        self.token = "refreshed-at"


class FakeMessages:
    def __init__(self, parent: "FakeGmailService"):
        self._p = parent

    def list(self, **kwargs: Any):
        req = MagicMock()
        token = kwargs.get("pageToken")
        page = self._p.list_pages.get(token or "", {"messages": [], "nextPageToken": None})
        if callable(page):
            req.execute.side_effect = page
        else:
            req.execute.return_value = page
        return req

    def get(self, **kwargs: Any):
        req = MagicMock()
        mid = kwargs["id"]
        if mid in self._p.get_errors:
            req.execute.side_effect = self._p.get_errors[mid]
        else:
            req.execute.return_value = self._p.messages.get(
                mid,
                {
                    "id": mid,
                    "threadId": f"t-{mid}",
                    "snippet": f"snip-{mid}",
                    "internalDate": "1",
                    "labelIds": ["INBOX"],
                    "payload": {
                        "headers": [
                            {"name": "Subject", "value": f"Subj {mid}"},
                            {"name": "From", "value": "hr@example.com"},
                        ],
                        "body": {"data": ""},
                    },
                },
            )
        return req


class FakeHistory:
    def __init__(self, parent: "FakeGmailService"):
        self._p = parent

    def list(self, **kwargs: Any):
        req = MagicMock()
        if self._p.history_error is not None:
            req.execute.side_effect = self._p.history_error
            return req
        token = kwargs.get("pageToken")
        start = str(kwargs.get("startHistoryId") or "")
        key = (start, token or "")
        page = self._p.history_pages.get(key)
        if page is None:
            page = {"history": [], "historyId": start or "1", "nextPageToken": None}
        if callable(page):
            req.execute.side_effect = page
        else:
            req.execute.return_value = page
        return req


class FakeUsers:
    def __init__(self, parent: "FakeGmailService"):
        self._p = parent
        self._messages = FakeMessages(parent)
        self._history = FakeHistory(parent)

    def messages(self):
        return self._messages

    def history(self):
        return self._history

    def getProfile(self, **_kwargs: Any):
        req = MagicMock()
        if self._p.profile_error is not None:
            req.execute.side_effect = self._p.profile_error
        else:
            req.execute.return_value = {
                "emailAddress": self._p.email,
                "historyId": self._p.profile_history_id,
            }
        return req


class FakeGmailService:
    """In-memory Gmail API stand-in for sync / chaos tests."""

    def __init__(self, email: str = "user@example.com", history_id: str = "100"):
        self.email = email
        self.profile_history_id = history_id
        self.list_pages: dict[str | None, Any] = {"": {"messages": [], "nextPageToken": None}}
        self.history_pages: dict[tuple[str, str], Any] = {}
        self.messages: dict[str, dict] = {}
        self.get_errors: dict[str, Exception] = {}
        self.history_error: Exception | None = None
        self.profile_error: Exception | None = None
        self._users = FakeUsers(self)
        self._seq = 0

    def users(self):
        return self._users

    def seed_message(
        self,
        *,
        mid: str | None = None,
        subject: str,
        sender: str,
        body: str = "",
        thread_id: str | None = None,
        internal_date: str = "1700000000000",
    ) -> str:
        self._seq += 1
        mid = mid or f"msg-{self._seq:04d}"
        thread_id = thread_id or f"t-{mid}"
        self.messages[mid] = {
            "id": mid,
            "threadId": thread_id,
            "snippet": body[:80],
            "internalDate": internal_date,
            "labelIds": ["INBOX"],
            "payload": {
                "headers": [
                    {"name": "Subject", "value": subject},
                    {"name": "From", "value": sender},
                ],
                "body": {"data": ""},
                "parts": [
                    {
                        "mimeType": "text/plain",
                        "body": {"data": _b64(body)},
                    }
                ],
            },
        }
        page = self.list_pages.setdefault("", {"messages": [], "nextPageToken": None})
        ids = {m["id"] for m in page["messages"]}
        if mid not in ids:
            page["messages"].append({"id": mid})
        return mid


class MemoryCursorStore:
    def __init__(self, cursor: SyncCursor | None = None):
        self.cursor = cursor or SyncCursor()
        self.saves: list[SyncCursor] = []

    def load(self) -> SyncCursor:
        return SyncCursor(
            schema_version=self.cursor.schema_version,
            history_id=self.cursor.history_id,
            account_key=self.cursor.account_key,
            resume_page_token=self.cursor.resume_page_token,
            sync_mode=self.cursor.sync_mode,
            last_error=self.cursor.last_error,
            pending_message_ids=list(self.cursor.pending_message_ids),
        )

    def save(self, cursor: SyncCursor) -> None:
        self.cursor = SyncCursor(
            schema_version=cursor.schema_version,
            history_id=cursor.history_id,
            account_key=cursor.account_key,
            resume_page_token=cursor.resume_page_token,
            sync_mode=cursor.sync_mode,
            last_error=cursor.last_error,
            pending_message_ids=list(cursor.pending_message_ids),
        )
        self.saves.append(self.load())


def _b64(text: str) -> str:
    import base64

    return base64.urlsafe_b64encode(text.encode("utf-8")).decode("ascii").rstrip("=")
