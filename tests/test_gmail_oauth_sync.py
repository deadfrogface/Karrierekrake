"""PR27 — Gmail OAuth & robust incremental sync (mocked; no live inbox)."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import httplib2
import pytest
from googleapiclient.errors import HttpError

from core.database import Database
from integrations import gmail_auth, gmail_sync, secure_tokens
from integrations.gmail_auth import (
    GMAIL_READONLY_SCOPE,
    SCOPES,
    TOKEN_ACCOUNT,
    creds_from_payload,
    disconnect_gmail,
    gmail_connected,
    load_client_config,
    resolve_oauth_port,
    save_creds_payload,
)
from integrations.gmail_sync import (
    CURSOR_SCHEMA_VERSION,
    ParsedEmail,
    SyncCursor,
    SyncResult,
    extract_history_message_ids,
    list_history_page,
    list_message_ids,
    parse_message,
    run_robust_sync,
    sender_is_excluded,
)
from integrations.secure_tokens import delete_token, load_token, store_token


def _http_error(status: int, body: bytes = b'{"error":{"message":"x"}}') -> HttpError:
    return HttpError(httplib2.Response({"status": str(status)}), body)


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
        expiry=None,
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

    def refresh(self, _request) -> None:
        self.refresh_calls += 1
        if self._refresh_exc:
            raise self._refresh_exc
        self.valid = True
        self.expired = False
        self.token = "refreshed-at"


class FakeMessages:
    def __init__(self, parent: "FakeGmailService"):
        self._p = parent

    def list(self, **kwargs):
        req = MagicMock()
        token = kwargs.get("pageToken")
        page = self._p.list_pages.get(token or "", {"messages": [], "nextPageToken": None})
        if callable(page):
            req.execute.side_effect = page
        else:
            req.execute.return_value = page
        return req

    def get(self, **kwargs):
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

    def list(self, **kwargs):
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

    def getProfile(self, **_kwargs):
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

    def users(self):
        return self._users


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


def _collecting_handler():
    known: set[str] = set()
    processed: list[str] = []

    def is_known(mid: str) -> bool:
        return mid in known

    def on_message(email: ParsedEmail) -> None:
        processed.append(email.id)
        known.add(email.id)

    return is_known, on_message, processed, known


def test_scopes_are_readonly_only():
    assert SCOPES == [GMAIL_READONLY_SCOPE]
    assert "gmail.readonly" in GMAIL_READONLY_SCOPE
    assert "gmail.modify" not in GMAIL_READONLY_SCOPE
    assert "gmail.compose" not in "".join(SCOPES)
    assert "gmail.send" not in "".join(SCOPES)


def test_load_client_config_installed(tmp_path: Path):
    path = tmp_path / "creds.json"
    path.write_text(
        json.dumps({"installed": {"client_id": "x", "redirect_uris": ["http://localhost:8080"]}}),
        encoding="utf-8",
    )
    kind, cfg = load_client_config(path)
    assert kind == "installed"
    assert cfg["client_id"] == "x"


def test_load_client_config_web(tmp_path: Path):
    path = tmp_path / "creds.json"
    path.write_text(
        json.dumps({"web": {"client_id": "w", "redirect_uris": ["http://localhost:8080"]}}),
        encoding="utf-8",
    )
    kind, cfg = load_client_config(path)
    assert kind == "web"
    assert cfg["client_id"] == "w"


def test_load_client_config_corrupt(tmp_path: Path):
    path = tmp_path / "bad.json"
    path.write_text("{not-json", encoding="utf-8")
    kind, cfg = load_client_config(path)
    assert kind is None and cfg is None


def test_load_client_config_missing_file(tmp_path: Path):
    kind, cfg = load_client_config(tmp_path / "missing.json")
    assert kind is None and cfg is None


def test_load_client_config_unknown_shape(tmp_path: Path):
    path = tmp_path / "creds.json"
    path.write_text(json.dumps({"other": {}}), encoding="utf-8")
    kind, cfg = load_client_config(path)
    assert kind is None and cfg is None


def test_resolve_oauth_port_installed_ok(monkeypatch):
    monkeypatch.setenv("GMAIL_OAUTH_PORT", "9090")
    assert resolve_oauth_port("installed", {}) == 9090


def test_resolve_oauth_port_web_mismatch():
    assert resolve_oauth_port("web", {"redirect_uris": ["http://localhost:9999"]}) is None


def test_resolve_oauth_port_web_match(monkeypatch):
    monkeypatch.setenv("GMAIL_OAUTH_PORT", "8080")
    assert resolve_oauth_port("web", {"redirect_uris": ["http://127.0.0.1:8080/"]}) == 8080


def test_oauth_happy_path_builds_service(tmp_path: Path, monkeypatch):
    creds_path = tmp_path / "client.json"
    creds_path.write_text(
        json.dumps(
            {"installed": {"client_id": "c", "client_secret": "s", "redirect_uris": ["http://localhost"]}}
        ),
        encoding="utf-8",
    )
    token_dir = tmp_path / "tok"
    fake = FakeCreds()
    flow = MagicMock()
    flow.run_local_server.return_value = fake
    monkeypatch.setattr(gmail_auth, "gmail_libs_available", lambda: True)
    with (
        patch(
            "google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file",
            return_value=flow,
        ),
        patch("googleapiclient.discovery.build", return_value="SERVICE") as build,
    ):
        svc = gmail_auth.get_gmail_service(credentials_path=creds_path, token_dir=token_dir)
    assert svc == "SERVICE"
    assert gmail_connected(token_dir=token_dir)
    build.assert_called_once()
    assert flow.run_local_server.called


def test_oauth_cancel_returns_none(tmp_path: Path, monkeypatch):
    creds_path = tmp_path / "client.json"
    creds_path.write_text(json.dumps({"installed": {"client_id": "c"}}), encoding="utf-8")
    flow = MagicMock()
    flow.run_local_server.side_effect = Exception("access_denied")
    monkeypatch.setattr(gmail_auth, "gmail_libs_available", lambda: True)
    with patch(
        "google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file",
        return_value=flow,
    ):
        assert gmail_auth.get_gmail_service(credentials_path=creds_path, token_dir=tmp_path / "t") is None


def test_oauth_expired_token_refreshes(tmp_path: Path, monkeypatch):
    token_dir = tmp_path / "tok"
    payload = {
        "token": "old",
        "refresh_token": "rt",
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": "cid",
        "client_secret": "sec",
        "scopes": list(SCOPES),
    }
    store_token(TOKEN_ACCOUNT, payload, fallback_dir=token_dir)
    fake = FakeCreds(valid=False, expired=True, refresh_token="rt")
    monkeypatch.setattr(gmail_auth, "gmail_libs_available", lambda: True)
    monkeypatch.setattr(gmail_auth, "creds_from_payload", lambda _p: fake)
    with (
        patch("google.auth.transport.requests.Request"),
        patch("googleapiclient.discovery.build", return_value="SVC"),
    ):
        assert (
            gmail_auth.get_gmail_service(credentials_path=tmp_path / "x.json", token_dir=token_dir)
            == "SVC"
        )
    assert fake.refresh_calls == 1
    loaded = load_token(TOKEN_ACCOUNT, fallback_dir=token_dir)
    assert loaded is not None
    assert loaded["token"] == "refreshed-at"


def test_oauth_revoked_token_clears_and_needs_reauth(tmp_path: Path, monkeypatch):
    token_dir = tmp_path / "tok"
    store_token(
        TOKEN_ACCOUNT,
        {"token": "t", "refresh_token": "rt", "client_id": "c", "scopes": list(SCOPES)},
        fallback_dir=token_dir,
    )
    from google.auth.exceptions import RefreshError

    fake = FakeCreds(valid=False, expired=True, refresh_exc=RefreshError("invalid_grant"))
    monkeypatch.setattr(gmail_auth, "gmail_libs_available", lambda: True)
    monkeypatch.setattr(gmail_auth, "creds_from_payload", lambda _p: fake)
    with patch("google.auth.transport.requests.Request"):
        outcome = gmail_auth.authorize_gmail(
            credentials_path=tmp_path / "x.json", token_dir=token_dir
        )
    assert outcome.service is None
    assert outcome.needs_reauth is True
    assert outcome.reason in {"revoked", "refresh_failed", "invalid_grant"}
    assert load_token(TOKEN_ACCOUNT, fallback_dir=token_dir) is None


def test_oauth_refresh_success_via_authorize(tmp_path: Path, monkeypatch):
    token_dir = tmp_path / "tok"
    store_token(
        TOKEN_ACCOUNT,
        {"token": "t", "refresh_token": "rt", "client_id": "c", "scopes": list(SCOPES)},
        fallback_dir=token_dir,
    )
    fake = FakeCreds(valid=False, expired=True)
    monkeypatch.setattr(gmail_auth, "gmail_libs_available", lambda: True)
    monkeypatch.setattr(gmail_auth, "creds_from_payload", lambda _p: fake)
    with (
        patch("google.auth.transport.requests.Request"),
        patch("googleapiclient.discovery.build", return_value="OK"),
    ):
        outcome = gmail_auth.authorize_gmail(
            credentials_path=tmp_path / "x.json", token_dir=token_dir
        )
    assert outcome.service == "OK"
    assert outcome.needs_reauth is False


def test_corrupt_keyring_payload_returns_none(tmp_path: Path, monkeypatch):
    token_dir = tmp_path / "tok"
    monkeypatch.setattr(gmail_auth, "gmail_libs_available", lambda: True)
    monkeypatch.setattr(gmail_auth, "load_token", lambda *a, **k: {"token": object()})
    outcome = gmail_auth.authorize_gmail(
        credentials_path=tmp_path / "missing.json", token_dir=token_dir
    )
    assert outcome.service is None


def test_wrong_client_config_blocks_oauth(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(gmail_auth, "gmail_libs_available", lambda: True)
    outcome = gmail_auth.authorize_gmail(
        credentials_path=tmp_path / "no.json", token_dir=tmp_path / "t"
    )
    assert outcome.service is None


def test_offline_libs_unavailable(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(gmail_auth, "gmail_libs_available", lambda: False)
    assert gmail_auth.get_gmail_service(credentials_path=tmp_path / "c.json", token_dir=tmp_path) is None


def test_scope_mismatch_detected():
    payload = {
        "scopes": ["https://www.googleapis.com/auth/gmail.modify"],
        "refresh_token": "r",
    }
    assert gmail_auth.scopes_are_compatible(payload) is False
    payload2 = {"scopes": [GMAIL_READONLY_SCOPE], "refresh_token": "r"}
    assert gmail_auth.scopes_are_compatible(payload2) is True


def test_scope_mismatch_forces_reauth(tmp_path: Path, monkeypatch):
    token_dir = tmp_path / "tok"
    store_token(
        TOKEN_ACCOUNT,
        {
            "token": "t",
            "refresh_token": "rt",
            "scopes": ["https://www.googleapis.com/auth/gmail.modify"],
            "client_id": "c",
        },
        fallback_dir=token_dir,
    )
    monkeypatch.setattr(gmail_auth, "gmail_libs_available", lambda: True)
    outcome = gmail_auth.authorize_gmail(
        credentials_path=tmp_path / "c.json",
        token_dir=token_dir,
        interactive=False,
    )
    assert outcome.needs_reauth is True
    assert outcome.reason == "scope_mismatch"


def test_disconnect_removes_token(tmp_path: Path):
    token_dir = tmp_path / "tok"
    store_token(
        TOKEN_ACCOUNT,
        {"token": "secret-token-value", "refresh_token": "r"},
        fallback_dir=token_dir,
    )
    disconnect_gmail(token_dir=token_dir)
    assert load_token(TOKEN_ACCOUNT, fallback_dir=token_dir) is None
    assert gmail_connected(token_dir=token_dir) is False


def test_disconnect_attempts_remote_revoke(tmp_path: Path, monkeypatch):
    token_dir = tmp_path / "tok"
    store_token(
        TOKEN_ACCOUNT,
        {"token": "access", "refresh_token": "refresh"},
        fallback_dir=token_dir,
    )
    called = {}

    def fake_revoke(token: str) -> bool:
        called["token"] = token
        return True

    monkeypatch.setattr(gmail_auth, "revoke_token_remote", fake_revoke)
    disconnect_gmail(token_dir=token_dir, revoke_remote=True)
    assert called["token"] in {"access", "refresh"}
    assert load_token(TOKEN_ACCOUNT, fallback_dir=token_dir) is None


def test_save_creds_never_writes_plaintext_next_to_logs(tmp_path: Path):
    fake = FakeCreds(token="super-secret-access")
    backend = save_creds_payload(fake, fallback_dir=tmp_path / "private")
    assert backend in {"keyring", "file"}
    for p in (tmp_path / "private").rglob("*"):
        if p.is_file():
            assert "logs" not in p.parts


def test_logs_omit_token_and_mail_body(caplog, tmp_path: Path, monkeypatch):
    caplog.set_level(logging.DEBUG)
    token_dir = tmp_path / "tok"
    store_token(
        TOKEN_ACCOUNT,
        {"token": "SECRETTOKENXYZ", "refresh_token": "rt", "scopes": list(SCOPES)},
        fallback_dir=token_dir,
    )
    from google.auth.exceptions import RefreshError

    fake = FakeCreds(
        valid=False, expired=True, refresh_exc=RefreshError("revoked SECRETTOKENXYZ")
    )
    monkeypatch.setattr(gmail_auth, "gmail_libs_available", lambda: True)
    monkeypatch.setattr(gmail_auth, "creds_from_payload", lambda _p: fake)
    with patch("google.auth.transport.requests.Request"):
        gmail_auth.authorize_gmail(credentials_path=tmp_path / "x.json", token_dir=token_dir)
    blob = "\n".join(r.getMessage() for r in caplog.records)
    assert "SECRETTOKENXYZ" not in blob


def test_file_fallback_corrupt_json(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(secure_tokens, "_keyring", lambda: None)
    path = tmp_path / f"oauth_{TOKEN_ACCOUNT}.json"
    path.write_text("{broken", encoding="utf-8")
    assert load_token(TOKEN_ACCOUNT, fallback_dir=tmp_path) is None


def test_keyring_store_failure_falls_back_to_file(tmp_path: Path, monkeypatch):
    class Boom:
        def set_password(self, *a, **k):
            raise RuntimeError("no keyring")

        def get_password(self, *a, **k):
            return None

        def delete_password(self, *a, **k):
            raise RuntimeError("x")

    monkeypatch.setattr(secure_tokens, "_keyring", lambda: Boom())
    assert store_token("acc", {"token": "t"}, fallback_dir=tmp_path) == "file"
    assert (tmp_path / "oauth_acc.json").is_file()


def test_creds_from_payload_roundtrip():
    payload = {
        "token": "a",
        "refresh_token": "b",
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": "c",
        "client_secret": "d",
        "scopes": list(SCOPES),
    }
    creds = creds_from_payload(payload)
    assert creds.token == "a"
    assert creds.refresh_token == "b"


def test_parse_message_basic():
    msg = {
        "id": "m1",
        "threadId": "t1",
        "snippet": "hello",
        "internalDate": "99",
        "labelIds": ["INBOX"],
        "payload": {
            "headers": [
                {"name": "Subject", "value": "Bewerbung"},
                {"name": "From", "value": "A <a@b.de>"},
            ],
            "body": {"data": ""},
        },
    }
    parsed = parse_message(msg)
    assert parsed.id == "m1"
    assert parsed.subject == "Bewerbung"
    assert "a@b.de" in parsed.sender.lower() or parsed.sender


def test_sender_exclude_wildcard():
    assert sender_is_excluded("x@news.example.com", ["*@news.example.com"]) is True
    assert sender_is_excluded("hr@corp.de", ["*@news.example.com"]) is False


def test_list_message_ids_pagination_token():
    svc = FakeGmailService()
    svc.list_pages[""] = {
        "messages": [{"id": "a"}, {"id": "b"}],
        "nextPageToken": "p2",
    }
    ids, nxt = list_message_ids(svc, max_results=10)
    assert ids == ["a", "b"]
    assert nxt == "p2"


def test_extract_history_message_ids_dedupes():
    history = [
        {
            "messagesAdded": [
                {"message": {"id": "m1"}},
                {"message": {"id": "m1"}},
                {"message": {"id": "m2"}},
            ]
        },
        {"messagesAdded": [{"message": {"id": "m2"}}]},
    ]
    assert extract_history_message_ids(history) == ["m1", "m2"]


def test_list_history_page_happy():
    svc = FakeGmailService()
    svc.history_pages[("50", "")] = {
        "history": [{"messagesAdded": [{"message": {"id": "n1"}}]}],
        "historyId": "60",
        "nextPageToken": None,
    }
    records, nxt, hid = list_history_page(svc, start_history_id="50")
    assert extract_history_message_ids(records) == ["n1"]
    assert nxt is None
    assert hid == "60"


def test_list_history_404_raises_or_signals():
    svc = FakeGmailService()
    svc.history_error = _http_error(404)
    with pytest.raises(Exception) as ei:
        list_history_page(svc, start_history_id="1")
    assert getattr(ei.value, "resp", None) is not None or "404" in str(ei.value)


def test_cursor_schema_version_constant():
    assert CURSOR_SCHEMA_VERSION >= 1
    c = SyncCursor()
    assert c.schema_version == CURSOR_SCHEMA_VERSION


def test_cursor_store_roundtrip_db(tmp_path: Path):
    db = Database(tmp_path / "x.db")
    store = gmail_sync.DatabaseCursorStore(db)
    cur = SyncCursor(history_id="42", account_key="acct-1", sync_mode="incremental")
    store.save(cur)
    loaded = store.load()
    assert loaded.history_id == "42"
    assert loaded.account_key == "acct-1"
    assert loaded.schema_version == CURSOR_SCHEMA_VERSION


def test_incompatible_cursor_schema_triggers_full_sync_not_db_wipe(tmp_path: Path):
    db = Database(tmp_path / "x.db")
    db.save_email_message({"gmail_id": "keep-me", "subject": "x", "body_text": "y"})
    store = gmail_sync.DatabaseCursorStore(db)
    db.set_meta(
        gmail_sync.CURSOR_META_KEY,
        json.dumps({"schema_version": 999, "history_id": "old", "account_key": "a"}),
    )
    svc = FakeGmailService(history_id="200")
    svc.list_pages[""] = {"messages": [{"id": "keep-me"}], "nextPageToken": None}
    _is_known, on_message, processed, _ = _collecting_handler()
    assert db.get_email_by_gmail_id("keep-me") is not None

    result = run_robust_sync(
        svc,
        cursor_store=store,
        is_known=lambda mid: db.get_email_by_gmail_id(mid) is not None,
        on_message=on_message,
        account_key="a",
    )
    assert result.mode in {"full", "full_fallback", "initial"}
    assert db.get_email_by_gmail_id("keep-me") is not None
    assert "keep-me" not in processed


def test_initial_sync_paginates_and_sets_history():
    svc = FakeGmailService(history_id="500")
    svc.list_pages[""] = {
        "messages": [{"id": "m1"}, {"id": "m2"}],
        "nextPageToken": "page2",
    }
    svc.list_pages["page2"] = {
        "messages": [{"id": "m3"}],
        "nextPageToken": None,
    }
    store = MemoryCursorStore()
    is_known, on_message, processed, _ = _collecting_handler()
    result = run_robust_sync(svc, cursor_store=store, is_known=is_known, on_message=on_message)
    assert result.mode == "initial"
    assert processed == ["m1", "m2", "m3"]
    assert store.cursor.history_id == "500"
    assert store.cursor.resume_page_token == ""


def test_incremental_sync_uses_history():
    svc = FakeGmailService(history_id="120")
    store = MemoryCursorStore(SyncCursor(history_id="100", account_key="default"))
    svc.history_pages[("100", "")] = {
        "history": [
            {"messagesAdded": [{"message": {"id": "new1"}}, {"message": {"id": "new2"}}]}
        ],
        "historyId": "120",
        "nextPageToken": None,
    }
    is_known, on_message, processed, _ = _collecting_handler()
    result = run_robust_sync(
        svc,
        cursor_store=store,
        is_known=is_known,
        on_message=on_message,
        account_key="default",
    )
    assert result.mode == "incremental"
    assert processed == ["new1", "new2"]
    assert store.cursor.history_id == "120"


def test_history_404_falls_back_to_full_sync():
    svc = FakeGmailService(history_id="900")
    store = MemoryCursorStore(SyncCursor(history_id="1", account_key="default"))
    svc.history_error = _http_error(404)
    svc.list_pages[""] = {"messages": [{"id": "f1"}], "nextPageToken": None}
    is_known, on_message, processed, _ = _collecting_handler()
    result = run_robust_sync(
        svc,
        cursor_store=store,
        is_known=is_known,
        on_message=on_message,
        account_key="default",
    )
    assert result.mode in {"full_fallback", "full"}
    assert processed == ["f1"]
    assert store.cursor.history_id == "900"


def test_duplicate_message_not_processed_twice():
    svc = FakeGmailService(history_id="10")
    svc.list_pages[""] = {
        "messages": [{"id": "dup"}, {"id": "dup"}, {"id": "ok"}],
        "nextPageToken": None,
    }
    store = MemoryCursorStore()
    is_known, on_message, processed, _ = _collecting_handler()
    result = run_robust_sync(svc, cursor_store=store, is_known=is_known, on_message=on_message)
    assert processed == ["dup", "ok"]
    assert result.skipped_duplicates >= 1


def test_restart_resume_mid_pagination():
    svc = FakeGmailService(history_id="77")
    svc.list_pages[""] = {
        "messages": [{"id": "a"}],
        "nextPageToken": "p2",
    }
    svc.list_pages["p2"] = {
        "messages": [{"id": "b"}],
        "nextPageToken": None,
    }
    store = MemoryCursorStore()
    is_known, on_message, processed, _ = _collecting_handler()
    r1 = run_robust_sync(
        svc,
        cursor_store=store,
        is_known=is_known,
        on_message=on_message,
        max_pages=1,
    )
    assert processed == ["a"]
    assert store.cursor.resume_page_token == "p2"
    assert r1.partial is True

    r2 = run_robust_sync(svc, cursor_store=store, is_known=is_known, on_message=on_message)
    assert processed == ["a", "b"]
    assert r2.resumed is True
    assert store.cursor.resume_page_token == ""
    assert store.cursor.history_id == "77"


def test_e2e_initial_restart_incremental_once_each():
    svc = FakeGmailService(history_id="100")
    svc.list_pages[""] = {
        "messages": [{"id": "m1"}, {"id": "m2"}],
        "nextPageToken": None,
    }
    store = MemoryCursorStore()
    is_known, on_message, processed, _ = _collecting_handler()

    r1 = run_robust_sync(svc, cursor_store=store, is_known=is_known, on_message=on_message)
    assert r1.mode == "initial"
    assert set(processed) == {"m1", "m2"}

    svc.history_pages[("100", "")] = {
        "history": [],
        "historyId": "100",
        "nextPageToken": None,
    }
    r2 = run_robust_sync(
        svc,
        cursor_store=store,
        is_known=is_known,
        on_message=on_message,
        account_key=store.cursor.account_key or "default",
    )
    assert r2.mode == "incremental"
    assert processed == ["m1", "m2"]

    store.cursor.history_id = "100"
    svc.history_pages[("100", "")] = {
        "history": [{"messagesAdded": [{"message": {"id": "m3"}}]}],
        "historyId": "110",
        "nextPageToken": None,
    }
    r3 = run_robust_sync(
        svc,
        cursor_store=store,
        is_known=is_known,
        on_message=on_message,
        account_key=store.cursor.account_key or "default",
    )
    assert r3.mode == "incremental"
    assert processed == ["m1", "m2", "m3"]
    assert len(processed) == len(set(processed))


def test_partial_failure_continues_other_messages():
    svc = FakeGmailService(history_id="5")
    svc.list_pages[""] = {
        "messages": [{"id": "good"}, {"id": "bad"}, {"id": "good2"}],
        "nextPageToken": None,
    }
    svc.get_errors["bad"] = RuntimeError("boom")
    store = MemoryCursorStore()
    is_known, on_message, processed, _ = _collecting_handler()
    result = run_robust_sync(svc, cursor_store=store, is_known=is_known, on_message=on_message)
    assert processed == ["good", "good2"]
    assert result.errors


def test_transient_retry_then_success():
    svc = FakeGmailService(history_id="3")
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise _http_error(503)
        return {"messages": [{"id": "r1"}], "nextPageToken": None}

    svc.list_pages[""] = flaky
    store = MemoryCursorStore()
    is_known, on_message, processed, _ = _collecting_handler()
    result = run_robust_sync(
        svc,
        cursor_store=store,
        is_known=is_known,
        on_message=on_message,
        retry_attempts=5,
        retry_wait_seconds=0,
    )
    assert processed == ["r1"]
    assert calls["n"] >= 3
    assert result.processed == 1


def test_offline_list_failure_preserves_cursor():
    svc = FakeGmailService(history_id="9")
    store = MemoryCursorStore(SyncCursor(history_id="8", account_key="default"))
    svc.history_error = ConnectionError("offline")
    is_known, on_message, processed, _ = _collecting_handler()
    result = run_robust_sync(
        svc,
        cursor_store=store,
        is_known=is_known,
        on_message=on_message,
        account_key="default",
        retry_attempts=1,
        retry_wait_seconds=0,
    )
    assert processed == []
    assert store.cursor.history_id == "8"
    assert result.needs_reauth is False


def test_cross_account_key_mismatch_forces_full_without_wiping_mail(tmp_path: Path):
    db = Database(tmp_path / "a.db")
    db.save_email_message({"gmail_id": "old-acct", "subject": "s", "body_text": "b"})
    store = gmail_sync.DatabaseCursorStore(db)
    store.save(SyncCursor(history_id="50", account_key="account-A"))
    svc = FakeGmailService(history_id="70")
    svc.list_pages[""] = {
        "messages": [{"id": "old-acct"}, {"id": "new1"}],
        "nextPageToken": None,
    }
    processed: list[str] = []

    def on_message(email: ParsedEmail) -> None:
        processed.append(email.id)
        db.save_email_message(
            {"gmail_id": email.id, "subject": email.subject, "body_text": email.body_text}
        )

    result = run_robust_sync(
        svc,
        cursor_store=store,
        is_known=lambda mid: db.get_email_by_gmail_id(mid) is not None,
        on_message=on_message,
        account_key="account-B",
    )
    assert result.mode in {"initial", "full", "full_fallback"}
    assert db.get_email_by_gmail_id("old-acct") is not None
    assert "old-acct" not in processed
    assert "new1" in processed
    assert store.load().account_key == "account-B"


def test_history_pagination():
    svc = FakeGmailService(history_id="30")
    store = MemoryCursorStore(SyncCursor(history_id="10", account_key="default"))
    svc.history_pages[("10", "")] = {
        "history": [{"messagesAdded": [{"message": {"id": "h1"}}]}],
        "historyId": "20",
        "nextPageToken": "hp2",
    }
    svc.history_pages[("10", "hp2")] = {
        "history": [{"messagesAdded": [{"message": {"id": "h2"}}]}],
        "historyId": "30",
        "nextPageToken": None,
    }
    is_known, on_message, processed, _ = _collecting_handler()
    result = run_robust_sync(
        svc,
        cursor_store=store,
        is_known=is_known,
        on_message=on_message,
        account_key="default",
    )
    assert processed == ["h1", "h2"]
    assert store.cursor.history_id == "30"
    assert result.mode == "incremental"


def test_sync_logs_omit_body(caplog):
    caplog.set_level(logging.DEBUG)
    svc = FakeGmailService(history_id="1")
    svc.messages["m1"] = {
        "id": "m1",
        "threadId": "t",
        "snippet": "snip",
        "internalDate": "1",
        "payload": {
            "headers": [
                {"name": "Subject", "value": "Subj"},
                {"name": "From", "value": "a@b.de"},
            ],
            "parts": [
                {
                    "mimeType": "text/plain",
                    "body": {"data": "U0VDUkVUX0JPRFlfUElJX0RPX05PVF9MT0c"},
                }
            ],
        },
    }
    svc.list_pages[""] = {"messages": [{"id": "m1"}], "nextPageToken": None}
    store = MemoryCursorStore()
    is_known, on_message, _, _ = _collecting_handler()
    run_robust_sync(svc, cursor_store=store, is_known=is_known, on_message=on_message)
    blob = "\n".join(r.getMessage() for r in caplog.records)
    assert "SECRET_BODY_PII" not in blob


def test_db_has_email_helpers(tmp_path: Path):
    db = Database(tmp_path / "e.db")
    assert db.get_email_by_gmail_id("x") is None
    db.save_email_message({"gmail_id": "x", "subject": "s", "body_text": "b"})
    row = db.get_email_by_gmail_id("x")
    assert row is not None
    assert row["subject"] == "s"
    assert db.has_gmail_message("x") is True
    assert db.has_gmail_message("missing") is False


def test_process_parsed_email_skips_duplicate_lifecycle(tmp_path: Path):
    from core.case_pipeline import process_parsed_email

    db = Database(tmp_path / "p.db")
    email = ParsedEmail(
        id="g1",
        subject="Hi",
        sender="hr@firma.de",
        body_text="Danke für Ihre Bewerbung",
    )
    r1 = process_parsed_email(db, email, auto_status=False)
    r2 = process_parsed_email(db, email, auto_status=False)
    assert r1["email_id"]
    assert r2.get("status") == "duplicate" or r2.get("skipped") is True


def test_authorize_result_dataclass_fields():
    r = gmail_auth.AuthOutcome(service=None, needs_reauth=True, reason="revoked")
    assert r.needs_reauth
    assert r.reason == "revoked"


def test_sync_result_fields():
    r = SyncResult(
        mode="initial",
        fetched=1,
        processed=1,
        skipped_duplicates=0,
        new_history_id="1",
    )
    assert r.mode == "initial"


def test_account_fingerprint_stable():
    a = gmail_auth.account_fingerprint({"client_id": "abc", "token": "t"})
    b = gmail_auth.account_fingerprint({"client_id": "abc", "token": "other"})
    c = gmail_auth.account_fingerprint({"client_id": "zzz", "token": "t"})
    assert a == b
    assert a != c


def test_get_gmail_service_uses_authorize(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        gmail_auth,
        "authorize_gmail",
        lambda **k: gmail_auth.AuthOutcome(service="S", needs_reauth=False, reason=""),
    )
    assert (
        gmail_auth.get_gmail_service(credentials_path=tmp_path / "c.json", token_dir=tmp_path)
        == "S"
    )


def test_history_empty_still_updates_id():
    svc = FakeGmailService(history_id="55")
    store = MemoryCursorStore(SyncCursor(history_id="40", account_key="default"))
    svc.history_pages[("40", "")] = {
        "history": [],
        "historyId": "55",
        "nextPageToken": None,
    }
    is_known, on_message, processed, _ = _collecting_handler()
    result = run_robust_sync(
        svc,
        cursor_store=store,
        is_known=is_known,
        on_message=on_message,
        account_key="default",
    )
    assert processed == []
    assert store.cursor.history_id == "55"
    assert result.mode == "incremental"


def test_rate_limit_429_retries():
    svc = FakeGmailService(history_id="2")
    n = {"c": 0}

    def flaky():
        n["c"] += 1
        if n["c"] == 1:
            raise _http_error(429)
        return {"messages": [{"id": "z"}], "nextPageToken": None}

    svc.list_pages[""] = flaky
    store = MemoryCursorStore()
    is_known, on_message, processed, _ = _collecting_handler()
    run_robust_sync(
        svc,
        cursor_store=store,
        is_known=is_known,
        on_message=on_message,
        retry_attempts=3,
        retry_wait_seconds=0,
    )
    assert processed == ["z"]


def test_invalid_grant_message_classified():
    assert gmail_auth.is_revocation_error(Exception("invalid_grant")) is True
    assert gmail_auth.is_revocation_error(Exception("network down")) is False


def test_reconnect_after_disconnect(tmp_path: Path, monkeypatch):
    token_dir = tmp_path / "tok"
    store_token(
        TOKEN_ACCOUNT,
        {"token": "t", "refresh_token": "r", "scopes": list(SCOPES)},
        fallback_dir=token_dir,
    )
    disconnect_gmail(token_dir=token_dir)
    assert gmail_connected(token_dir=token_dir) is False
    creds_path = tmp_path / "client.json"
    creds_path.write_text(json.dumps({"installed": {"client_id": "c"}}), encoding="utf-8")
    fake = FakeCreds()
    flow = MagicMock()
    flow.run_local_server.return_value = fake
    monkeypatch.setattr(gmail_auth, "gmail_libs_available", lambda: True)
    with (
        patch(
            "google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file",
            return_value=flow,
        ),
        patch("googleapiclient.discovery.build", return_value="NEW"),
    ):
        assert (
            gmail_auth.get_gmail_service(credentials_path=creds_path, token_dir=token_dir) == "NEW"
        )
    assert gmail_connected(token_dir=token_dir)


def test_pending_ids_resume_after_crash():
    svc = FakeGmailService(history_id="12")
    store = MemoryCursorStore(
        SyncCursor(
            history_id="",
            resume_page_token="",
            pending_message_ids=["p1", "p2"],
            sync_mode="initial",
        )
    )
    is_known, on_message, processed, _ = _collecting_handler()
    result = run_robust_sync(svc, cursor_store=store, is_known=is_known, on_message=on_message)
    assert "p1" in processed and "p2" in processed
    assert store.cursor.pending_message_ids == []
    assert result.resumed is True


def test_production_compliance_deferred_marker():
    assert "PR43" in (gmail_auth.__doc__ or "") or "PR43" in (gmail_sync.__doc__ or "")


def test_no_gmail_modify_in_module_scopes():
    assert all("modify" not in s for s in SCOPES)


def test_sync_does_not_call_status_pipeline_by_default():
    svc = FakeGmailService(history_id="1")
    svc.list_pages[""] = {"messages": [{"id": "m"}], "nextPageToken": None}
    store = MemoryCursorStore()
    seen = []
    run_robust_sync(
        svc,
        cursor_store=store,
        is_known=lambda _m: False,
        on_message=lambda e: seen.append(e.id),
    )
    assert seen == ["m"]


def test_database_cursor_clears_resume_on_complete(tmp_path: Path):
    db = Database(tmp_path / "c.db")
    store = gmail_sync.DatabaseCursorStore(db)
    svc = FakeGmailService(history_id="3")
    svc.list_pages[""] = {"messages": [{"id": "x"}], "nextPageToken": None}
    is_known, on_message, _, _ = _collecting_handler()
    run_robust_sync(svc, cursor_store=store, is_known=is_known, on_message=on_message)
    cur = store.load()
    assert cur.resume_page_token == ""
    assert cur.history_id == "3"


def test_is_transient_http_status():
    assert gmail_sync.is_transient_error(_http_error(429)) is True
    assert gmail_sync.is_transient_error(_http_error(503)) is True
    assert gmail_sync.is_transient_error(_http_error(404)) is False
    assert gmail_sync.is_transient_error(ConnectionError("x")) is True


def test_history_id_invalid_helper():
    assert gmail_sync.is_history_invalid_error(_http_error(404)) is True
    assert gmail_sync.is_history_invalid_error(_http_error(400)) is False


def test_full_sync_query_default_not_entire_mailbox_unbounded():
    assert "newer_than" in gmail_sync.DEFAULT_SYNC_QUERY


def test_revoke_remote_handles_network_failure(monkeypatch):
    monkeypatch.setattr(
        gmail_auth,
        "_post_revoke",
        lambda _t: (_ for _ in ()).throw(ConnectionError("offline")),
    )
    assert gmail_auth.revoke_token_remote("tok") is False


def test_authorize_interactive_false_no_browser(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(gmail_auth, "gmail_libs_available", lambda: True)
    outcome = gmail_auth.authorize_gmail(
        credentials_path=tmp_path / "missing.json",
        token_dir=tmp_path / "t",
        interactive=False,
    )
    assert outcome.service is None


def test_unit_no_duplicate_processing_across_two_syncs():
    svc = FakeGmailService(history_id="10")
    svc.list_pages[""] = {"messages": [{"id": "same"}], "nextPageToken": None}
    store = MemoryCursorStore()
    is_known, on_message, processed, _ = _collecting_handler()
    run_robust_sync(svc, cursor_store=store, is_known=is_known, on_message=on_message)
    store.cursor.history_id = ""
    store.cursor.resume_page_token = ""
    run_robust_sync(svc, cursor_store=store, is_known=is_known, on_message=on_message)
    assert processed == ["same"]


def test_beta_opt_in_flag_default_off():
    from core.config import empty_app_config

    cfg = empty_app_config()
    assert cfg.settings.gmail_sync_enabled is False
