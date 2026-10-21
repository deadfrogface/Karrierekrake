"""Minimal CalDAV transport over httpx.

Written for Karrierekrake from the public specifications: RFC 4918 (WebDAV PROPFIND), RFC 4791 (CalDAV:
calendar-home-set, calendar-query REPORT), RFC 6764 (``/.well-known/caldav`` discovery) and RFC 5545
(iCalendar). It offers just what ``LiveCaldavClient`` uses: ``principal().calendars()``,
``calendar.search(...)``, ``put``, ``request`` and ``close``.
"""
from __future__ import annotations

import time
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, Self
from urllib.parse import urljoin, urlparse
from zoneinfo import ZoneInfo

import httpx
from lxml import etree

from integrations.calendar.caldav.recurrence import expand

DAV = "DAV:"
CALDAV = "urn:ietf:params:xml:ns:caldav"
_NS = {"d": DAV, "c": CALDAV}
_MAX_BODY = 20 * 1024 * 1024
_MAX_REDIRECTS = 5
_PARSER = etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False)

_PROPFIND_PRINCIPAL = (
    '<?xml version="1.0" encoding="utf-8"?><d:propfind xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">'
    "<d:prop><d:current-user-principal/><c:calendar-home-set/></d:prop></d:propfind>")
_PROPFIND_HOME = (
    '<?xml version="1.0" encoding="utf-8"?><d:propfind xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">'
    "<d:prop><d:resourcetype/><d:displayname/><c:supported-calendar-component-set/></d:prop></d:propfind>")


class DavError(Exception):
    """A request failed; the message never contains credentials or calendar content."""


def _site(host: str) -> str:
    return ".".join((host or "").lower().split(".")[-2:])


class DavResponse:
    def __init__(self, response: httpx.Response) -> None:
        self.status = response.status_code
        self.headers = response.headers
        self.raw = response.text
        self.url = str(response.url)


class DAVClient:
    def __init__(self, url: str, username: str = "", password: str = "", timeout: float = 20,
                 ssl_verify_cert: bool = True, require_tls: bool = True, rate_limit_max_sleep: float = 1,
                 default_timezone: str = "Europe/Berlin", **_: Any) -> None:
        parts = urlparse(url)
        if require_tls and parts.scheme != "https":
            raise DavError("tls_required")
        self.url = url
        self._auth: httpx.Auth = httpx.BasicAuth(username, password)
        self._credentials = (username, password)
        self._max_sleep = rate_limit_max_sleep
        self._http = httpx.Client(timeout=timeout, verify=ssl_verify_cert, follow_redirects=False,
                                  headers={"User-Agent": "Karrierekrake/1.0"})
        self._origin = parts
        self.default_timezone = default_timezone

    # --- plumbing -------------------------------------------------------------------------------
    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _allowed(self, target: str) -> bool:
        parts = urlparse(target)
        return parts.scheme == "https" and (_site(parts.hostname or "") == _site(self._origin.hostname or ""))

    def request(self, url: str, method: str = "GET", body: str | bytes | None = None,
                headers: dict[str, str] | None = None) -> DavResponse:
        """One DAV request. Redirects are followed only inside the account's own site; credentials never go elsewhere."""
        if not self._allowed(url):
            raise DavError("foreign_host")
        current, verb, retried = url, method, False
        for _ in range(_MAX_REDIRECTS + 1):
            response = self._http.request(verb, current, content=body, headers=headers, auth=self._auth)
            if response.status_code == 401 and "digest" in response.headers.get("www-authenticate", "").lower() \
                    and isinstance(self._auth, httpx.BasicAuth):
                self._auth = httpx.DigestAuth(*self._credentials)
                continue
            if response.status_code in {429, 503} and not retried:
                wait = response.headers.get("retry-after", "")
                if wait.isdigit() and float(wait) <= self._max_sleep:
                    time.sleep(float(wait))
                    retried = True
                    continue
            if response.status_code in {301, 302, 307, 308} and response.headers.get("location"):
                current = urljoin(current, response.headers["location"])
                if not self._allowed(current):
                    raise DavError("foreign_host")
                continue
            if len(response.content) > _MAX_BODY:
                raise DavError("response_too_large")
            return DavResponse(response)
        raise DavError("too_many_redirects")

    def put(self, url: str, data: str, headers: dict[str, str] | None = None) -> DavResponse:
        return self.request(url, "PUT", body=data.encode("utf-8"), headers=headers)

    def _multistatus(self, url: str, method: str, body: str, depth: str) -> tuple[str, list[Any]]:
        response = self.request(url, method, body=body, headers={"Depth": depth, "Content-Type": "application/xml"})
        if response.status not in {207, 200}:
            raise DavError(f"http_{response.status}")
        try:
            root = etree.fromstring(response.raw.encode("utf-8"), _PARSER)
        except etree.XMLSyntaxError as exc:
            raise DavError("invalid_xml") from exc
        return response.url, root.findall("d:response", _NS)

    # --- discovery ------------------------------------------------------------------------------
    def principal(self) -> Principal:
        for start in (self.url, urljoin(self.url, "/.well-known/caldav")):
            try:
                base, rows = self._multistatus(start, "PROPFIND", _PROPFIND_PRINCIPAL, "0")
            except DavError:
                continue
            for row in rows:
                home = row.find(".//c:calendar-home-set/d:href", _NS)
                if home is not None and (home.text or "").strip():
                    return Principal(self, urljoin(base, home.text.strip()))
                principal = row.find(".//d:current-user-principal/d:href", _NS)
                if principal is not None and (principal.text or "").strip():
                    principal_url = urljoin(base, principal.text.strip())
                    home_url = self._home_set(principal_url)
                    if home_url:
                        return Principal(self, home_url)
        raise DavError("no_calendar_home")

    def _home_set(self, principal_url: str) -> str:
        base, rows = self._multistatus(principal_url, "PROPFIND", _PROPFIND_PRINCIPAL, "0")
        for row in rows:
            home = row.find(".//c:calendar-home-set/d:href", _NS)
            if home is not None and (home.text or "").strip():
                return urljoin(base, home.text.strip())
        return ""


class Principal:
    def __init__(self, client: DAVClient, home_url: str) -> None:
        self._client = client
        self.home_url = home_url

    def calendars(self) -> list[Calendar]:
        base, rows = self._client._multistatus(self.home_url, "PROPFIND", _PROPFIND_HOME, "1")
        found = []
        for row in rows:
            if row.find(".//d:resourcetype/c:calendar", _NS) is None:
                continue
            components = [c.get("name", "").upper() for c in row.findall(".//c:supported-calendar-component-set/c:comp", _NS)]
            if components and "VEVENT" not in components:
                continue
            href = row.findtext("d:href", default="", namespaces=_NS).strip()
            if href:
                found.append(Calendar(self._client, urljoin(base, href)))
        return found


class Calendar:
    def __init__(self, client: DAVClient, url: str) -> None:
        self._client = client
        self.url = url

    def search(self, event: bool = True, start: datetime | None = None, end: datetime | None = None,
               expand: bool = False, **_: Any) -> list[Any]:
        """Events overlapping [start, end]; with ``expand`` recurring events come back as single occurrences."""
        stamp = "%Y%m%dT%H%M%SZ"
        window = ""
        if start is not None and end is not None:
            window = (f'<c:time-range start="{start.astimezone(UTC).strftime(stamp)}" '
                      f'end="{end.astimezone(UTC).strftime(stamp)}"/>')
        body = ('<?xml version="1.0" encoding="utf-8"?><c:calendar-query xmlns:d="DAV:" '
                'xmlns:c="urn:ietf:params:xml:ns:caldav"><d:prop><d:getetag/><c:calendar-data/></d:prop><c:filter>'
                f'<c:comp-filter name="VCALENDAR"><c:comp-filter name="VEVENT">{window}</c:comp-filter>'
                "</c:comp-filter></c:filter></c:calendar-query>")
        _, rows = self._client._multistatus(self.url, "REPORT", body, "1")
        documents = [text for row in rows
                     if (text := row.findtext(".//c:calendar-data", default="", namespaces=_NS).strip())]
        if expand and start is not None and end is not None:
            tz = ZoneInfo(self._client.default_timezone)
            documents = _expanded(documents, start, end, tz)
        return [SimpleNamespace(data=text) for text in documents]


def _expanded(documents: list[str], start: datetime, end: datetime, tz: ZoneInfo) -> list[str]:
    return expand(documents, start, end, tz)
