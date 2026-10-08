"""Read-only HTTPS ICS subscription with SSRF protections.

Never send the private subscription URL to logs or remote services.
"""
from __future__ import annotations

import ipaddress
import socket
import urllib.parse
import urllib.request

from integrations.calendar.local_ics import MAX_BYTES, read_calendar


def validate_feed_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url.strip())
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Nur private HTTPS-ICS-Links ohne eingebettete Zugangsdaten erlaubt.")
    if parsed.port not in (None, 443):
        raise ValueError("ICS-Feed darf keinen alternativen Port verwenden.")
    hostname = parsed.hostname.rstrip(".").lower()
    if hostname in {"localhost", "localhost.localdomain"} or hostname.endswith((".local", ".internal")):
        raise ValueError("Lokale Netzwerkadressen sind nicht erlaubt.")
    try:
        addresses = socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise ValueError("ICS-Server konnte nicht aufgelöst werden.") from exc
    if not addresses:
        raise ValueError("ICS-Server konnte nicht aufgelöst werden.")
    for entry in addresses:
        address = ipaddress.ip_address(entry[4][0].split("%")[0])
        if not address.is_global:
            raise ValueError("Private und interne Netzwerkadressen sind nicht erlaubt.")
    return url.strip()


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("ICS-Weiterleitungen sind nicht erlaubt.")


def fetch_ics_feed(url: str, destination, *, opener=None) -> None:
    """Explicitly download a calendar snapshot; atomic replace after validation.

    Revalidate the hostname on every refresh. No background network requests.
    A private ICS URL is a bearer secret: callers must store it in the OS vault.
    """
    from pathlib import Path
    import os
    import tempfile

    safe_url = validate_feed_url(url)
    # The standard URL opener may resolve a different address after validation.
    # Restrict subscriptions to Google's official public ICS host until a
    # DNS-pinned transport is implemented for arbitrary providers.
    hostname = urllib.parse.urlsplit(safe_url).hostname
    if hostname not in {"calendar.google.com", "www.google.com"}:
        raise ValueError("Automatischer ICS-Abruf unterstützt derzeit nur Google Calendar.")
    destination = Path(destination)
    client = opener or urllib.request.build_opener(NoRedirect())
    request = urllib.request.Request(safe_url, headers={"User-Agent": "Karrierekrake-ICS/1.0"})
    try:
        with client.open(request, timeout=15) as response:
            if response.status != 200:
                raise ValueError("ICS-Abruf fehlgeschlagen.")
            data = response.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise ValueError("Kalenderdatei ist zu groß.")
        destination.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".ics-", suffix=".tmp", dir=destination.parent)
        try:
            with os.fdopen(fd, "wb") as out:
                out.write(data)
            read_calendar(tmp)
            os.replace(tmp, destination)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
    except Exception as exc:
        raise ValueError("ICS-Feed konnte nicht sicher aktualisiert werden.") from exc
