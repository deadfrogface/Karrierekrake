"""Shared JobPosting JSON-LD → Job mapping for HTML scrapers."""

from __future__ import annotations

import re
from typing import Any

from bs4 import BeautifulSoup

from core.deduplicator import make_job_id
from core.geo_normalize import (
    normalize_country_code,
    source_location_blob_to_fields,
)
from core.models import Job, RemoteType
from search.job_schema import normalize_portal_job


def _is_job_posting_type(type_value: Any) -> bool:
    if type_value == "JobPosting":
        return True
    if isinstance(type_value, list) and "JobPosting" in type_value:
        return True
    return False


def iter_job_postings(payload: Any) -> list[dict]:
    """Extract JobPosting dicts from a parsed JSON-LD document.

    Supports bare JobPosting objects, ``@graph`` arrays, and schema.org
    ``ItemList`` wrappers (common on StepStone/XING list pages).
    """
    items = payload if isinstance(payload, list) else [payload]
    out: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if _is_job_posting_type(item.get("@type")):
            out.append(item)
        if item.get("@type") == "ItemList":
            for elem in item.get("itemListElement") or []:
                if not isinstance(elem, dict):
                    continue
                candidate = elem.get("item", elem)
                if isinstance(candidate, dict) and _is_job_posting_type(candidate.get("@type")):
                    out.append(candidate)
        for g in item.get("@graph") or []:
            if isinstance(g, dict) and _is_job_posting_type(g.get("@type")):
                out.append(g)
    return out



def _is_gender_only_title(title: str) -> bool:
    cleaned = (title or "").strip()
    if not cleaned:
        return True
    stripped = re.sub(
        r"\((?:m/w/d|w/m/d|m/w|w/m|f/m/d|d/m/w|all genders|alle geschlechter)\)|"
        r"\b(?:m/w/d|w/m/d|f/m/d|d/m/w)\b",
        " ",
        cleaned,
        flags=re.I,
    )
    stripped = re.sub(r"[\s|/\\-–—]+", " ", stripped).strip()
    return len(stripped) < 2


def _infer_remote(*parts: str) -> str:
    blob = " ".join(p or "" for p in parts).lower()
    blob_norm = (
        blob.replace("home-office", "homeoffice")
        .replace("home office", "homeoffice")
    )
    # Explicit onsite / no-remote phrasing wins over loose keyword hits.
    if re.search(
        r"\b(?:kein|keine|ohne|nicht|no)\s+(?:homeoffice|remote|telearbeit)\b"
        r"|\bpräsenzpflicht\b|\bnur\s+vor\s+ort\b",
        blob_norm,
    ):
        return RemoteType.ONSITE.value
    # Remote-desktop / remote-access tooling is not a remote job.
    if re.search(r"\bremote[\s\-_]?(?:desktop|access|support|verwaltung)\b", blob_norm):
        if "homeoffice" not in blob_norm and "telearbeit" not in blob_norm and "hybrid" not in blob_norm:
            return RemoteType.ONSITE.value
    if "hybrid" in blob_norm:
        return RemoteType.HYBRID.value
    if any(
        k in blob_norm
        for k in ("remote", "homeoffice", "telearbeit", "telecommute", "mobil arbeiten")
    ):
        return RemoteType.REMOTE.value
    city = (parts[-1] if parts else "") or ""
    if city.strip().lower() in {"remote", "homeoffice", "home office", "telecommute"}:
        return RemoteType.REMOTE.value
    return RemoteType.ONSITE.value


def _salary_from_base_salary(item: dict) -> tuple[float | None, float | None, str]:
    """Map schema.org baseSalary → (min, max, text)."""
    bs = item.get("baseSalary")
    if not isinstance(bs, dict):
        return None, None, ""
    currency = str(bs.get("currency") or "").strip()
    val = bs.get("value")
    unit = ""
    smin = smax = None
    if isinstance(val, dict):
        unit = str(val.get("unitText") or "").strip()
        for key, target in (("minValue", "min"), ("maxValue", "max"), ("value", "single")):
            raw = val.get(key)
            if raw is None:
                continue
            try:
                num = float(raw)
            except (TypeError, ValueError):
                continue
            if target == "min":
                smin = num
            elif target == "max":
                smax = num
            elif smin is None and smax is None:
                smin = num
    elif isinstance(val, (int, float)):
        smin = float(val)
        unit = str(bs.get("unitText") or "").strip()
    bits: list[str] = []
    if smin is not None and smax is not None and smin != smax:
        bits.append(f"{smin:g} – {smax:g}")
    elif smin is not None:
        bits.append(f"{smin:g}")
    elif smax is not None:
        bits.append(f"{smax:g}")
    if currency:
        bits.append(currency)
    if unit:
        bits.append(unit)
    return smin, smax, " ".join(bits).strip()


def job_from_list_card(
    *,
    source: str,
    title: str,
    url: str,
    company: str = "",
    city: str = "",
    min_title_len: int = 5,
    country_code: str = "",
) -> Job | None:
    """Build a Job from HTML card/link fallbacks when JSON-LD is absent."""
    title = (title or "").strip()
    url = (url or "").strip()
    if len(title) < min_title_len or not url:
        return None
    if _is_gender_only_title(title):
        return None
    company = (company or "").strip()
    fields = source_location_blob_to_fields(city)
    city_n = fields["city"] or (city or "").strip()
    cc = normalize_country_code(country_code) or fields["country_code"]
    job = Job(
        id=make_job_id(source, url, url, title, company),
        source=source,
        source_job_id=url,
        title=title,
        company=company,
        description="",
        city=city_n,
        postal_code=fields.get("postal_code") or "",
        address=city or city_n,
        country_code=cc,
        remote_type=_infer_remote(title, company, city_n),
        published_at="",
        url=url,
        application_url=url,
    )
    return normalize_portal_job(job)


def job_from_job_posting(
    item: dict,
    *,
    source: str,
    min_title_len: int = 1,
) -> Job | None:
    """Normalize a schema.org JobPosting object into a Job."""
    title = str(item.get("title") or "").strip()
    if len(title) < min_title_len:
        return None
    org = item.get("hiringOrganization") or {}
    company = ""
    if isinstance(org, dict):
        company = str(org.get("name") or "").strip()
    url = item.get("url") or item.get("mainEntityOfPage") or ""
    if isinstance(url, dict):
        url = url.get("@id") or ""
    url = str(url or "").strip()
    city = ""
    postal = ""
    country_code = ""
    loc = item.get("jobLocation") or {}
    if isinstance(loc, list) and loc:
        loc = loc[0]
    if isinstance(loc, dict):
        addr = loc.get("address") or {}
        if isinstance(addr, dict):
            city = str(addr.get("addressLocality") or "").strip()
            postal = str(addr.get("postalCode") or "").strip()
            country_code = normalize_country_code(
                addr.get("addressCountry") or ""
            )
    description = item.get("description") or ""
    text = (
        BeautifulSoup(description, "lxml").get_text("\n", strip=True) if description else ""
    )
    location_type = str(item.get("jobLocationType") or "").upper()
    remote = _infer_remote(title, text, city, location_type)
    if "TELECOMMUTE" in location_type:
        remote = RemoteType.REMOTE.value
    smin, smax, salary_text = _salary_from_base_salary(item)
    if not country_code:
        country_code = source_location_blob_to_fields(
            f"{postal} {city}".strip()
        ).get("country_code") or ""
    job = Job(
        id=make_job_id(source, url, url, title, company),
        source=source,
        source_job_id=url,
        title=title,
        company=company,
        description=text,
        city=city,
        postal_code=postal,
        address=city,
        country_code=country_code,
        remote_type=remote,
        salary_min=smin,
        salary_max=smax,
        salary_text=salary_text,
        published_at=str(item.get("datePosted") or ""),
        url=url,
        application_url=url,
    )
    return normalize_portal_job(job)
