"""Public company career boards plus bounded discovery of employer JobPosting pages."""

from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from core.deduplicator import make_job_id
from core.models import Job, RemoteType
from search.base import JobSource, PartialResultsError, SearchQuery

logger = logging.getLogger("karrierekrake")

# (provider, board_token, company_display_name)
# Greenhouse: https://boards-api.greenhouse.io/v1/boards/{token}/jobs
# Lever:     https://api.lever.co/v0/postings/{token}?mode=json
CURATED_BOARDS: tuple[tuple[str, str, str], ...] = (
    ("greenhouse", "zalando", "Zalando SE"),
    ("greenhouse", "deliveryhero", "Delivery Hero SE"),
    ("greenhouse", "n26", "N26 GmbH"),
    ("greenhouse", "personio", "Personio SE & Co. KG"),
    ("greenhouse", "contentful", "Contentful GmbH"),
    ("lever", "auto1-group", "AUTO1 Group"),
    ("lever", "getyourguide", "GetYourGuide"),
    ("lever", "flink", "Flink SE"),
)

_UA = "Karrierekrake/1.0 (+local job discovery; public boards only)"
_TIMEOUT_S = 20


def curated_board_count() -> int:
    return len(CURATED_BOARDS)


def _http_json(url: str) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=_TIMEOUT_S) as resp:  # noqa: S310 — fixed HTTPS hosts
        raw = resp.read()
    return json.loads(raw.decode("utf-8", errors="replace"))


def _keyword_match(title: str, keyword: str) -> bool:
    kw = (keyword or "").strip().lower()
    if not kw:
        return True
    title_l = (title or "").lower()
    tokens = [t for t in re.split(r"[\s,/|+]+", kw) if len(t) >= 2]
    if not tokens:
        return kw in title_l
    return any(tok in title_l for tok in tokens)


def _remote_from_text(*parts: str) -> str:
    blob = " ".join(p for p in parts if p).lower()
    if "hybrid" in blob:
        return RemoteType.HYBRID.value
    if any(x in blob for x in ("remote", "homeoffice", "home office", "telearbeit")):
        return RemoteType.REMOTE.value
    return RemoteType.ONSITE.value


def _fetch_greenhouse(token: str, company: str, keyword: str) -> list[Job]:
    url = f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs"
    data = _http_json(url)
    jobs_raw = data.get("jobs") if isinstance(data, dict) else data
    out: list[Job] = []
    for item in jobs_raw or []:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        if not title or not _keyword_match(title, keyword):
            continue
        abs_url = str(item.get("absolute_url") or "").strip()
        loc = ""
        locs = item.get("location")
        if isinstance(locs, dict):
            loc = str(locs.get("name") or "")
        jid = str(item.get("id") or abs_url or title)
        out.append(
            Job(
                id=make_job_id("company_sites", jid, abs_url, title, company),
                source="company_sites",
                source_job_id=jid,
                title=title,
                company=company,
                description="",
                city=(loc.split(",")[0].strip() if loc else ""),
                address=loc,
                country_code="DE",
                remote_type=_remote_from_text(loc, title),
                url=abs_url,
                application_url=abs_url,
            )
        )
    return out


def _fetch_lever(token: str, company: str, keyword: str) -> list[Job]:
    url = f"https://api.lever.co/v0/postings/{token}?mode=json"
    data = _http_json(url)
    out: list[Job] = []
    for item in data or []:
        if not isinstance(item, dict):
            continue
        title = str(item.get("text") or item.get("title") or "").strip()
        if not title or not _keyword_match(title, keyword):
            continue
        abs_url = str(item.get("hostedUrl") or item.get("applyUrl") or "").strip()
        cats = item.get("categories") if isinstance(item.get("categories"), dict) else {}
        loc = str((cats or {}).get("location") or item.get("workplaceType") or "")
        jid = str(item.get("id") or abs_url or title)
        out.append(
            Job(
                id=make_job_id("company_sites", jid, abs_url, title, company),
                source="company_sites",
                source_job_id=jid,
                title=title,
                company=company,
                description="",
                city=(loc.split(",")[0].strip() if loc else ""),
                address=loc,
                country_code="DE",
                remote_type=_remote_from_text(loc, title, str(item.get("workplaceType") or "")),
                url=abs_url,
                application_url=abs_url,
            )
        )
    return out


class CompanySitesSource(JobSource):
    """Public web discovery plus curated company career boards."""

    source_id = "company_sites"

    def health_check(self) -> tuple[bool, str]:
        return True, (
            f"kuratierte öffentliche Boards ({curated_board_count()}): "
            "Greenhouse/Lever + Websuche nach Karriere- und Stellenseiten"
        )

    def search(self, queries: list[SearchQuery]) -> list[Job]:
        if not queries:
            return []
        from search.company_web import PublicPages, search_web

        all_jobs: dict[str, Job] = {}
        errors: list[str] = []
        pages = PublicPages()
        try:
            for query in queries:
                batch, failures = search_web(query, pages)
                errors.extend(failures)
                for job in batch:
                    all_jobs.setdefault(job.url or job.id, job)
        finally:
            pages.close()
        # Fetch each board once, then match every query, not just queries[0].
        counts = [0] * len(queries)
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = [(provider, token, pool.submit(
                _fetch_greenhouse if provider == "greenhouse" else _fetch_lever,
                token, company, "")) for provider, token, company in CURATED_BOARDS]
            for provider, token, future in futures:
                try:
                    for job in future.result():
                        for index, query in enumerate(queries):
                            if (counts[index] < max(1, int(query.max_results or 40))
                                    and _keyword_match(job.title, query.keyword)):
                                all_jobs.setdefault(job.url or job.id, job)
                                counts[index] += 1
                                break
                except Exception as exc:
                    errors.append(f"{provider}/{token}: {type(exc).__name__}")
        result = list(all_jobs.values())
        if errors and result:
            raise PartialResultsError(result, errors[0])
        if errors and not result:
            raise RuntimeError(errors[0])
        return result
