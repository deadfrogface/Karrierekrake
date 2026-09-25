"""One cleaned job shape for matching, shared by portal scrapers.

Strips HTML and placeholder junk, splits location blobs such as
``Berlin, Deutschland``, and keeps work model on ``remote_type``
(``onsite`` | ``hybrid`` | ``remote`` | ``unknown``).

LinkedIn is not expanded here — Indeed's normalizer calls this helper, and
the LinkedIn adapter stays the existing stub.
"""

from __future__ import annotations

import html
import re

from bs4 import BeautifulSoup

from core.geo_normalize import source_location_blob_to_fields
from core.models import Job, RemoteType
from core.text_normalize import clean_company, clean_text, is_blankish

WORK_MODELS = (
    RemoteType.ONSITE.value,
    RemoteType.HYBRID.value,
    RemoteType.REMOTE.value,
    RemoteType.UNKNOWN.value,
)

_TAG_RE = re.compile(r"<\s*/?\s*[a-zA-Z!]")
_WORK_ALIASES = {
    "homeoffice": RemoteType.REMOTE.value,
    "home-office": RemoteType.REMOTE.value,
    "home office": RemoteType.REMOTE.value,
    "telearbeit": RemoteType.REMOTE.value,
    "telecommute": RemoteType.REMOTE.value,
    "vollremote": RemoteType.REMOTE.value,
    "remote": RemoteType.REMOTE.value,
    "hybrid": RemoteType.HYBRID.value,
    "vor ort": RemoteType.ONSITE.value,
    "vor-ort": RemoteType.ONSITE.value,
    "praesenz": RemoteType.ONSITE.value,
    "präsenz": RemoteType.ONSITE.value,
    "onsite": RemoteType.ONSITE.value,
    "on-site": RemoteType.ONSITE.value,
    "on site": RemoteType.ONSITE.value,
    "unknown": RemoteType.UNKNOWN.value,
    "unbekannt": RemoteType.UNKNOWN.value,
}


def strip_markup(value: object, *, keep_lines: bool = False) -> str:
    """Remove HTML, entities, and blank placeholders. Does not invent text."""
    raw = "" if value is None else str(value)
    if _TAG_RE.search(raw):
        soup = BeautifulSoup(raw, "lxml")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        raw = soup.get_text("\n" if keep_lines else " ", strip=True)
    raw = html.unescape(raw).replace("\u00a0", " ").replace("\u200b", "")
    if keep_lines:
        lines = [" ".join(line.split()) for line in raw.splitlines()]
        raw = "\n".join(line for line in lines if line)
    else:
        raw = " ".join(raw.split())
    if is_blankish(raw):
        return ""
    return raw.strip()


def canonical_work_model(value: object) -> str:
    text = " ".join(str(value or "").replace("_", " ").split()).strip().lower()
    if not text or is_blankish(text):
        return RemoteType.UNKNOWN.value
    if text in _WORK_ALIASES:
        return _WORK_ALIASES[text]
    if text in WORK_MODELS:
        return text
    return RemoteType.UNKNOWN.value


def _usable_city(value: str) -> str:
    city = clean_text(value)
    if not city or city.isdigit():
        return ""
    return city


def apply_location_blob(job: Job) -> None:
    """Normalize ``Berlin, Deutschland`` style blobs onto city / PLZ / country.

    The city field wins over an address that starts with a postal code, so
    ``20095, Hamburg, Deutschland`` does not replace Hamburg with ``20095``.
    """
    city_fields = (
        source_location_blob_to_fields(clean_text(job.city)) if clean_text(job.city) else {}
    )
    addr_fields = (
        source_location_blob_to_fields(clean_text(job.address))
        if clean_text(job.address)
        else {}
    )
    parsed_city = _usable_city(str(city_fields.get("city") or "")) or _usable_city(
        str(addr_fields.get("city") or "")
    )
    if parsed_city and ("," in (job.city or "") or not clean_text(job.city)):
        job.city = parsed_city
    if not clean_text(job.postal_code):
        plz = str(city_fields.get("postal_code") or addr_fields.get("postal_code") or "")
        if plz:
            job.postal_code = plz
    if not clean_text(job.country_code):
        cc = str(city_fields.get("country_code") or addr_fields.get("country_code") or "")
        if cc:
            job.country_code = cc
    if not clean_text(job.address):
        job.address = ", ".join(
            p for p in (job.postal_code, job.city, job.country_code) if clean_text(p)
        )


def normalize_portal_job(job: Job) -> Job:
    """Return the same job with matching-ready title/company/location/work model/description."""
    job.title = strip_markup(job.title)
    job.company = clean_company(strip_markup(job.company))
    job.city = strip_markup(job.city)
    job.address = strip_markup(job.address)
    job.postal_code = strip_markup(job.postal_code)
    job.description = strip_markup(job.description, keep_lines=True)
    job.salary_text = strip_markup(job.salary_text)
    apply_location_blob(job)
    job.remote_type = canonical_work_model(job.remote_type)
    job.country_code = (job.country_code or "").strip().upper()
    return job
