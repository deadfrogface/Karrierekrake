"""Connection checks and mailbox identifiers must reflect the correct account."""
from types import SimpleNamespace

import pytest

from integrations.providers import connection_probe as probes
from integrations.mail.imap import adapter as imap


@pytest.fixture(autouse=True)
def clean_cache():
    probes.clear_probe_cache()
    yield
    probes.clear_probe_cache()


def test_probe_result_does_not_leak_between_profiles(tmp_path):
    assert probes.probe_microsoft_graph(provider="microsoft_graph_mail", token_dir=tmp_path / "a", graph_get=lambda _: {"id": "a"}).connected
    other = probes.probe_microsoft_graph(provider="microsoft_graph_mail", token_dir=tmp_path / "b", graph_get=lambda _: {})
    assert not other.connected
    probes.clear_probe_cache("microsoft_graph_mail")
    assert not probes._PROBE_CACHE


def test_calendar_scope_string_and_per_calendar_errors(monkeypatch, tmp_path):
    from integrations import google_oauth, gmail_auth
    response = {"calendars": {"primary": {"busy": []}}}
    service = SimpleNamespace(freebusy=lambda: SimpleNamespace(query=lambda **_: SimpleNamespace(execute=lambda: response)))
    monkeypatch.setattr(google_oauth, "load_google_token", lambda **_: {"scope": google_oauth.CALENDAR_FREEBUSY})
    monkeypatch.setattr(gmail_auth, "creds_from_payload", lambda _: object())
    monkeypatch.setattr(google_oauth, "build_calendar_service", lambda _: service)
    assert probes.probe_google_calendar(token_dir=tmp_path, force=True).connected
    response["calendars"]["primary"] = {"errors": [{"reason": "forbidden"}]}
    assert not probes.probe_google_calendar(token_dir=tmp_path, force=True).connected


class Mailbox:
    def __init__(self, *args, **kwargs):
        self.closed = False
        self.validity = b"100"
        self.fail = False
    def login(self, *args): pass
    def select(self, *args, **kwargs): return "OK", [b"1"]
    def response(self, _): return "UIDVALIDITY", [self.validity]
    def uid(self, command, *args):
        if self.fail: raise OSError("connection lost")
        if command == "search": return "OK", [b"27"]
        assert args[1] == "(BODY.PEEK[])"
        return "OK", [(b"27", b"Subject: Interview\r\nFrom: hiring@example.test\r\nDate: Tue, 29 Sep 2026 12:00:00 +0200\r\nMessage-ID: <a@example.test>\r\n\r\nHello")]
    def logout(self): self.closed = True


def test_imap_uid_namespaces_and_disconnect_on_failure(monkeypatch):
    box = Mailbox()
    monkeypatch.setattr(imap.imaplib, "IMAP4_SSL", lambda *a, **k: box)
    ep = imap.ImapEndpoint("mail.example.test", username="first")
    a = imap._fetch_imap_messages(ep, {"password": "test"})[0]
    assert box.closed and a.internal_date and a.thread_id
    assert a.provider_message_id == a.external_message_id
    ep.username = "second"
    b = imap._fetch_imap_messages(ep, {"password": "test"})[0]
    assert a.external_message_id != b.external_message_id
    box.validity = b"101"
    c = imap._fetch_imap_messages(ep, {"password": "test"})[0]
    assert b.external_message_id != c.external_message_id
    box.closed = False
    box.fail = True
    with pytest.raises(imap.ProviderError):
        imap._fetch_imap_messages(ep, {"password": "test"})
    assert box.closed
