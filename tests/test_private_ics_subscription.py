"""Regression tests for free private ICS subscriptions."""
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
import pytest
from integrations.calendar.local_ics import refresh_private_ics


def test_private_ics_rejects_http_and_private_addresses(tmp_path):
    target = tmp_path / "calendar.ics"
    with pytest.raises(ValueError):
        refresh_private_ics("http://example.com/calendar.ics", target)
    with pytest.raises(ValueError):
        refresh_private_ics("https://127.0.0.1/calendar.ics", target)
    assert not target.exists()


def test_private_ics_validates_before_atomic_replace(tmp_path, monkeypatch):
    import integrations.calendar.local_ics as ics
    target = tmp_path / "calendar.ics"
    old = b"BEGIN:VCALENDAR\r\nVERSION:2.0\r\nEND:VCALENDAR\r\n"
    target.write_bytes(old)
    monkeypatch.setattr(ics.socket, "getaddrinfo", lambda *a, **kw: [(2, 1, 6, "", ("93.184.215.14", 443))])
    class Response:
        status = 200
        def read(self, count):
            return b"not an ics"
    class Conn:
        def __init__(self, *a, **kw): pass
        def request(self, *a, **kw): pass
        def getresponse(self): return Response()
        def close(self): pass
    monkeypatch.setattr(ics.http.client, "HTTPSConnection", Conn)
    # The implementation uses a pinned subclass; override the connection's
    # inherited methods without opening any network socket.
    monkeypatch.setattr(ics.http.client.HTTPSConnection, "connect", lambda self: None)
    with pytest.raises(Exception):
        refresh_private_ics("https://example.com/private.ics", target)
    assert target.read_bytes() == old
