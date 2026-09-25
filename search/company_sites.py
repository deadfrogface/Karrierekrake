"""Company career pages — curated public Greenhouse / Lever boards only.

Scope (documented):
- Fetch ONLY public JSON endpoints of known DACH-relevant company boards.
- No login, no scraping of arbitrary corporate sites, no invented hits.
- Keyword filter from the active SearchQuery; empty → honest OK_EMPTY / errors.

Boards can be extended by editing CURATED_BOARDS below.
"""

from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.request
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
    """Curated public company career boards (Greenhouse / Lever)."""

    source_id = "company_sites"

    def health_check(self) -> tuple[bool, str]:
        return True, (
            f"kuratierte öffentliche Boards ({curated_board_count()}): "
            "Greenhouse/Lever JSON — kein Platzhalter"
        )

    def search(self, queries: list[SearchQuery]) -> list[Job]:
        if not queries:
            return []
        # Use first query keyword; location is informational for public boards.
        keyword = (queries[0].keyword or "").strip()
        max_results = max(1, int(queries[0].max_results or 40))
        all_jobs: list[Job] = []
        seen: set[str] = set()
        errors: list[str] = []
        for provider, token, company in CURATED_BOARDS:
            try:
                if provider == "greenhouse":
                    batch = _fetch_greenhouse(token, company, keyword)
                elif provider == "lever":
                    batch = _fetch_lever(token, company, keyword)
                else:
                    continue
            except urllib.error.HTTPError as exc:
                errors.append(f"{provider}/{token}: HTTP {exc.code}")
                logger.info("company_sites %s/%s HTTP %s", provider, token, exc.code)
                continue
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{provider}/{token}: {type(exc).__name__}")
                logger.info("company_sites %s/%s error %s", provider, token, type(exc).__name__)
                continue
            for job in batch:
                if job.id in seen:
                    continue
                seen.add(job.id)
                all_jobs.append(job)
                if len(all_jobs) >= max_results:
                    return all_jobs
        if errors and all_jobs:
            raise PartialResultsError(all_jobs, errors[0])
        if not all_jobs and errors and len(errors) >= len(CURATED_BOARDS):
            raise RuntimeError(errors[0])
        return all_jobs
