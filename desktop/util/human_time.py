"""Human-friendly datetime formatting for production UI (keep ISO internally)."""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo


def _parse_ts(value: str | datetime | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        raw = str(value).strip()
        if not raw or raw == "—":
            return None
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
                try:
                    dt = datetime.strptime(raw[:19], fmt)
                    break
                except ValueError:
                    continue
            else:
                return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def format_human_datetime(
    value: str | datetime | None,
    *,
    lang: str = "de",
    tz_name: str | None = None,
) -> str:
    """Localized relative/absolute clock for dashboard / lists."""
    dt = _parse_ts(value)
    if dt is None:
        return "—"
    try:
        local_tz = ZoneInfo(tz_name) if tz_name else datetime.now().astimezone().tzinfo
    except Exception:
        local_tz = datetime.now().astimezone().tzinfo
    local = dt.astimezone(local_tz) if local_tz else dt
    now = datetime.now(tz=local.tzinfo)
    same_day = local.date() == now.date()
    yesterday = (now.date().toordinal() - local.date().toordinal()) == 1
    time_part = local.strftime("%H:%M")
    if lang.startswith("de"):
        if same_day:
            return f"Heute, {time_part} Uhr"
        if yesterday:
            return f"Gestern, {time_part} Uhr"
        return f"{local.strftime('%d.%m.%Y')}, {time_part} Uhr"
    if same_day:
        return f"Today, {time_part}"
    if yesterday:
        return f"Yesterday, {time_part}"
    return f"{local.strftime('%Y-%m-%d')}, {time_part}"


def format_human_date_short(value: str | datetime | None, *, lang: str = "de") -> str:
    dt = _parse_ts(value)
    if dt is None:
        return "—"
    local = dt.astimezone()
    now = datetime.now(tz=local.tzinfo)
    if local.date() == now.date():
        return local.strftime("%H:%M")
    if (now.date().toordinal() - local.date().toordinal()) == 1:
        return "Gestern" if lang.startswith("de") else "Yesterday"
    if lang.startswith("de"):
        return local.strftime("%d. %b")
    return local.strftime("%b %d")
