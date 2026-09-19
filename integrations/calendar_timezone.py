"""Timezone-aware datetime helpers for calendar scheduling.

All public APIs return aware datetimes. Naive inputs are rejected or
explicitly anchored to a named zone — never silently treated as local wall
clock without a zone. Ambiguous DST folds fail closed.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class TimezoneAmbiguityError(ValueError):
    """Raised when a wall time is ambiguous or missing timezone context."""


def resolve_zone(name: str | None) -> ZoneInfo:
    raw = (name or "Europe/Berlin").strip() or "Europe/Berlin"
    try:
        return ZoneInfo(raw)
    except ZoneInfoNotFoundError as exc:
        raise TimezoneAmbiguityError(f"unknown_timezone:{raw}") from exc


def ensure_aware(dt: datetime, *, default_tz: str | ZoneInfo | None = None) -> datetime:
    """Return timezone-aware datetime.

    If ``dt`` is naive and ``default_tz`` is given, attach that zone (wall time).
    If naive and no default — raise (fail closed).
    """
    if dt.tzinfo is not None:
        return dt
    if default_tz is None:
        raise TimezoneAmbiguityError("naive_datetime_without_timezone")
    zone = default_tz if isinstance(default_tz, ZoneInfo) else resolve_zone(str(default_tz))
    return dt.replace(tzinfo=zone)


def to_utc(dt: datetime) -> datetime:
    return ensure_aware(dt, default_tz=timezone.utc).astimezone(timezone.utc)


def to_zone(dt: datetime, tz: str | ZoneInfo) -> datetime:
    zone = tz if isinstance(tz, ZoneInfo) else resolve_zone(tz)
    return ensure_aware(dt, default_tz=zone).astimezone(zone)


def parse_iso_datetime(
    value: str | datetime | None,
    *,
    default_tz: str | None = None,
    allow_naive: bool = False,
) -> datetime | None:
    """Parse ISO-8601 / RFC3339 into an aware datetime.

    ``Z`` and offsets are respected. Naive strings require ``default_tz``.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            return value
        if allow_naive and default_tz:
            return ensure_aware(value, default_tz=default_tz)
        raise TimezoneAmbiguityError("naive_datetime_without_timezone")

    raw = str(value).strip()
    if not raw:
        return None
    try:
        if raw.endswith("Z"):
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if dt.tzinfo is not None:
        return dt
    if default_tz:
        return ensure_aware(dt, default_tz=default_tz)
    if allow_naive:
        raise TimezoneAmbiguityError("naive_datetime_without_timezone")
    return None


def combine_local(day: date, clock: time, tz: str | ZoneInfo) -> datetime:
    """Combine local calendar date + clock into an aware datetime.

    On DST fold (ambiguous) or gap (non-existent), raise TimezoneAmbiguityError
    instead of guessing.
    """
    zone = tz if isinstance(tz, ZoneInfo) else resolve_zone(tz)
    naive = datetime.combine(day, clock)
    try:
        dt0 = naive.replace(tzinfo=zone)
        roundtrip = dt0.astimezone(timezone.utc).astimezone(zone)
        if roundtrip.replace(tzinfo=None) != naive:
            raise TimezoneAmbiguityError(f"nonexistent_local_time:{naive.isoformat()}")
        dt1 = naive.replace(tzinfo=zone, fold=1)
        if dt0.utcoffset() != dt1.utcoffset():
            raise TimezoneAmbiguityError(f"ambiguous_local_time:{naive.isoformat()}")
        return dt0
    except TimezoneAmbiguityError:
        raise
    except Exception as exc:  # pragma: no cover — defensive
        raise TimezoneAmbiguityError(f"invalid_local_time:{naive.isoformat()}") from exc


def add_minutes(dt: datetime, minutes: int) -> datetime:
    aware = ensure_aware(dt, default_tz=timezone.utc)
    return aware + timedelta(minutes=int(minutes))


def isoformat_z(dt: datetime) -> str:
    """UTC ISO string with Z suffix (stable for persistence / ICS)."""
    return to_utc(dt).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def isoformat_offset(dt: datetime) -> str:
    aware = ensure_aware(dt, default_tz=timezone.utc).replace(microsecond=0)
    return aware.isoformat()


def same_instant(a: datetime, b: datetime) -> bool:
    return to_utc(a) == to_utc(b)


def as_busy_dict(start: datetime, end: datetime, *, source: str = "busy") -> dict[str, Any]:
    """Public busy interval — never includes private event titles."""
    return {
        "start": isoformat_z(start),
        "end": isoformat_z(end),
        "source": source,
    }
