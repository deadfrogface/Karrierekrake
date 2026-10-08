"""Map existing provider selections to bundled offline setup help."""
from __future__ import annotations

GUIDES = {
    "mail": {
        "generic_imap": "mail-generic.html",
        "google_gmail": "mail-google.html",
        "none": "mail-generic.html",
    },
    "calendar": {
        "generic_caldav": "calendar-caldav.html",
        "local_ics": "calendar-ics.html",
        "google_calendar": "calendar-google.html",
        "none": "calendar-ics.html",
    },
}


def guide_filename(kind: str, provider: str) -> str:
    if kind not in GUIDES:
        raise ValueError("Unknown setup guide category")
    return GUIDES[kind].get(provider, GUIDES[kind]["none"])
