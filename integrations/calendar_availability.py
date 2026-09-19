"""Calendar availability + timezone-aware scheduling constraints (PR31).

Collision logic adapted from PBP termin_dubletten ideas (MIT).
Google FreeBusy is optional; never exposes private event titles to employers.

All datetimes are timezone-aware. Naive inputs fail closed unless a default
zone is provided explicitly by the caller.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any, Iterable

from core.scheduling_preferences import (
    DEFAULT_TIMEZONE,
    SchedulingPreferences,
    empty_scheduling_preferences,
)
from integrations.calendar_timezone import (
    TimezoneAmbiguityError,
    combine_local,
    ensure_aware,
    isoformat_z,
    parse_iso_datetime,
    resolve_zone,
    to_utc,
    to_zone,
)

try:
    import holidays as _holidays_lib
except ImportError:  # pragma: no cover
    _holidays_lib = None


@dataclass(frozen=True)
class TimeWindow:
    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        if self.start.tzinfo is None or self.end.tzinfo is None:
            raise TimezoneAmbiguityError("TimeWindow requires aware datetimes")
        if self.end <= self.start:
            raise ValueError("TimeWindow end must be after start")

    def as_utc(self) -> "TimeWindow":
        return TimeWindow(to_utc(self.start), to_utc(self.end))


@dataclass(frozen=True)
class CollisionResult:
    conflicts: tuple[str, ...]
    outside_working_hours: bool
    ok: bool
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class ConstraintContext:
    """Resolved constraint inputs for one evaluation."""

    prefs: SchedulingPreferences
    modality: str = "remote"
    busy: tuple[TimeWindow, ...] = ()
    existing_meetings: tuple[dict[str, Any], ...] = ()
    holiday_dates: frozenset[date] = field(default_factory=frozenset)


def parse_working_hours(spec: str) -> tuple[time, time]:
    """Parse '09:00-17:00' style config."""
    raw = (spec or "09:00-17:00").strip()
    try:
        left, _, right = raw.partition("-")
        sh, sm = left.strip().split(":")[:2]
        eh, em = right.strip().split(":")[:2]
        return time(int(sh), int(sm)), time(int(eh), int(em))
    except Exception:
        return time(9, 0), time(17, 0)


def parse_multi_windows(spec: str) -> list[tuple[time, time]]:
    """Parse comma-separated HH:MM-HH:MM windows."""
    out: list[tuple[time, time]] = []
    for part in (spec or "").split(","):
        part = part.strip()
        if not part:
            continue
        start, end = parse_working_hours(part)
        if start < end:
            out.append((start, end))
    return out


def overlaps(a: TimeWindow, b: TimeWindow) -> bool:
    au, bu = a.as_utc(), b.as_utc()
    return au.start < bu.end and bu.start < au.end


def expand_with_buffers(
    window: TimeWindow,
    *,
    before: int,
    after: int,
    travel: int = 0,
) -> TimeWindow:
    """Expand interview window by before/after + optional onsite travel buffers."""
    start = window.start - timedelta(minutes=max(0, before) + max(0, travel))
    end = window.end + timedelta(minutes=max(0, after) + max(0, travel))
    return TimeWindow(ensure_aware(start), ensure_aware(end))


def load_holiday_dates(
    *,
    country: str,
    years: Iterable[int],
    enabled: bool,
) -> frozenset[date]:
    if not enabled:
        return frozenset()
    if _holidays_lib is None:
        return frozenset()
    try:
        cal = _holidays_lib.country_holidays(country, years=list(years))
        return frozenset(cal.keys())
    except Exception:
        return frozenset()


def is_weekend(day: date) -> bool:
    return day.weekday() >= 5


def within_working_hours(
    local_start: datetime, local_end: datetime, prefs: SchedulingPreferences
) -> bool:
    wh_start, wh_end = parse_working_hours(prefs.working_hours)
    t0 = local_start.timetz().replace(tzinfo=None)
    t1 = local_end.timetz().replace(tzinfo=None)
    return wh_start <= t0 and t1 <= wh_end


def weekday_allowed(day: date, prefs: SchedulingPreferences) -> bool:
    if day.weekday() in prefs.working_weekdays:
        return True
    if prefs.allow_weekends and is_weekend(day):
        return True
    return False


def check_constraints(window: TimeWindow, ctx: ConstraintContext) -> CollisionResult:
    """Evaluate buffers, working hours, weekend/holiday, busy, meeting collisions."""
    prefs = ctx.prefs
    zone = resolve_zone(prefs.timezone)
    local_start = to_zone(window.start, zone)
    local_end = to_zone(window.end, zone)
    reasons: list[str] = []
    conflicts: list[str] = []

    if local_start.date() != local_end.date():
        conflicts.append("spans_midnight")
        reasons.append("Interview darf nicht über Mitternacht gehen")

    if not weekday_allowed(local_start.date(), prefs):
        conflicts.append("weekday_blocked")
        reasons.append("Wochentag außerhalb der erlaubten Arbeitstage")

    if prefs.respect_holidays and local_start.date() in ctx.holiday_dates:
        conflicts.append("holiday")
        reasons.append("Feiertag (optional aktiv)")

    outside = not within_working_hours(local_start, local_end, prefs)
    if outside:
        reasons.append("Außerhalb der Arbeitszeiten")

    travel = prefs.effective_onsite_buffer(modality=ctx.modality)
    padded = expand_with_buffers(
        window,
        before=prefs.buffer_before_minutes,
        after=prefs.buffer_after_minutes,
        travel=travel,
    )

    for b in ctx.busy:
        if overlaps(padded, b):
            conflicts.append("calendar_busy")
            reasons.append("Kalender belegt (FreeBusy)")
            break

    duration_fallback = prefs.interview_duration_minutes
    for m in ctx.existing_meetings:
        other_start = parse_iso_datetime(
            str(m.get("scheduled_at") or m.get("start") or ""),
            default_tz=prefs.timezone,
        )
        if not other_start:
            continue
        other_end_raw = m.get("end")
        if other_end_raw:
            other_end = parse_iso_datetime(str(other_end_raw), default_tz=prefs.timezone)
            if not other_end:
                other_end = other_start + timedelta(minutes=duration_fallback)
        else:
            other_end = other_start + timedelta(minutes=duration_fallback)
        other = TimeWindow(other_start, other_end)
        if overlaps(padded, other):
            conflicts.append(f"meeting_collision:{m.get('id') or 'existing'}")
            reasons.append("Kollision mit bekanntem Interview")

    if prefs.explicit_availability:
        fits = False
        for avail in prefs.explicit_availability:
            a0 = parse_iso_datetime(avail.start, default_tz=prefs.timezone)
            a1 = parse_iso_datetime(avail.end, default_tz=prefs.timezone)
            if not a0 or not a1:
                continue
            if a0 <= padded.start and padded.end <= a1:
                fits = True
                break
        if not fits:
            conflicts.append("outside_explicit_availability")
            reasons.append("Außerhalb der expliziten Verfügbarkeit")

    ok = not conflicts and not outside
    return CollisionResult(tuple(conflicts), outside, ok, tuple(dict.fromkeys(reasons)))


def check_interview_slot(
    proposed_start: str | datetime,
    *,
    duration_minutes: int | None = None,
    busy: Iterable[TimeWindow] = (),
    working_hours: str = "09:00-17:00",
    existing_meetings: Iterable[dict[str, Any]] = (),
    timezone_name: str = DEFAULT_TIMEZONE,
    prefs: SchedulingPreferences | None = None,
    modality: str = "remote",
    holiday_dates: Iterable[date] = (),
) -> CollisionResult:
    """Backward-compatible collision check with full timezone-aware constraints."""
    if prefs is not None:
        base = prefs
    else:
        base = empty_scheduling_preferences()
        base.working_hours = working_hours
        base.timezone = timezone_name
    if duration_minutes is not None:
        base.interview_duration_minutes = int(duration_minutes)

    try:
        if isinstance(proposed_start, datetime):
            start = ensure_aware(proposed_start, default_tz=base.timezone)
        else:
            start = parse_iso_datetime(str(proposed_start), default_tz=base.timezone)
            if start is None:
                return CollisionResult(
                    ("invalid_datetime",), False, False, ("Ungültige Zeitangabe",)
                )
    except TimezoneAmbiguityError:
        return CollisionResult(
            ("timezone_ambiguity",),
            False,
            False,
            ("Zeitzonenambiguität — kein Slot",),
        )

    end = start + timedelta(minutes=base.interview_duration_minutes)
    window = TimeWindow(start, end)
    ctx = ConstraintContext(
        prefs=base,
        modality=modality,
        busy=tuple(busy),
        existing_meetings=tuple(existing_meetings),
        holiday_dates=frozenset(holiday_dates),
    )
    return check_constraints(window, ctx)


def availability_reply_slots(
    *,
    working_hours: str,
    busy: Iterable[TimeWindow],
    day_iso_dates: list[str],
    slot_minutes: int = 60,
    timezone_name: str = "UTC",
) -> list[str]:
    """Return generic availability strings (no private event titles)."""
    prefs = empty_scheduling_preferences()
    prefs.working_hours = working_hours
    prefs.timezone = timezone_name
    prefs.interview_duration_minutes = slot_minutes
    wh_start, wh_end = parse_working_hours(working_hours)
    suggestions: list[str] = []
    busy_list = list(busy)
    zone = resolve_zone(timezone_name)

    for day in day_iso_dates:
        try:
            d = date.fromisoformat(day)
        except ValueError:
            continue
        try:
            cursor = combine_local(d, wh_start, zone)
            day_end = combine_local(d, wh_end, zone)
        except TimezoneAmbiguityError:
            continue
        while cursor + timedelta(minutes=slot_minutes) <= day_end:
            end = cursor + timedelta(minutes=slot_minutes)
            win = TimeWindow(cursor, end)
            ctx = ConstraintContext(prefs=prefs, busy=tuple(busy_list))
            result = check_constraints(win, ctx)
            if result.ok:
                local_c = to_zone(cursor, zone)
                local_e = to_zone(end, zone)
                suggestions.append(
                    f"{day} {local_c.strftime('%H:%M')}–{local_e.strftime('%H:%M')} "
                    f"{timezone_name} (verfügbar)"
                )
            cursor = end
            if len(suggestions) >= 6:
                return suggestions
    return suggestions


def iter_candidate_starts(
    day: date,
    window_start: time,
    window_end: time,
    *,
    duration_minutes: int,
    step_minutes: int,
    tz: str,
) -> list[datetime]:
    """Generate aware candidate start times inside a local window."""
    out: list[datetime] = []
    try:
        cursor = combine_local(day, window_start, tz)
        limit = combine_local(day, window_end, tz)
    except TimezoneAmbiguityError:
        return out
    step = timedelta(minutes=max(5, step_minutes))
    dur = timedelta(minutes=max(15, duration_minutes))
    while cursor + dur <= limit:
        out.append(cursor)
        cursor = cursor + step
    return out


def public_busy_marker(window: TimeWindow) -> dict[str, str]:
    """Busy interval safe to share externally (no titles)."""
    return {"start": isoformat_z(window.start), "end": isoformat_z(window.end), "busy": "true"}
