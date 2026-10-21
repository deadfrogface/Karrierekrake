"""Own recurrence expansion and DAV safety rules (RFC 5545 / RFC 4791), offline."""
from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest
from icalendar import Calendar

from integrations.calendar.caldav.dav import DAVClient, DavError
from integrations.calendar.caldav.recurrence import expand

BERLIN = ZoneInfo("Europe/Berlin")


def ics(*events: str) -> str:
    return "BEGIN:VCALENDAR\r\nVERSION:2.0\r\n" + "".join(
        f"BEGIN:VEVENT\r\nUID:u1\r\n{body}\r\nEND:VEVENT\r\n" for body in events) + "END:VCALENDAR\r\n"


def starts(texts: list[str]) -> list[str]:
    out = []
    for text in texts:
        part = Calendar.from_ical(text).walk("VEVENT")[0]
        value = part.decoded("DTSTART")
        out.append(value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M") if isinstance(value, datetime) else str(value))
    return sorted(out)


def window(day_from: int, day_to: int) -> tuple[datetime, datetime]:
    return datetime(2026, 10, day_from, tzinfo=UTC), datetime(2026, 10, day_to, tzinfo=UTC)


def test_daily_count_with_exdate_and_window_edges():
    text = ics("DTSTART:20261005T100000Z\r\nDTEND:20261005T110000Z\r\nRRULE:FREQ=DAILY;COUNT=5\r\nEXDATE:20261006T100000Z")
    assert starts(expand([text], *window(5, 9), BERLIN)) == [
        "2026-10-05T10:00", "2026-10-07T10:00", "2026-10-08T10:00"]
    assert starts(expand([text], *window(7, 8), BERLIN)) == ["2026-10-07T10:00"]


def test_weekly_by_day_until_and_override_replaces_its_occurrence():
    series = ("DTSTART;TZID=Europe/Berlin:20261005T090000\r\nDTEND;TZID=Europe/Berlin:20261005T100000\r\n"
              "RRULE:FREQ=WEEKLY;BYDAY=MO,WE;UNTIL=20261014T000000Z")
    moved = ("RECURRENCE-ID;TZID=Europe/Berlin:20261007T090000\r\nDTSTART;TZID=Europe/Berlin:20261007T150000\r\n"
             "DTEND;TZID=Europe/Berlin:20261007T160000")
    got = starts(expand([ics(series, moved)], *window(1, 31), BERLIN))
    # Mon 5, (Wed 7 moved to 15:00 local = 13:00 UTC), Mon 12; Wed 14 is after UNTIL
    assert got == ["2026-10-05T07:00", "2026-10-07T13:00", "2026-10-12T07:00"]


def test_dst_keeps_local_wall_time():
    text = ics("DTSTART;TZID=Europe/Berlin:20261024T100000\r\nDTEND;TZID=Europe/Berlin:20261024T110000\r\n"
               "RRULE:FREQ=DAILY;COUNT=3")
    # Clocks go back on 2026-10-25: 10:00 local is 08:00 UTC before and 09:00 UTC after.
    assert starts(expand([text], *window(24, 28), BERLIN)) == [
        "2026-10-24T08:00", "2026-10-25T09:00", "2026-10-26T09:00"]


def test_all_day_and_floating_events_use_the_account_time_zone():
    all_day = ics("DTSTART;VALUE=DATE:20261010\r\nRRULE:FREQ=DAILY;COUNT=2")
    got = expand([all_day], *window(1, 31), BERLIN)
    assert starts(got) == ["2026-10-10", "2026-10-11"]
    floating = ics("DTSTART:20261010T090000\r\nDTEND:20261010T100000")
    assert starts(expand([floating], *window(1, 31), BERLIN)) == ["2026-10-10T07:00"]


def test_single_event_outside_window_and_titles_are_not_copied():
    text = ics("DTSTART:20261020T100000Z\r\nDTEND:20261020T110000Z\r\nSUMMARY:Geheimer Titel")
    assert expand([text], *window(1, 5), BERLIN) == []
    inside = expand([text], *window(19, 22), BERLIN)
    assert len(inside) == 1 and "Geheimer" not in inside[0]


def test_cancelled_and_transparent_flags_survive_and_garbage_is_skipped():
    text = ics("DTSTART:20261020T100000Z\r\nDTEND:20261020T110000Z\r\nSTATUS:CANCELLED\r\nTRANSP:TRANSPARENT")
    out = expand(["not a calendar", text], *window(19, 22), BERLIN)
    assert len(out) == 1 and "STATUS:CANCELLED" in out[0] and "TRANSP:TRANSPARENT" in out[0]


def test_open_ended_rule_is_capped_not_endless():
    text = ics("DTSTART:20261001T000000Z\r\nDTEND:20261001T000100Z\r\nRRULE:FREQ=MINUTELY")
    assert len(expand([text], *window(1, 2), BERLIN)) <= 2000


def test_dav_requires_tls_and_never_leaves_the_account_site(monkeypatch):
    with pytest.raises(DavError, match="tls_required"):
        DAVClient(url="http://calendar.example.org/")
    client = DAVClient(url="https://caldav.example.org/dav/", username="u", password="p")
    try:
        with pytest.raises(DavError, match="foreign_host"):
            client.request("https://evil.example.net/dav/", "PROPFIND")
        with pytest.raises(DavError, match="foreign_host"):
            client.request("http://caldav.example.org/dav/", "PROPFIND")
    finally:
        client.close()
