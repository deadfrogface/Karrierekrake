"""Indeed Germany search via python-jobspy.

Pattern adapted from JobRadar jobspy_adapter.py (GPL-3.0).
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any

from core.deduplicator import make_job_id
from core.geo_normalize import normalize_country_code, source_location_blob_to_fields
from core.models import Job, RemoteType
from search.base import JobSource, PartialResultsError, SearchQuery

logger = logging.getLogger("karrierekrake")


def _remote_from_row(row) -> str:
    """Classify remote/hybrid from JobSpy row location + is_remote flag.

    Normalizes DE/EN Home-Office spellings (space/hyphen) like JSON-LD/BA.
    Explicit negations and Remote-Desktop / remote-access tooling must not
    count as a remote job.
    """
    loc = str(row.get("location") or "").lower()
    loc_norm = (
        loc.replace("home-office", "homeoffice").replace("home office", "homeoffice")
    )
    is_remote = bool(row.get("is_remote"))
    if re.search(
        r"\b(?:kein|keine|ohne|nicht|no)\s+(?:homeoffice|remote|telearbeit)\b"
        r"|\bpräsenzpflicht\b|\bnur\s+vor\s+ort\b",
        loc_norm,
    ):
        return RemoteType.ONSITE.value
    remote_tooling = bool(
        re.search(r"\bremote[\s\-_]?(?:desktop|access|support|verwaltung)\b", loc_norm)
    )
    mentions_home = any(
        tok in loc_norm
        for tok in ("homeoffice", "telearbeit", "telecommute", "mobil arbeiten")
    )
    mentions_remote_word = bool(re.search(r"\bremote\b", loc_norm)) and not remote_tooling
    if "hybrid" in loc_norm:
        return RemoteType.HYBRID.value
    if is_remote or mentions_home or mentions_remote_word:
        return RemoteType.REMOTE.value
    return RemoteType.ONSITE.value


class IndeedSource(JobSource):
    source_id = "indeed"
    board = "indeed"

    def health_check(self) -> tuple[bool, str]:
        try:
            import tls_client  # noqa: F401
            import jobspy  # noqa: F401
        except ImportError as exc:
            return False, f"missing dependency: {exc}"
        except OSError as exc:
            return False, f"native library error: {exc}"
        return True, "ok"

    def search(self, queries: list[SearchQuery]) -> list[Job]:
        try:
            # tls_client ships native DLLs required by python-jobspy on Windows.
            import tls_client  # noqa: F401
            from jobspy import scrape_jobs
        except ImportError as exc:
            raise RuntimeError(
                f"Indeed dependency missing (python-jobspy/tls_client): {exc}"
            ) from exc
        except OSError as exc:
            raise RuntimeError(
                f"Indeed native library failed to load (tls_client DLL): {exc}"
            ) from exc

        all_jobs: list[Job] = []
        seen: set[str] = set()
        hard_errors: list[str] = []
        for query in queries:
            try:
                kwargs = dict(
                    site_name=[self.board],
                    search_term=query.keyword,
                    location=query.location if query.location.lower() != "remote" else "Germany",
                    country_indeed="germany",
                    results_wanted=query.max_results,
                    is_remote=query.location.lower() == "remote",
                    distance=int(query.radius_km) if query.radius_km else None,
                )
                try:
                    df = scrape_jobs(**kwargs)
                except TypeError:
                    # Older/newer jobspy builds differ slightly in kwargs
                    kwargs.pop("distance", None)
                    df = scrape_jobs(**kwargs)
            except Exception as exc:
                logger.error("Indeed JobSpy error for '%s': %s", query.keyword, exc)
                msg = str(exc)
                if any(
                    x in msg.lower()
                    for x in ("dynlib", "dll", "unexpected keyword", "missing")
                ):
                    hard_errors.append(msg)
                    continue
                hard_errors.append(msg)
                continue
            if df is None or getattr(df, "empty", True):
                continue
            for _, row in df.iterrows():
                job = self.normalize(row)
                if job and job.id not in seen:
                    seen.add(job.id)
                    all_jobs.append(job)
        if hard_errors and all_jobs:
            raise PartialResultsError(all_jobs, hard_errors[0])
        if not all_jobs and hard_errors:
            raise RuntimeError(hard_errors[0])
        return all_jobs

    def normalize(self, raw: Any) -> Job | None:
        row = raw
        title = str(row.get("title") or "").strip()
        if not title:
            return None
        url = str(row.get("job_url") or row.get("link") or "").strip()
        company = str(row.get("company") or "").strip()
        location = str(row.get("location") or "").strip()
        fields = source_location_blob_to_fields(location)
        city = fields["city"] or (location.split(",")[0].strip() if location else "")
        # JobSpy Indeed adapter stays DE-scoped (country_indeed=germany) — isolated.
        # Still normalize any explicit country token in the location string.
        country_code = fields["country_code"] or "DE"
        description = str(row.get("description") or "")
        salary_text = ""
        salary_min = salary_max = None
        interval = str(row.get("interval") or row.get("salary_period") or "").strip().lower()
        interval_map = {
            "yearly": "year",
            "year": "year",
            "annual": "year",
            "annually": "year",
            "monthly": "month",
            "month": "month",
            "hourly": "hour",
            "hour": "hour",
        }
        period = interval_map.get(interval, "")
        if row.get("min_amount") is not None or row.get("max_amount") is not None:
            try:
                salary_min = float(row.get("min_amount")) if row.get("min_amount") is not None else None
                salary_max = float(row.get("max_amount")) if row.get("max_amount") is not None else None
                cur = row.get("currency") or "EUR"
                if salary_min is not None and salary_max is not None:
                    salary_text = f"{salary_min}-{salary_max} {cur}"
                elif salary_min is not None:
                    salary_text = f"{salary_min} {cur}"
                elif salary_max is not None:
                    salary_text = f"{salary_max} {cur}"
                if period and salary_text:
                    salary_text = f"{salary_text}/{period}"
            except (TypeError, ValueError):
                salary_text = str(row.get("min_amount") or "")
        dp = row.get("date_posted")
        if isinstance(dp, datetime):
            published = dp.date().isoformat()
        else:
            published = str(dp or "")
        source_job_id = str(row.get("id") or url)
        return Job(
            id=make_job_id(self.source_id, source_job_id, url, title, company),
            source=self.source_id,
            source_job_id=source_job_id,
            title=title,
            company=company,
            description=description,
            city=city,
            postal_code=fields.get("postal_code") or "",
            address=location,
            country_code=normalize_country_code(country_code) or "DE",
            remote_type=_remote_from_row(row),
            employment_type=str(row.get("job_type") or ""),
            salary_min=salary_min,
            salary_max=salary_max,
            salary_text=salary_text,
            published_at=published,
            url=url,
            application_url=str(row.get("job_url_direct") or url),
        )


