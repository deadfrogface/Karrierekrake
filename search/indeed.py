"""Indeed (and, through ``board``, LinkedIn) job discovery.

Written for Karrierekrake. The portal clients are ``search.indeed_api`` and ``search.linkedin_api``; they return flat
rows (id, job_url, job_url_direct, title, company, location, date_posted, job_type, interval, min_amount, max_amount,
currency, is_remote, description) that ``normalize`` turns into jobs.
"""
from __future__ import annotations

import logging
import math
from datetime import date, datetime
from typing import Any

from core.cancel import current_cancel_generation, searches_cancelled
from core.deduplicator import make_job_id
from core.models import Job
from search.base import JobSource, PartialResultsError, SearchQuery, is_source_blocked
from search.job_schema import normalize_portal_job, strip_markup
from search.portal_html import raise_first
from search.remote_text import classify_remote, truthy_flag

logger = logging.getLogger("karrierekrake")

_INTERVALS = {"yearly": "year", "monthly": "month", "weekly": "week", "daily": "day", "hourly": "hour"}
_COUNTRY = "germany"
_MAX_QUERIES = 6


def _blank(value: Any) -> bool:
    return value is None or (isinstance(value, float) and math.isnan(value)) or str(value).strip().lower() in {
        "", "nan", "none", "nat", "null"}


def _text(row: dict, *names: str) -> str:
    for name in names:
        value = row.get(name)
        if not _blank(value):
            return str(value).strip()
    return ""


def _amount(value: Any) -> float | None:
    if _blank(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _remote_from_row(row: dict) -> str:
    """Work model of a JobSpy row: the ad's own wording beats the ``is_remote`` checkbox."""
    text = " ".join(_text(row, key) for key in ("location", "title", "description"))
    return classify_remote(text, flag=truthy_flag(row.get("is_remote")) if not _blank(row.get("is_remote")) else None)


def _city_and_country(location: str) -> str:
    """JobSpy writes "city, state, country". The state is a code like "BE" (Berlin), which reads as Belgium."""
    parts = [part.strip() for part in location.split(",") if part.strip()]
    return f"{parts[0]}, {parts[-1]}" if len(parts) >= 3 else location


def _salary(row: dict) -> tuple[float | None, float | None, str]:
    low, high = _amount(row.get("min_amount")), _amount(row.get("max_amount"))
    if low is None and high is None:
        return None, None, ""
    unit = _INTERVALS.get(_text(row, "interval").lower(), "")
    currency = _text(row, "currency") or "EUR"
    parts = [f"{value:g}" for value in (low, high) if value is not None]
    if len(parts) == 2 and low == high:
        parts = parts[:1]
    amount = " – ".join(parts)
    return low, high, f"{amount} {currency}" + (f"/{unit}" if unit else "")


class IndeedSource(JobSource):
    source_id = "indeed"
    board = "indeed"

    def health_check(self) -> tuple[bool, str]:
        return True, "ok"

    def search(self, queries: list[SearchQuery]) -> list[Job]:
        generation = current_cancel_generation()
        found: dict[str, Job] = {}
        errors: list[Exception] = []
        for query in list(queries or [])[:_MAX_QUERIES]:
            if searches_cancelled(generation):
                break
            try:
                for job in self._search_one(query):
                    found.setdefault(job.id, job)
            except Exception as exc:  # noqa: BLE001 - one failing query must not hide the others
                logger.warning("%s query %r failed: %s", self.source_id, query.keyword, exc)
                errors.append(exc)
                if is_source_blocked(exc):
                    break
        jobs = list(found.values())
        if errors and jobs:
            raise PartialResultsError(jobs, f"{len(errors)} Suchen fehlgeschlagen: {errors[0]}")
        if errors:
            raise_first(self.source_id, errors)
        return jobs

    def _search_one(self, query: SearchQuery) -> list[Job]:
        from search import indeed_api, linkedin_api

        extra = dict(query.extra or {})
        remote_only = (query.location or "").strip().lower() == "remote"
        location = "Germany" if remote_only or not (query.location or "").strip() else query.location.strip()
        hours = int(extra.get("hours_old") or max(1, int(query.published_within_days or 14)) * 24)
        wanted = max(1, int(query.max_results or 50))
        radius = float(query.radius_km or 0) or 50.0
        if self.board == "linkedin":
            rows = linkedin_api.search(term=query.keyword, location=location, radius_km=radius, results_wanted=wanted,
                                       hours_old=hours, fetch_description=bool(extra.get("linkedin_fetch_description")))
        else:
            rows = indeed_api.search(term=query.keyword, location=location, radius_km=radius, results_wanted=wanted,
                                     hours_old=hours, country=str(extra.get("country_indeed") or _COUNTRY),
                                     remote_only=remote_only)
        return [job for job in (self.normalize(row) for row in rows) if job is not None]

    def normalize(self, raw: Any) -> Job | None:
        if not isinstance(raw, dict):
            return None
        title = strip_markup(_text(raw, "title"))
        url = _text(raw, "job_url", "job_url_direct")
        if not title or not (url or _text(raw, "id")):
            return None
        low, high, salary_text = _salary(raw)
        posted = raw.get("date_posted")
        published = posted.isoformat() if isinstance(posted, (date, datetime)) else ("" if _blank(posted) else str(posted))
        job_type = raw.get("job_type")
        employment = ", ".join(str(t) for t in job_type) if isinstance(job_type, (list, tuple)) else _text(raw, "job_type")
        source_id = _text(raw, "id")
        company = _text(raw, "company")
        location = _city_and_country(_text(raw, "location"))
        job = Job(
            id=make_job_id(self.source_id, source_id, url, title, company), source=self.source_id,
            source_job_id=source_id, title=title, company=company, description=_text(raw, "description"),
            city=location, address=location, employment_type=employment, salary_min=low, salary_max=high,
            salary_text=salary_text, published_at=published, url=url,
            application_url=_text(raw, "job_url_direct") or url,
        )
        job.remote_type = _remote_from_row(raw)
        return normalize_portal_job(job)
