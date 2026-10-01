"""Real CalDAV bridge with a simulated server transport, no account writes."""
from datetime import datetime, timezone
from types import SimpleNamespace as NS

import pytest
from integrations.calendar.caldav.client import LiveCaldavClient
from integrations.providers.enums import ProviderError

SECRET = {"base_url": "https://calendar.example.org/", "username": "demo", "password": "test-only"}
START = datetime(2026, 10, 1, tzinfo=timezone.utc)
END = datetime(2026, 10, 4, tzinfo=timezone.utc)


def ics(body):
    return "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VEVENT\r\nUID:test-one\r\n" + body + "\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n"


class Calendar:
    url = "https://calendar.example.org/cal/"
    def __init__(self, events=()):
        self.events = events
    def search(self, **kwargs):
        assert kwargs == dict(event=True, start=START, end=END, expand=True)
        return [NS(data=e) for e in self.events]


class Client:
    def __init__(self, calendars=None):
        self.items = calendars if calendars is not None else [Calendar()]
        self.closed = False
        self.calls = []
        self.response = NS(status=201, headers={"ETag": '"one"'})
    def principal(self):
        return self
    def calendars(self):
        return self.items
    def close(self):
        self.closed = True
    def put(self, url, data, headers):
        self.calls.append((url, data, headers))
        return self.response
    def get(self, url):
        return self.existing


def bridge(client, **extra):
    def factory(**kwargs):
        assert kwargs["ssl_verify_cert"] and kwargs["require_tls"]
        assert kwargs["timeout"] == 20
        return client
    return LiveCaldavClient({**SECRET, **extra}, client_factory=factory)


@pytest.mark.parametrize("url", ["http://calendar.example.org", "https://user:pass@calendar.example.org", "garbage", "https://"])
def test_requires_tls_without_embedded_credentials(url):
    with pytest.raises(ProviderError):
        LiveCaldavClient({**SECRET, "base_url": url})


def test_discovery_and_selection_close_session():
    client = Client()
    assert bridge(client, calendar_path="/cal/").discover_calendars() == [Calendar.url]
    assert client.closed
    with pytest.raises(ProviderError, match="caldav_calendar_not_found"):
        bridge(client, calendar_path="/absent/").discover_calendars()


def test_all_day_duration_transparent_cancelled_and_dedup():
    timed = ics("DTSTART:20261001T120000Z\r\nDURATION:PT1H\r\nSUMMARY:Private title")
    events = [timed, timed, ics("DTSTART;VALUE=DATE:20261002"),
              ics("DTSTART:20261001T150000Z\r\nDURATION:PT1H\r\nTRANSP:TRANSPARENT"),
              ics("DTSTART:20261001T160000Z\r\nDURATION:PT1H\r\nSTATUS:CANCELLED")]
    client = Client([Calendar(events)])
    assert bridge(client).list_busy(time_min=START, time_max=END) == [
        {"start": "2026-10-01T12:00:00+00:00", "end": "2026-10-01T13:00:00+00:00"},
        {"start": "2026-10-01T22:00:00+00:00", "end": "2026-10-02T22:00:00+00:00"}]
    assert client.closed


def test_errors_sanitized_and_closed():
    client = Client()
    def fail():
        raise RuntimeError("password-and-event-content")
    client.principal = fail
    with pytest.raises(ProviderError) as exc:
        bridge(client).discover_calendars()
    assert "password-and-event" not in str(exc.value)
    assert client.closed


def test_missing_calendar_does_not_look_like_free_time():
    with pytest.raises(ProviderError):
        bridge(Client([])).list_busy(time_min=START, time_max=END)


def test_create_retry_is_idempotent_but_conflict_not_overwritten():
    event = ics("DTSTART:20261001T120000Z\r\nDTEND:20261001T130000Z\r\nSUMMARY:Interview")
    client = Client()
    transport = bridge(client)
    result = transport.put_event(href="test-one.ics", ics=event)
    assert result["etag"] == '"one"'
    assert client.calls[-1][2]["If-None-Match"] == "*"
    client.response.status = 412
    client.existing = NS(status=200, raw=event, headers={"ETag": '"one"'})
    assert transport.put_event(href="test-one.ics", ics=event) == result
    client.existing.raw = event.replace("Interview", "Different")
    with pytest.raises(ProviderError, match="caldav_event_conflict"):
        transport.put_event(href="test-one.ics", ics=event)


def test_update_uses_etag_and_preserves_returned_href():
    client = Client()
    event = ics("DTSTART:20261001T120000Z\r\nDTEND:20261001T130000Z")
    bridge(client).put_event(href=Calendar.url + "test.ics", ics=event, etag='"old"')
    assert client.calls[-1][0] == Calendar.url + "test.ics"
    assert client.calls[-1][2]["If-Match"] == '"old"'
    with pytest.raises(ProviderError):
        bridge(client).put_event(href="https://other.example.org/a", ics=event)


def test_multiple_calendars_require_explicit_target_for_write():
    with pytest.raises(ProviderError, match="caldav_select_calendar"):
        bridge(Client([Calendar(), Calendar()])).put_event(href="x.ics", ics=ics("DTSTART:20261001T120000Z"))


def test_production_adapter_loads_secret_and_enforces_approval(monkeypatch, tmp_path):
    from integrations.calendar.caldav import adapter
    from integrations.calendar.contracts import CalendarProposal
    client = Client()
    monkeypatch.setattr(adapter, "load_caldav_secret", lambda **kw: SECRET)
    monkeypatch.setattr("caldav.DAVClient", lambda **kw: client)
    transport = adapter.GenericCaldavCalendarAdapter(token_dir=tmp_path, settings=NS(allow_calendar_write=True))
    assert transport.discover() == [Calendar.url]
    draft = CalendarProposal(case_id="test", title="Interview", start="2026-10-01T12:00:00Z", end="2026-10-01T13:00:00Z").to_draft()
    with pytest.raises(ProviderError, match="calendar_event_not_approved"):
        transport.create_event(draft)
    draft.approved = True
    assert transport.create_event(draft).external_event_id.endswith(".ics")
    transport.settings.allow_calendar_write = False
    with pytest.raises(ProviderError, match="calendar_write_disabled"):
        transport.create_event(draft)


def test_google_calendar_does_not_use_empty_mock_without_credentials(monkeypatch, tmp_path):
    from integrations.calendar.google.adapter import GoogleCalendarAdapter
    from integrations.calendar_freebusy import FreeBusyQuery, GoogleFreeBusyProvider
    monkeypatch.setattr("integrations.google_oauth.load_google_token", lambda **kw: None)
    with pytest.raises(ProviderError):
        GoogleCalendarAdapter(token_dir=tmp_path).query_busy(FreeBusyQuery(START, END))
    service = NS(freebusy=lambda: NS(query=lambda **kw: NS(execute=lambda: {"calendars": {"primary": {"errors": [{"reason": "notFound"}]}}})))
    with pytest.raises(RuntimeError, match="calendar_freebusy_unavailable"):
        GoogleFreeBusyProvider(service).query(FreeBusyQuery(START, END))


def test_google_calendar_approved_write_uses_live_service(monkeypatch, tmp_path):
    from integrations.calendar.google.adapter import GoogleCalendarAdapter
    from integrations.calendar.contracts import CalendarProposal
    captured = []
    service = NS(events=lambda: NS(insert=lambda **kw: captured.append(kw) or NS(execute=lambda: {"id": kw["body"]["id"]})))
    adapter = GoogleCalendarAdapter(token_dir=tmp_path, settings=NS(allow_calendar_write=True))
    monkeypatch.setattr(adapter, "_service", lambda: service)
    draft = CalendarProposal(case_id="demo", title="Interview", start="2026-10-01T12:00:00Z", end="2026-10-01T13:00:00Z").to_draft()
    with pytest.raises(ProviderError):
        adapter.create_event(draft)
    assert not captured
    draft.approved = True
    result = adapter.create_event(draft)
    assert captured[0]["calendarId"] == "primary"
    assert result.external_event_id == captured[0]["body"]["id"]
    adapter.settings.allow_calendar_write = False
    with pytest.raises(ProviderError):
        adapter.create_event(draft)
    assert len(captured) == 1
