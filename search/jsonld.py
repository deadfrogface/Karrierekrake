"""schema.org ``JobPosting`` data (JSON-LD or microdata dicts) → ``Job``.

Written for Karrierekrake from the public schema.org vocabulary (JobPosting, Organization, Place,
PostalAddress, MonetaryAmount, QuantitativeValue) and Google's job-posting structured-data guide.
"""
from __future__ import annotations

import re
from typing import Any

from core.deduplicator import make_job_id
from core.geo_normalize import normalize_country_code
from core.models import Job
from search.job_schema import normalize_portal_job, strip_markup
from search.remote_text import classify_remote

_UNITS = {"YEAR": "year", "MONTH": "month", "WEEK": "week", "DAY": "day", "HOUR": "hour"}
_GENDER_ONLY = re.compile(r"^[\s(\[]*(?:[mwfdxi*]\s*[/|,]\s*)+[mwfdxi*][\s)\]]*$", re.IGNORECASE)
_DEFAULT_MIN_TITLE = 3


def _types(node: Any) -> set[str]:
    value = node.get("@type") if isinstance(node, dict) else None
    values = value if isinstance(value, list) else [value]
    return {str(v).rsplit("/", 1)[-1] for v in values if v}


def iter_job_postings(payload: Any) -> list[dict]:
    """Every JobPosting inside a JSON-LD document: top level, ``@graph``, ``ItemList`` entries, nested lists."""
    found: list[dict] = []

    def walk(node: Any) -> None:
        if isinstance(node, list):
            for child in node:
                walk(child)
        elif isinstance(node, dict):
            if "JobPosting" in _types(node):
                found.append(node)
                return
            for key in ("@graph", "itemListElement", "item", "mainEntity", "mainEntityOfPage"):
                if key in node:
                    walk(node[key])

    walk(payload)
    return found


def _is_gender_only_title(title: str) -> bool:
    return bool(_GENDER_ONLY.match(title or ""))


def _name(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("name") or value.get("legalName") or "")
    if isinstance(value, list):
        return next((n for n in (_name(v) for v in value) if n), "")
    return "" if value is None else str(value)


def _salary(item: dict) -> tuple[float | None, float | None, str]:
    base = item.get("baseSalary")
    if not isinstance(base, dict):
        return None, None, ""
    currency = str(base.get("currency") or "")
    value = base.get("value")
    unit = ""
    low = high = None
    if isinstance(value, dict):
        unit = _UNITS.get(str(value.get("unitText") or "").upper(), "")
        low = _number(value.get("minValue", value.get("value")))
        high = _number(value.get("maxValue", value.get("value")))
    else:
        low = high = _number(value)
    if low is None and high is None:
        return None, None, ""
    low, high = (low if low is not None else high), (high if high is not None else low)
    amounts = f"{low:g}" if low == high else f"{low:g} – {high:g}"
    return low, high, f"{amounts} {currency}".strip() + (f"/{unit}" if unit else "")


def _number(value: Any) -> float | None:
    try:
        return float(str(value).replace(",", ".")) if value not in (None, "") else None
    except ValueError:
        return None


def _place(item: dict) -> dict[str, Any]:
    location = item.get("jobLocation")
    if isinstance(location, list):
        location = next((p for p in location if isinstance(p, dict)), {})
    location = location if isinstance(location, dict) else {}
    address = location.get("address")
    address = address if isinstance(address, dict) else {"addressLocality": address} if address else {}
    geo = location.get("geo") if isinstance(location.get("geo"), dict) else {}
    country = address.get("addressCountry")
    return {
        "city": str(address.get("addressLocality") or ""), "postal": str(address.get("postalCode") or ""),
        "street": str(address.get("streetAddress") or ""),
        "country": normalize_country_code(_name(country) if isinstance(country, dict) else country),
        "lat": _number(geo.get("latitude")), "lon": _number(geo.get("longitude")),
    }


def job_from_job_posting(item: dict, *, source: str, min_title_len: int = _DEFAULT_MIN_TITLE) -> Job | None:
    """One JobPosting dict → cleaned ``Job``; None when title is too short, gender-only or missing."""
    if not isinstance(item, dict):
        return None
    title = strip_markup(item.get("title") or item.get("name") or "")
    if len(title) < min_title_len or _is_gender_only_title(title):
        return None
    description = strip_markup(item.get("description") or "", keep_lines=True)
    url = str(item.get("url") or "")
    identifier = item.get("identifier")
    source_job_id = str(identifier.get("value") if isinstance(identifier, dict) else identifier or "")
    company = strip_markup(_name(item.get("hiringOrganization")))
    place = _place(item)
    low, high, salary_text = _salary(item)
    employment = item.get("employmentType")
    job = Job(
        id=make_job_id(source, source_job_id, url, title, company), source=source, source_job_id=source_job_id,
        title=title, company=company, description=description, city=place["city"], postal_code=place["postal"],
        address=place["street"], country_code=place["country"], latitude=place["lat"], longitude=place["lon"],
        employment_type=", ".join(map(str, employment)) if isinstance(employment, list) else str(employment or ""),
        salary_min=low, salary_max=high, salary_text=salary_text, published_at=str(item.get("datePosted") or ""),
        url=url, application_url=url,
    )
    telecommute = "TELECOMMUTE" in str(item.get("jobLocationType") or "").upper()
    job.remote_type = classify_remote(f"{title}\n{description}", telecommute=telecommute)
    return normalize_portal_job(job)


def job_from_list_card(*, source: str, title: str, url: str, company: str = "", city: str = "",
                       description: str = "", min_title_len: int = _DEFAULT_MIN_TITLE) -> Job | None:
    """A search-result card (title, link, company, place) → ``Job``; needs a real title and a link."""
    title = strip_markup(title)
    if len(title) < min_title_len or _is_gender_only_title(title) or not str(url or "").strip():
        return None
    company = strip_markup(company)
    job = Job(id=make_job_id(source, "", url, title, company), source=source, title=title, company=company,
              description=strip_markup(description, keep_lines=True), city=city or "", url=url, application_url=url)
    job.remote_type = classify_remote(f"{title} {city or ''}\n{job.description}")
    return normalize_portal_job(job)
