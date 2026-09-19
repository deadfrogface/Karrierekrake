"""Versioned scheduling preferences for the Calendar Scheduling Engine (PR31).

Preferences are the source of truth for timezone, working hours, buffers, and
ranking knobs. Schema and ranking versions are independent so ranking can be
rolled back without discarding user preference data.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from typing import Any

# Bump when persisted preference shape changes (migration / dual-read).
SCHEDULING_PREFS_SCHEMA_VERSION = 1
# Independent of schema — bump when ranking weights/order change; revertible.
RANKING_VERSION = 1

DEFAULT_TIMEZONE = "Europe/Berlin"
DEFAULT_WORKING_HOURS = "09:00-17:00"
DEFAULT_WEEKDAYS: tuple[int, ...] = (0, 1, 2, 3, 4)  # Mon–Fri (datetime.weekday)


@dataclass
class ExplicitAvailabilityWindow:
    """User-declared free window in the configured timezone (ISO local or aware)."""

    start: str
    end: str
    label: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExplicitAvailabilityWindow":
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})


@dataclass
class SchedulingPreferences:
    """User schedule preferences — versioned, rollback-safe."""

    schema_version: int = SCHEDULING_PREFS_SCHEMA_VERSION
    ranking_version: int = RANKING_VERSION

    timezone: str = DEFAULT_TIMEZONE
    working_hours: str = DEFAULT_WORKING_HOURS
    # datetime.weekday integers: 0=Mon … 6=Sun
    working_weekdays: list[int] = field(default_factory=lambda: list(DEFAULT_WEEKDAYS))

    interview_duration_minutes: int = 60
    buffer_before_minutes: int = 15
    buffer_after_minutes: int = 15
    # Onsite only — must be user-configured; never invent travel time from maps.
    onsite_travel_buffer_minutes: int = 0
    slot_step_minutes: int = 30
    max_ranked_slots: int = 5

    allow_weekends: bool = False
    respect_holidays: bool = False  # optional; off by default
    holiday_country: str = "DE"

    # Preferred sub-windows inside working hours, e.g. "09:00-12:00,14:00-16:00"
    preferred_windows: str = ""
    explicit_availability: list[ExplicitAvailabilityWindow] = field(default_factory=list)

    # Feature gates
    calendar_freebusy_enabled: bool = False
    # Calendar writes always need explicit approval; this only enables the write path.
    allow_calendar_write: bool = False

    def __post_init__(self) -> None:
        self.timezone = (self.timezone or DEFAULT_TIMEZONE).strip() or DEFAULT_TIMEZONE
        self.working_hours = (self.working_hours or DEFAULT_WORKING_HOURS).strip()
        self.working_weekdays = sorted(
            {int(d) for d in (self.working_weekdays or list(DEFAULT_WEEKDAYS)) if 0 <= int(d) <= 6}
        ) or list(DEFAULT_WEEKDAYS)
        self.interview_duration_minutes = max(15, int(self.interview_duration_minutes or 60))
        self.buffer_before_minutes = max(0, int(self.buffer_before_minutes or 0))
        self.buffer_after_minutes = max(0, int(self.buffer_after_minutes or 0))
        self.onsite_travel_buffer_minutes = max(0, int(self.onsite_travel_buffer_minutes or 0))
        self.slot_step_minutes = max(5, int(self.slot_step_minutes or 30))
        self.max_ranked_slots = max(1, min(20, int(self.max_ranked_slots or 5)))
        self.holiday_country = (self.holiday_country or "DE").strip().upper()[:2] or "DE"
        if isinstance(self.explicit_availability, list):
            normalized: list[ExplicitAvailabilityWindow] = []
            for item in self.explicit_availability:
                if isinstance(item, ExplicitAvailabilityWindow):
                    normalized.append(item)
                elif isinstance(item, dict):
                    normalized.append(ExplicitAvailabilityWindow.from_dict(item))
            self.explicit_availability = normalized

    def effective_onsite_buffer(self, *, modality: str) -> int:
        """Travel buffer applies only for onsite; remote/hybrid get 0 unless configured elsewhere."""
        mode = (modality or "remote").strip().lower()
        if mode == "onsite":
            return self.onsite_travel_buffer_minutes
        return 0

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["explicit_availability"] = [w.to_dict() for w in self.explicit_availability]
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "SchedulingPreferences":
        if not data:
            return empty_scheduling_preferences()
        known = {f.name for f in fields(cls)}
        raw = {k: v for k, v in data.items() if k in known}
        prefs = cls(**raw)
        return migrate_scheduling_preferences(prefs)

    def with_ranking_version(self, version: int) -> "SchedulingPreferences":
        """Return a copy pinned to an older ranking version (rollback)."""
        data = self.to_dict()
        data["ranking_version"] = int(version)
        return SchedulingPreferences.from_dict(data)


def empty_scheduling_preferences() -> SchedulingPreferences:
    return SchedulingPreferences()


def migrate_scheduling_preferences(prefs: SchedulingPreferences) -> SchedulingPreferences:
    """Forward-migrate older schema versions; never invent new availability."""
    if prefs.schema_version < 1:
        prefs.schema_version = 1
    if prefs.schema_version > SCHEDULING_PREFS_SCHEMA_VERSION:
        prefs.schema_version = SCHEDULING_PREFS_SCHEMA_VERSION
    if prefs.ranking_version < 1:
        prefs.ranking_version = RANKING_VERSION
    return prefs


def preferences_from_settings(
    *,
    working_hours: str = DEFAULT_WORKING_HOURS,
    timezone: str = DEFAULT_TIMEZONE,
    calendar_freebusy_enabled: bool = False,
    telephone_availability: str = "",
    raw: dict[str, Any] | None = None,
    interview_duration_minutes: int = 60,
    buffer_before_minutes: int = 15,
    buffer_after_minutes: int = 15,
    onsite_travel_buffer_minutes: int = 0,
    allow_weekends: bool = False,
    respect_holidays: bool = False,
    holiday_country: str = "DE",
    preferred_windows: str = "",
    slot_step_minutes: int = 30,
    max_ranked_slots: int = 5,
    allow_calendar_write: bool = False,
) -> SchedulingPreferences:
    """Build preferences from SettingsConfig fields + optional nested dict."""
    base = SchedulingPreferences.from_dict(raw) if raw else empty_scheduling_preferences()
    if working_hours:
        base.working_hours = working_hours
    if timezone:
        base.timezone = timezone
    base.calendar_freebusy_enabled = bool(calendar_freebusy_enabled)
    base.interview_duration_minutes = int(interview_duration_minutes)
    base.buffer_before_minutes = int(buffer_before_minutes)
    base.buffer_after_minutes = int(buffer_after_minutes)
    base.onsite_travel_buffer_minutes = int(onsite_travel_buffer_minutes)
    base.allow_weekends = bool(allow_weekends)
    base.respect_holidays = bool(respect_holidays)
    base.holiday_country = holiday_country or "DE"
    if preferred_windows:
        base.preferred_windows = preferred_windows
    elif telephone_availability and not base.preferred_windows:
        base.preferred_windows = telephone_availability
    base.slot_step_minutes = int(slot_step_minutes)
    base.max_ranked_slots = int(max_ranked_slots)
    base.allow_calendar_write = bool(allow_calendar_write)
    return migrate_scheduling_preferences(base)


def preferences_from_settings_config(settings: Any) -> SchedulingPreferences:
    """Adapter for ``core.config.SettingsConfig`` (duck-typed)."""
    return preferences_from_settings(
        working_hours=getattr(settings, "working_hours", DEFAULT_WORKING_HOURS),
        timezone=getattr(settings, "scheduling_timezone", DEFAULT_TIMEZONE),
        calendar_freebusy_enabled=getattr(settings, "calendar_freebusy_enabled", False),
        telephone_availability=getattr(settings, "telephone_availability", ""),
        raw=getattr(settings, "scheduling_preferences", None),
        interview_duration_minutes=getattr(settings, "interview_duration_minutes", 60),
        buffer_before_minutes=getattr(settings, "schedule_buffer_before_minutes", 15),
        buffer_after_minutes=getattr(settings, "schedule_buffer_after_minutes", 15),
        onsite_travel_buffer_minutes=getattr(settings, "onsite_travel_buffer_minutes", 0),
        allow_weekends=getattr(settings, "schedule_allow_weekends", False),
        respect_holidays=getattr(settings, "schedule_respect_holidays", False),
        holiday_country=getattr(settings, "schedule_holiday_country", "DE"),
        preferred_windows=getattr(settings, "schedule_preferred_windows", ""),
        slot_step_minutes=getattr(settings, "schedule_slot_step_minutes", 30),
        max_ranked_slots=getattr(settings, "schedule_max_ranked_slots", 5),
        allow_calendar_write=getattr(settings, "allow_calendar_write", False),
    )
