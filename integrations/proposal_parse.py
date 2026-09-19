"""Natural-language employer scheduling proposal parser (DE/EN).

Understands phrases like:
  \"Dienstag oder Mittwoch zwischen 9 und 15 Uhr\"
  \"Tue/Wed 9am–3pm\"
  \"am 20.09.2026 um 14:00\"

Fail-closed on timezone ambiguity: fixed clock times without zone context are
anchored only when the caller supplies ``default_tz``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any

from integrations.calendar_timezone import (
    TimezoneAmbiguityError,
    combine_local,
    parse_iso_datetime,
    resolve_zone,
)

WEEKDAY_DE = {
    "montag": 0,
    "dienstag": 1,
    "mittwoch": 2,
    "donnerstag": 3,
    "freitag": 4,
    "samstag": 5,
    "sonntag": 6,
}
WEEKDAY_EN = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
    "mon": 0,
    "tue": 1,
    "tues": 1,
    "wed": 2,
    "thu": 3,
    "thur": 3,
    "thurs": 3,
    "fri": 4,
    "sat": 5,
    "sun": 6,
}
WEEKDAY_ALIASES = {**WEEKDAY_DE, **WEEKDAY_EN}

MONTH_DE = {
    "januar": 1,
    "februar": 2,
    "märz": 3,
    "maerz": 3,
    "april": 4,
    "mai": 5,
    "juni": 6,
    "juli": 7,
    "august": 8,
    "september": 9,
    "oktober": 10,
    "november": 11,
    "dezember": 12,
}

_WINDOW_RE = re.compile(
    r"(?:zwischen|between)\s+(\d{1,2})(?::(\d{2}))?\s*(?:uhr|h|am|pm)?"
    r"\s+(?:und|and|–|-|—)\s+(\d{1,2})(?::(\d{2}))?\s*(?:uhr|h|am|pm)?",
    re.I,
)
_RANGE_RE = re.compile(
    r"\b(\d{1,2})(?::(\d{2}))?\s*(?:uhr|h)?\s*(?:–|-|—|bis|to)\s*"
    r"(\d{1,2})(?::(\d{2}))?\s*(?:uhr|h)?",
    re.I,
)
_FIXED_DE = re.compile(
    r"(?:am\s+)?(\d{1,2})\.(\d{1,2})\.(\d{4})\s+(?:um\s+)?(\d{1,2})[:\.](\d{2})\s*(?:uhr)?",
    re.I,
)
_FIXED_LONG_DE = re.compile(
    r"(?:montag|dienstag|mittwoch|donnerstag|freitag|samstag|sonntag)[,\s]+"
    r"(\d{1,2})\.\s*"
    r"(januar|februar|märz|maerz|april|mai|juni|juli|august|september|oktober|november|dezember)\s+"
    r"(\d{4})[,\s]+(\d{1,2})[:\.](\d{2})",
    re.I,
)
_ISO_FIXED = re.compile(
    r"\b(\d{4}-\d{2}-\d{2})[T\s](\d{2}:\d{2}(?::\d{2})?(?:Z|[+-]\d{2}:?\d{2})?)\b"
)
_ONSITE_RE = re.compile(
    r"\b(vor\s*ort|onsite|on-site|persönlich|persoenlich|in\s+unserem\s+büro)\b", re.I
)
_REMOTE_RE = re.compile(
    r"\b(remote|online|video|teams|zoom|google\s*meet|telefon|phone|virtuell)\b", re.I
)


@dataclass(frozen=True)
class ProposalWindow:
    """A flexible day + local time window (timezone-aware bounds when resolved)."""

    weekdays: tuple[int, ...]
    start_time: time
    end_time: time
    fixed_dates: tuple[date, ...] = ()
    modality: str = "remote"
    raw_text: str = ""
    timezone: str = "Europe/Berlin"
    ambiguous: bool = False
    ambiguity_reason: str = ""

    def is_usable(self) -> bool:
        return (
            not self.ambiguous
            and (bool(self.weekdays) or bool(self.fixed_dates))
            and self.start_time < self.end_time
        )


@dataclass
class ParseResult:
    windows: list[ProposalWindow] = field(default_factory=list)
    fixed_slots: list[datetime] = field(default_factory=list)
    modality: str = "unknown"
    raw_text: str = ""
    errors: list[str] = field(default_factory=list)
    used_dateparser: bool = False

    @property
    def ok(self) -> bool:
        return (bool(self.windows) or bool(self.fixed_slots)) and not any(
            e.startswith("ambiguous") or e.startswith("timezone") for e in self.errors
        )


def _clock(h: int, m: int = 0) -> time:
    h = max(0, min(23, int(h)))
    m = max(0, min(59, int(m)))
    return time(h, m)


def _extract_weekdays(text: str) -> list[int]:
    lowered = text.lower()
    found: list[int] = []
    for name, idx in sorted(WEEKDAY_ALIASES.items(), key=lambda x: -len(x[0])):
        if re.search(rf"\b{re.escape(name)}\b", lowered):
            if idx not in found:
                found.append(idx)
    return found


def _extract_modality(text: str) -> str:
    if _ONSITE_RE.search(text):
        return "onsite"
    if _REMOTE_RE.search(text):
        return "remote"
    return "unknown"


def _extract_time_window(text: str) -> tuple[time, time] | None:
    for rx in (_WINDOW_RE, _RANGE_RE):
        m = rx.search(text)
        if not m:
            continue
        sh, sm, eh, em = m.group(1), m.group(2), m.group(3), m.group(4)
        start = _clock(int(sh), int(sm or 0))
        end = _clock(int(eh), int(em or 0))
        if start < end:
            return start, end
    return None


def _upcoming_weekdays(ref: date, weekdays: list[int], *, weeks: int = 2) -> list[date]:
    out: list[date] = []
    for i in range(0, 7 * max(1, weeks)):
        d = ref + timedelta(days=i)
        if d.weekday() in weekdays:
            out.append(d)
    return out


def _try_dateparser(text: str, *, default_tz: str, reference: datetime) -> datetime | None:
    try:
        import dateparser
    except ImportError:
        return None
    settings = {
        "TIMEZONE": default_tz,
        "RETURN_AS_TIMEZONE_AWARE": True,
        "PREFER_DATES_FROM": "future",
        "RELATIVE_BASE": reference.replace(tzinfo=None),
    }
    dt = dateparser.parse(text, languages=["de", "en"], settings=settings)
    if dt is None:
        return None
    if dt.tzinfo is None:
        raise TimezoneAmbiguityError("dateparser_naive_result")
    return dt


def parse_scheduling_proposal(
    text: str,
    *,
    default_tz: str = "Europe/Berlin",
    reference: datetime | date | None = None,
    horizon_weeks: int = 2,
) -> ParseResult:
    """Parse employer free-text into windows and/or fixed slots."""
    raw = (text or "").strip()
    result = ParseResult(raw_text=raw, modality=_extract_modality(raw))
    if not raw:
        result.errors.append("empty_proposal")
        return result

    try:
        resolve_zone(default_tz)
    except TimezoneAmbiguityError:
        result.errors.append(f"timezone_unknown:{default_tz}")
        return result

    if reference is None:
        ref_dt = datetime.now(resolve_zone(default_tz))
    elif isinstance(reference, datetime):
        ref_dt = (
            reference
            if reference.tzinfo
            else combine_local(reference.date(), reference.time(), default_tz)
        )
    else:
        ref_dt = combine_local(reference, time(12, 0), default_tz)
    ref_day = ref_dt.date()

    for m in _ISO_FIXED.finditer(raw):
        iso = f"{m.group(1)}T{m.group(2)}"
        try:
            dt = parse_iso_datetime(iso, default_tz=default_tz)
        except TimezoneAmbiguityError:
            result.errors.append("ambiguous_timezone:iso_naive")
            continue
        if dt:
            result.fixed_slots.append(dt)

    for m in _FIXED_DE.finditer(raw):
        d = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        try:
            result.fixed_slots.append(
                combine_local(d, _clock(int(m.group(4)), int(m.group(5))), default_tz)
            )
        except TimezoneAmbiguityError as exc:
            result.errors.append(str(exc))

    for m in _FIXED_LONG_DE.finditer(raw):
        month = MONTH_DE.get(m.group(2).lower())
        if not month:
            continue
        d = date(int(m.group(3)), month, int(m.group(1)))
        try:
            result.fixed_slots.append(
                combine_local(d, _clock(int(m.group(4)), int(m.group(5))), default_tz)
            )
        except TimezoneAmbiguityError as exc:
            result.errors.append(str(exc))

    weekdays = _extract_weekdays(raw)
    window = _extract_time_window(raw)

    if weekdays and window:
        start_t, end_t = window
        dates = tuple(_upcoming_weekdays(ref_day, weekdays, weeks=horizon_weeks))
        result.windows.append(
            ProposalWindow(
                weekdays=tuple(weekdays),
                start_time=start_t,
                end_time=end_t,
                fixed_dates=dates,
                modality=result.modality if result.modality != "unknown" else "remote",
                raw_text=raw,
                timezone=default_tz,
            )
        )
    elif weekdays and not window:
        result.windows.append(
            ProposalWindow(
                weekdays=tuple(weekdays),
                start_time=time(9, 0),
                end_time=time(17, 0),
                fixed_dates=tuple(_upcoming_weekdays(ref_day, weekdays, weeks=horizon_weeks)),
                modality=result.modality if result.modality != "unknown" else "remote",
                raw_text=raw,
                timezone=default_tz,
            )
        )
    elif window and not weekdays and not result.fixed_slots:
        start_t, end_t = window
        result.windows.append(
            ProposalWindow(
                weekdays=(),
                start_time=start_t,
                end_time=end_t,
                modality=result.modality,
                raw_text=raw,
                timezone=default_tz,
                ambiguous=True,
                ambiguity_reason="time_window_without_weekdays",
            )
        )
        result.errors.append("ambiguous:time_window_without_weekdays")

    if not result.fixed_slots and not any(w.is_usable() for w in result.windows):
        try:
            parsed = _try_dateparser(raw, default_tz=default_tz, reference=ref_dt)
            if parsed is not None:
                result.fixed_slots.append(parsed)
                result.used_dateparser = True
        except TimezoneAmbiguityError as exc:
            result.errors.append(str(exc))
        except Exception:
            result.errors.append("dateparser_failed")

    if not result.fixed_slots and not any(w.is_usable() for w in result.windows):
        if "empty_proposal" not in result.errors:
            result.errors.append("unparseable_proposal")

    return result


def parse_result_to_dict(result: ParseResult) -> dict[str, Any]:
    return {
        "ok": result.ok,
        "modality": result.modality,
        "raw_text": result.raw_text,
        "errors": list(result.errors),
        "used_dateparser": result.used_dateparser,
        "fixed_slots": [dt.isoformat() for dt in result.fixed_slots],
        "windows": [
            {
                "weekdays": list(w.weekdays),
                "start_time": w.start_time.strftime("%H:%M"),
                "end_time": w.end_time.strftime("%H:%M"),
                "fixed_dates": [d.isoformat() for d in w.fixed_dates],
                "modality": w.modality,
                "timezone": w.timezone,
                "ambiguous": w.ambiguous,
                "ambiguity_reason": w.ambiguity_reason,
                "usable": w.is_usable(),
            }
            for w in result.windows
        ],
    }
