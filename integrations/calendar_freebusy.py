"""Google Calendar FreeBusy client + mockable provider (PR31).

Never exposes private event titles — only opaque busy intervals.
Live API is optional and gated; CI uses MockFreeBusyProvider.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from integrations.calendar_availability import TimeWindow
from integrations.calendar_timezone import ensure_aware, isoformat_z, parse_iso_datetime, to_utc

logger = logging.getLogger("karrierekrake.calendar")

# Prefer freebusy over calendar.readonly (PR43 least privilege).
# calendar.readonly remains defined only as a forbidden-comparison constant.
CALENDAR_READONLY_SCOPE = "https://www.googleapis.com/auth/calendar.readonly"
CALENDAR_FREEBUSY_SCOPE = "https://www.googleapis.com/auth/calendar.freebusy"

# Production OAuth for FreeBusy: integrations.google_oauth.Feature.CALENDAR_SLOT_FINDING
# → authorize via integrations.gmail_auth.authorize_calendar_freebusy (shared token).


@dataclass(frozen=True)
class FreeBusyQuery:
    time_min: datetime
    time_max: datetime
    calendar_ids: tuple[str, ...] = ("primary",)


class FreeBusyProvider(Protocol):
    def query(self, q: FreeBusyQuery) -> list[TimeWindow]:
        """Return busy windows (no titles)."""


class MockFreeBusyProvider:
    """Deterministic busy intervals for tests / offline."""

    def __init__(self, busy: list[TimeWindow] | None = None) -> None:
        self._busy = list(busy or [])

    def set_busy(self, busy: list[TimeWindow]) -> None:
        self._busy = list(busy)

    def query(self, q: FreeBusyQuery) -> list[TimeWindow]:
        tmin = to_utc(ensure_aware(q.time_min, default_tz="UTC"))
        tmax = to_utc(ensure_aware(q.time_max, default_tz="UTC"))
        out: list[TimeWindow] = []
        for b in self._busy:
            bs = to_utc(b.start)
            be = to_utc(b.end)
            if bs < tmax and tmin < be:
                out.append(TimeWindow(start=bs, end=be))
        return out


class StaticDictFreeBusyProvider:
    """Busy from plain dicts ``{start, end}`` — titles ignored if present."""

    def __init__(self, intervals: list[dict[str, Any]] | None = None) -> None:
        self._intervals = list(intervals or [])

    def query(self, q: FreeBusyQuery) -> list[TimeWindow]:
        windows: list[TimeWindow] = []
        for item in self._intervals:
            start = parse_iso_datetime(item.get("start"), default_tz="UTC")
            end = parse_iso_datetime(item.get("end"), default_tz="UTC")
            if not start or not end or end <= start:
                continue
            windows.append(TimeWindow(start=to_utc(start), end=to_utc(end)))
        return MockFreeBusyProvider(windows).query(q)


class GoogleFreeBusyProvider:
    """Thin Google Calendar FreeBusy wrapper. Requires injected service."""

    def __init__(self, service: Any) -> None:
        self._service = service

    def query(self, q: FreeBusyQuery) -> list[TimeWindow]:
        body = {
            "timeMin": isoformat_z(q.time_min),
            "timeMax": isoformat_z(q.time_max),
            "items": [{"id": cid} for cid in q.calendar_ids],
        }
        try:
            resp = self._service.freebusy().query(body=body).execute()
        except Exception as exc:
            logger.error("FreeBusy query failed: %s", type(exc).__name__)
            raise
        windows: list[TimeWindow] = []
        calendars = (resp or {}).get("calendars") or {}
        for _cal_id, payload in calendars.items():
            for block in payload.get("busy") or []:
                start = parse_iso_datetime(block.get("start"), default_tz="UTC")
                end = parse_iso_datetime(block.get("end"), default_tz="UTC")
                if start and end and end > start:
                    windows.append(TimeWindow(start=to_utc(start), end=to_utc(end)))
        return windows


def merge_busy(*groups: list[TimeWindow]) -> list[TimeWindow]:
    """Merge and coalesce overlapping busy windows (UTC-normalized)."""
    items = sorted(
        (TimeWindow(to_utc(w.start), to_utc(w.end)) for g in groups for w in g),
        key=lambda w: w.start,
    )
    if not items:
        return []
    merged: list[TimeWindow] = [items[0]]
    for w in items[1:]:
        last = merged[-1]
        if w.start <= last.end:
            merged[-1] = TimeWindow(last.start, max(last.end, w.end))
        else:
            merged.append(w)
    return merged


def busy_as_public_dicts(windows: list[TimeWindow]) -> list[dict[str, str]]:
    """Serialize busy intervals without titles."""
    return [
        {"start": isoformat_z(w.start), "end": isoformat_z(w.end), "source": "freebusy"}
        for w in windows
    ]
