"""Recurring events (RFC 5545) expanded into single occurrences for a time window.

Written for Karrierekrake from RFC 5545 (RRULE, RDATE, EXDATE, RECURRENCE-ID) with python-dateutil's rule
engine. Input is calendar-object text as a CalDAV server returns it; output is one small calendar text per
occurrence with the fields the busy-time reader needs (UID, DTSTART, DTEND, STATUS, TRANSP). Event titles and
descriptions are not copied.
"""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import date, datetime, time, timedelta, tzinfo
from itertools import islice
from typing import Any

from dateutil.rrule import rruleset, rrulestr
from icalendar import Calendar, Event

MAX_OCCURRENCES = 2000


def _is_date(value: Any) -> bool:
    return isinstance(value, date) and not isinstance(value, datetime)


def _datetimes(prop: Any) -> list[Any]:
    """Values of an EXDATE / RDATE property (one or several lists, each with several dates)."""
    out: list[Any] = []
    for entry in prop if isinstance(prop, list) else [prop]:
        out.extend(getattr(dt, "dt", dt) for dt in getattr(entry, "dts", [entry]))
    return out


class _Master:
    """One recurring (or single) event with its start style: all-day date, floating time or aware time."""

    def __init__(self, event: Any, tz: tzinfo) -> None:
        self.event = event
        self.tz = tz
        raw = event.decoded("DTSTART")
        self.all_day = _is_date(raw)
        self.start = datetime.combine(raw, time.min) if self.all_day else raw
        self.floating = self.start.tzinfo is None
        default = timedelta(days=1) if self.all_day else timedelta()
        self.length = default
        if "DTEND" in event:
            end = event.decoded("DTEND")
            end = datetime.combine(end, time.min) if _is_date(end) else end
            try:
                self.length = end - self.start
            except TypeError:  # one side aware, the other floating: keep the default
                pass
        elif "DURATION" in event:
            self.length = event.decoded("DURATION")

    def local(self, value: Any) -> datetime:
        """Bring a date / datetime to the style of this event's start so that it can be compared and iterated."""
        if _is_date(value):
            value = datetime.combine(value, time.min)
        if self.floating:
            return value.astimezone(self.tz).replace(tzinfo=None) if value.tzinfo else value
        return value if value.tzinfo else value.replace(tzinfo=self.tz)

    def window(self, start: datetime, end: datetime) -> tuple[datetime, datetime]:
        return self.local(start), self.local(end)

    def aware(self, value: datetime) -> datetime:
        return value if value.tzinfo else value.replace(tzinfo=self.tz)

    def occurrences(self, start: datetime, end: datetime) -> list[datetime]:
        """Start times of all occurrences that may overlap [start, end)."""
        first, last = self.window(start, end)
        rules = self.event.get("RRULE")
        rdates = _datetimes(self.event.get("RDATE")) if "RDATE" in self.event else []
        if rules is None and not rdates:
            return [self.start]
        rs = rruleset()
        for rule in rules if isinstance(rules, list) else ([rules] if rules is not None else []):
            text = rule.to_ical().decode()
            if self.floating or self.all_day:
                text = re.sub(r"(UNTIL=\d{8}T\d{6})Z", r"\1", text)
                text = re.sub(r"UNTIL=(\d{8})(?!T)", r"UNTIL=\1T235959", text)
            else:
                text = re.sub(r"UNTIL=(\d{8})(?!T)", r"UNTIL=\1T235959Z", text)
            rs.rrule(rrulestr(text, dtstart=self.start))
        if rules is None:
            rs.rdate(self.start)
        for value in rdates:
            rs.rdate(self.local(value))
        if "EXDATE" in self.event:
            for value in _datetimes(self.event["EXDATE"]):
                rs.exdate(self.local(value))
        found = []
        for occurrence in islice(rs.xafter(first - self.length, inc=True), MAX_OCCURRENCES):
            if occurrence >= last:
                break
            found.append(occurrence)
        return found


def _instance(source: Any, master: _Master, begin: datetime, length: timedelta) -> str:
    event = Event()
    event.add("UID", str(source.get("UID", "")))
    if master.all_day:
        event.add("DTSTART", begin.date())
        event.add("DTEND", (begin + length).date())
    else:
        event.add("DTSTART", master.aware(begin))
        event.add("DTEND", master.aware(begin + length))
    for name in ("STATUS", "TRANSP"):
        if name in source:
            event.add(name, str(source[name]))
    calendar = Calendar()
    calendar.add("VERSION", "2.0")
    calendar.add("PRODID", "-//Karrierekrake//busy//EN")
    calendar.add_component(event)
    return calendar.to_ical().decode()


def expand(documents: list[str], start: datetime, end: datetime, tz: tzinfo) -> list[str]:
    """Occurrences overlapping [start, end) for every calendar object; overrides replace their occurrence."""
    by_uid: dict[str, list[Any]] = defaultdict(list)
    for text in documents:
        try:
            events = Calendar.from_ical(text).walk("VEVENT")
        except ValueError:
            continue
        for event in events:
            if "DTSTART" in event:
                by_uid[str(event.get("UID", ""))].append(event)
    results: list[str] = []
    for events in by_uid.values():
        masters = [e for e in events if "RECURRENCE-ID" not in e]
        overrides = [e for e in events if "RECURRENCE-ID" in e]
        replaced: set[datetime] = set()
        for override in overrides:
            replaced.add(_Master(override, tz).local(override.decoded("RECURRENCE-ID")))
        for event in masters:
            master = _Master(event, tz)
            for begin in master.occurrences(start, end):
                if begin in replaced or begin + master.length <= master.local(start) or begin >= master.local(end):
                    continue
                results.append(_instance(event, master, begin, master.length))
        for override in overrides:
            single = _Master(override, tz)
            if single.start + single.length > single.local(start) and single.start < single.local(end):
                results.append(_instance(override, single, single.start, single.length))
    return results
