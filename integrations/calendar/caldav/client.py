"""Bounded CalDAV transport backed by python-caldav (discovery and recurrence).

Only busy intervals leave this client; event titles are not used for matching.
Every operation closes its HTTP session, including failed authentication.
"""
from __future__ import annotations

from contextlib import contextmanager, suppress
import logging
from datetime import date, datetime, time, timedelta, timezone
from urllib.parse import quote, urljoin, urlparse
from zoneinfo import ZoneInfo

from integrations.providers.enums import ProviderError


class LiveCaldavClient:
    def __init__(self, secret: dict, *, client_factory=None):
        self._secret = dict(secret)
        self._factory = client_factory
        url = urlparse(str(secret.get("base_url") or ""))
        if url.scheme != "https" or not url.hostname or url.username or url.password:
            raise ProviderError("generic_caldav", "caldav_https_url_required", reconnectable=True)
        if not secret.get("username") or not (secret.get("password") or secret.get("app_password")):
            raise ProviderError("generic_caldav", "caldav_credentials_missing", reconnectable=True)

    @contextmanager
    def _session(self):
        from caldav import DAVClient
        # Upstream compatibility warnings can include complete event bodies.
        # Surface only the sanitized ProviderError/connection diagnostics.
        logging.getLogger("caldav").setLevel(logging.CRITICAL + 1)
        factory = self._factory or DAVClient
        client = None
        try:
            client = factory(url=self._secret["base_url"], username=self._secret["username"],
                             password=self._secret.get("password") or self._secret.get("app_password"),
                             timeout=20, ssl_verify_cert=True, require_tls=True,
                             rate_limit_max_sleep=1)
            yield client
        except ProviderError:
            raise
        except Exception:
            # HTTP exceptions may contain authenticated URLs or server content.
            raise ProviderError("generic_caldav", "caldav_request_failed", reconnectable=True) from None
        finally:
            with suppress(Exception):
                client.close()

    def _calendars(self, client):
        calendars = client.principal().calendars()
        selected = str(self._secret.get("calendar_path") or "")
        if selected:
            expected = urljoin(self._secret["base_url"], selected).rstrip("/")
            calendars = [c for c in calendars if str(c.url).rstrip("/") == expected]
        if not calendars:
            raise ProviderError("generic_caldav", "caldav_calendar_not_found", reconnectable=True)
        return calendars

    def discover_calendars(self):
        with self._session() as client:
            return [str(c.url) for c in self._calendars(client)]

    def list_busy(self, *, time_min: datetime, time_max: datetime):
        from icalendar import Calendar
        tz = ZoneInfo(str(self._secret.get("timezone") or "Europe/Berlin"))

        def aware(value):
            if isinstance(value, datetime):
                return value if value.tzinfo else value.replace(tzinfo=tz)
            if isinstance(value, date):
                return datetime.combine(value, time.min, tzinfo=tz)
            raise ValueError("invalid_event_date")

        if time_min.tzinfo is None or time_max.tzinfo is None or time_max <= time_min:
            raise ProviderError("generic_caldav", "caldav_invalid_range", reconnectable=False)
        if time_max - time_min > timedelta(days=366):
            raise ProviderError("generic_caldav", "caldav_range_too_large", reconnectable=False)
        intervals = set()
        with self._session() as client:
            for calendar in self._calendars(client):
                # python-caldav expands recurring events and exception dates.
                for event in calendar.search(event=True, start=time_min, end=time_max, expand=True):
                    for part in Calendar.from_ical(event.data).walk("VEVENT"):
                        if str(part.get("STATUS", "")).upper() == "CANCELLED" or str(part.get("TRANSP", "")).upper() == "TRANSPARENT":
                            continue
                        start_value = part.decoded("DTSTART")
                        start = aware(start_value)
                        if "DTEND" in part:
                            end = aware(part.decoded("DTEND"))
                        elif "DURATION" in part:
                            end = start + part.decoded("DURATION")
                        else:
                            end = start + (timedelta(days=1) if not isinstance(start_value, datetime) else timedelta())
                        start, end = start.astimezone(timezone.utc), end.astimezone(timezone.utc)
                        if end > start and start < time_max and end > time_min:
                            intervals.add((start.isoformat(), end.isoformat()))
        return [{"start": start, "end": end} for start, end in sorted(intervals)]

    def put_event(self, *, href: str, ics: str, etag: str = ""):
        from icalendar import Calendar
        requested = Calendar.from_ical(ics).walk("VEVENT")
        if len(requested) != 1:
            raise ProviderError("generic_caldav", "caldav_single_event_required", reconnectable=False)
        with self._session() as client:
            calendars = self._calendars(client)
            if len(calendars) != 1:
                raise ProviderError("generic_caldav", "caldav_select_calendar", reconnectable=False)
            base = str(calendars[0].url).rstrip("/") + "/"
            if urlparse(href).scheme:
                if not href.startswith(base) or "/" in href[len(base):] or "?" in href or "#" in href:
                    raise ProviderError("generic_caldav", "caldav_invalid_event_url", reconnectable=False)
                url = href
            else:
                url = base + quote(href, safe="")
            headers = {"Content-Type": "text/calendar; charset=utf-8"}
            headers["If-Match" if etag else "If-None-Match"] = etag or "*"
            response = client.put(url, ics, headers=headers)
            if response.status == 412 and not etag:
                # A retry may find an already created event. Do not overwrite it.
                existing = client.request(url, "GET")
                existing_events = Calendar.from_ical(existing.raw).walk("VEVENT") if existing.status == 200 else []
                keys = ("UID", "DTSTART", "DTEND", "SUMMARY", "DESCRIPTION", "LOCATION")
                if len(existing_events) != 1 or any(str(existing_events[0].get(k, "")) != str(requested[0].get(k, "")) for k in keys):
                    raise ProviderError("generic_caldav", "caldav_event_conflict", reconnectable=False)
                response = existing
            elif response.status not in {200, 201, 204}:
                raise ProviderError("generic_caldav", "caldav_write_failed", reconnectable=True)
            return {"href": url, "etag": response.headers.get("ETag", "")}
