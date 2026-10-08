"""Offline regression tests for private read-only ICS subscriptions."""
import socket
from types import SimpleNamespace

import pytest

from integrations.calendar import local_ics as ics


VALID = b"BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//Karrierekrake Test//EN\r\nEND:VCALENDAR\r\n"


def test_rejects_insecure_or_private_feed(tmp_path):
    target = tmp_path / "calendar.ics"
    for url in ("http://example.com/calendar.ics", "https://127.0.0.1/calendar.ics",
                "https://user:password@example.com/calendar.ics", "https://example.com:8443/x"):
        with pytest.raises(ValueError):
            ics.refresh_private_ics(url, target)
    assert not target.exists()


def test_rejects_mixed_dns_answers(tmp_path, monkeypatch):
    monkeypatch.setattr(ics.socket, "getaddrinfo", lambda *a, **kw: [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443)),
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443)),
    ])
    with pytest.raises(ValueError, match="Private Netzwerkadressen"):
        ics.refresh_private_ics("https://example.com/secret.ics", tmp_path / "calendar.ics")


def test_atomic_refresh_and_reject_invalid_payload(tmp_path, monkeypatch):
    target = tmp_path / "calendar.ics"
    target.write_bytes(VALID)
    monkeypatch.setattr(ics.socket, "getaddrinfo", lambda *a, **kw: [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))
    ])
    payload = [b"invalid", VALID]
    class FakeConnection:
        def __init__(self, *a, **kw): pass
        def request(self, *a, **kw): pass
        def getresponse(self):
            return SimpleNamespace(status=200, read=lambda n: payload.pop(0))
        def close(self): pass
    monkeypatch.setattr(ics.http.client, "HTTPSConnection", FakeConnection)
    with pytest.raises(Exception):
        ics.refresh_private_ics("https://example.com/secret.ics", target)
    assert target.read_bytes() == VALID
    assert ics.refresh_private_ics("https://example.com/secret.ics", target)
    assert target.read_bytes() == VALID


def test_rejects_redirect_without_replacing_cache(tmp_path, monkeypatch):
    target = tmp_path / "calendar.ics"
    target.write_bytes(VALID)
    monkeypatch.setattr(ics.socket, "getaddrinfo", lambda *a, **kw: [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))
    ])
    class RedirectConnection:
        def __init__(self, *a, **kw): pass
        def request(self, *a, **kw): pass
        def getresponse(self): return SimpleNamespace(status=302)
        def close(self): pass
    monkeypatch.setattr(ics.http.client, "HTTPSConnection", RedirectConnection)
    with pytest.raises(ValueError, match="HTTP 302"):
        ics.refresh_private_ics("https://example.com/secret.ics", target)
    assert target.read_bytes() == VALID
