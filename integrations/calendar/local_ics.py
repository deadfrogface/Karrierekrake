"""Local calendar snapshot for Google, Samsung and Apple exports; never writes."""
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from icalendar import Calendar
import recurring_ical_events
from integrations.calendar.contracts import BusyInterval, CalendarAccountIdentity
from integrations.providers.enums import CalendarProvider, ProviderError

MAX_BYTES = 20 * 1024 * 1024
MAX_AGE = timedelta(days=7)


def read_calendar(path):
    path = Path(path)
    if not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise ValueError('Bitte eine Kalenderdatei bis 20 MB auswählen.')
    calendar = Calendar.from_ical(path.read_bytes())
    if calendar.name != 'VCALENDAR':
        raise ValueError('Ungültige Kalenderdatei.')
    # Malformed timed events must not appear as free time.
    for event in calendar.walk('VEVENT'):
        if 'DTSTART' not in event:
            raise ValueError('Kalender enthält einen Termin ohne Beginn.')
        start = event.decoded('DTSTART')
        if 'DTEND' in event:
            end = event.decoded('DTEND')
            if isinstance(start, datetime) != isinstance(end, datetime):
                raise ValueError('Kalender enthält inkompatible Terminzeiten.')
            if isinstance(start, datetime):
                # RFC floating timestamps use the configured timezone at query time.
                a = start if start.tzinfo else start.replace(tzinfo=ZoneInfo('Europe/Berlin'))
                b = end if end.tzinfo else end.replace(tzinfo=ZoneInfo('Europe/Berlin'))
                valid = b > a
            else:
                valid = end > start
            if not valid:
                raise ValueError('Kalender enthält einen Termin mit ungültigem Ende.')
        elif 'DURATION' in event:
            if event.decoded('DURATION') <= timedelta(0):
                raise ValueError('Kalender enthält einen Termin mit ungültiger Dauer.')
        elif isinstance(start, datetime):
            raise ValueError('Kalender enthält einen Termin ohne Ende.')
    return calendar


class LocalIcsCalendarAdapter:
    provider = CalendarProvider.LOCAL_ICS

    def __init__(self, *, settings, token_dir=None):
        self.path = Path(settings.local_calendar_path or '')
        self.timezone = getattr(settings, "scheduling_timezone", "Europe/Berlin")

    def identity(self):
        return CalendarAccountIdentity(provider=self.provider, account_key='local_ics', calendar_id='snapshot')

    def is_connected(self):
        try:
            read_calendar(self.path)
            return datetime.now(timezone.utc) - datetime.fromtimestamp(self.path.stat().st_mtime, timezone.utc) <= MAX_AGE
        except Exception:
            return False

    def query_busy(self, q):
        if q.time_min.tzinfo is None or q.time_max.tzinfo is None or not timedelta(0) < q.time_max - q.time_min <= timedelta(days=366):
            raise ProviderError('local_ics', 'calendar_invalid_range', reconnectable=False)
        if not self.is_connected():
            raise ProviderError('local_ics', 'calendar_snapshot_missing_or_stale', reconnectable=True)
        try:
            calendar = read_calendar(self.path)
            tz = ZoneInfo(self.timezone)

            def aware(value):
                if isinstance(value, datetime):
                    return value if value.tzinfo else value.replace(tzinfo=tz)
                if isinstance(value, date):
                    return datetime.combine(value, time.min, tzinfo=tz)
                raise ValueError('invalid_event_date')

            intervals = []
            for event in recurring_ical_events.of(calendar).between(q.time_min, q.time_max):
                if str(event.get('STATUS', '')).upper() == 'CANCELLED' or str(event.get('TRANSP', '')).upper() == 'TRANSPARENT':
                    continue
                raw_start = event.decoded('DTSTART')
                start = aware(raw_start)
                if 'DTEND' in event:
                    end = aware(event.decoded('DTEND'))
                elif 'DURATION' in event:
                    end = start + event.decoded('DURATION')
                elif not isinstance(raw_start, datetime):
                    end = start + timedelta(days=1)
                else:
                    raise ValueError('event_end_missing')
                if end <= start:
                    raise ValueError('invalid_event_end')
                if start < q.time_max and q.time_min < end:
                    intervals.append(BusyInterval(start=start.astimezone(timezone.utc), end=end.astimezone(timezone.utc)))
            return intervals
        except Exception:
            raise ProviderError('local_ics', 'calendar_snapshot_invalid', reconnectable=True) from None

    def create_event(self, draft):
        raise ProviderError('local_ics', 'calendar_snapshot_read_only', reconnectable=False)

    def disconnect(self, *, revoke_remote=True):
        # Configuration cleanup is owned by the caller; remove only the app copy.
        if self.path.name == "calendar-snapshot.ics" and self.path.parent.name == "cache":
            self.path.unlink(missing_ok=True)
