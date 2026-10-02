"""Production bridge from configured provider to scheduling and approved writes."""
from pathlib import Path

from integrations.calendar.registry import resolve_calendar_adapter
from integrations.providers.enums import ProviderError


class CalendarSession:
    def __init__(self, settings, *, token_dir: Path):
        self.settings = settings
        self.adapter = resolve_calendar_adapter(settings.calendar_provider, settings=settings,
                                                token_dir=token_dir, allow_none=False)

    def query(self, query):
        # No fallback to an empty calendar when authentication or the API fails.
        return [interval.to_time_window() for interval in self.adapter.query_busy(query)]

    def create_event(self, draft):
        if not draft.approved or not self.settings.allow_calendar_write:
            raise ProviderError("calendar", "calendar_write_not_approved", reconnectable=False)
        from integrations.calendar_freebusy import FreeBusyQuery
        from integrations.calendar_timezone import parse_iso_datetime
        start, end = parse_iso_datetime(draft.start), parse_iso_datetime(draft.end)
        if not start or not end or end <= start:
            raise ProviderError("calendar", "calendar_invalid_dates", reconnectable=False)
        # Recheck availability after approval, not only at proposal time.
        if self.query(FreeBusyQuery(time_min=start, time_max=end)):
            raise ProviderError("calendar", "calendar_slot_now_busy", reconnectable=False)
        return self.adapter.create_event(draft).external_event_id
