"""ICS export helpers — adapted from PBP ics_service.py (MIT).

Times are written as UTC (Z). Callers must pass timezone-aware ISO starts;
naive values are anchored to UTC explicitly (never silent local guess).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable


def ics_escape(text: Any) -> str:
    value = "" if text is None else str(text)
    return (
        value.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
        .replace("\r", "")
    )


def ics_fold(line: str) -> str:
    """RFC 5545 line folding at 75 octets (approx chars for ASCII)."""
    if len(line) <= 75:
        return line
    parts = [line[:75]]
    rest = line[75:]
    while rest:
        parts.append(" " + rest[:74])
        rest = rest[74:]
    return "\r\n".join(parts)


def _fmt_dt(iso_str: str | None) -> str | None:
    if not iso_str:
        return None
    raw = str(iso_str).strip()
    try:
        if raw.endswith("Z"):
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        else:
            dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    except ValueError:
        return None


def build_meetings_ics(meetings: Iterable[dict[str, Any]], *, calendar_name: str = "Karrierekrake") -> str:
    """Build a VCALENDAR from meeting dicts (scheduled_at, title, description, uid)."""
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:-//{ics_escape(calendar_name)}//DE",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]
    count = 0
    for m in meetings:
        start = _fmt_dt(m.get("scheduled_at") or m.get("start"))
        if not start:
            continue
        uid = ics_escape(m.get("uid") or m.get("id") or f"kk-{count}@local")
        # Availability-safe default title — never leak private calendar titles outward.
        summary = ics_escape(m.get("title") or "Interview (Karrierekrake)")
        description = ics_escape(m.get("description") or "")
        lines.append("BEGIN:VEVENT")
        lines.append(ics_fold(f"UID:{uid}"))
        lines.append(ics_fold(f"DTSTAMP:{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"))
        lines.append(ics_fold(f"DTSTART:{start}"))
        end = _fmt_dt(m.get("end"))
        if end:
            lines.append(ics_fold(f"DTEND:{end}"))
        lines.append(ics_fold(f"SUMMARY:{summary}"))
        if description:
            lines.append(ics_fold(f"DESCRIPTION:{description}"))
        location = ics_escape(m.get("location") or "")
        if location:
            lines.append(ics_fold(f"LOCATION:{location}"))
        lines.append("END:VEVENT")
        count += 1
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"
