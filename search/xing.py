"""XING Jobs discovery scraper.

Adapted from JobRadar xing.py (GPL-3.0): JSON-LD first, then card/link
fallbacks, with an optional second results page.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx
from bs4 import BeautifulSoup

from core.models import Job
from search.base import is_source_blocked, JobSource, PartialResultsError, SearchQuery
from search.jsonld import iter_job_postings, job_from_job_posting, job_from_list_card

logger = logging.getLogger("karrierekrake")

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
}
_MIN_TITLE_LEN = 8


class XingSource(JobSource):
    source_id = "xing"

    def health_check(self) -> tuple[bool, str]:
        try:
            with httpx.Client(timeout=8.0, headers=_HEADERS) as client:
                r = client.get("https://www.xing.com/jobs", follow_redirects=True)
                return r.status_code < 500, f"HTTP {r.status_code}"
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)

    def search(self, queries: list[SearchQuery]) -> list[Job]:
        all_jobs: list[Job] = []
        seen: set[str] = set()
        errors: list[str] = []
        for query in queries:
            try:
                for job in self._search_one(query):
                    if job.id not in seen:
                        seen.add(job.id)
                        all_jobs.append(job)
            except Exception as exc:  # noqa: BLE001 — keep other queries
                logger.error("XING query failed for %r: %s", query.keyword, exc)
                errors.append(str(exc))
                if is_source_blocked(exc):
                    break
        if errors and not all_jobs:
            raise RuntimeError(errors[0])
        if errors and all_jobs:
            raise PartialResultsError(all_jobs, errors[0])
        return all_jobs

    def _search_one(self, query: SearchQuery) -> list[Job]:
        location = (query.location or "").strip()
        if location.lower() == "remote":
            location = ""
        params: dict[str, Any] = {"keywords": query.keyword, "sort": "date"}
        if location:
            params["location"] = location
        url = "https://www.xing.com/jobs/search"
        jobs: list[Job] = []
        try:
            with httpx.Client(timeout=30.0, headers=_HEADERS, follow_redirects=True) as client:
                resp = client.get(url, params=params)
                if resp.status_code != 200:
                    logger.warning("XING HTTP %s for %r", resp.status_code, query.keyword)
                    resp.raise_for_status()
                jobs.extend(self._parse_page(BeautifulSoup(resp.text, "lxml")))
                if len(jobs) < query.max_results:
                    resp2 = client.get(url, params={**params, "page": 2})
                    if resp2.status_code == 200:
                        jobs.extend(self._parse_page(BeautifulSoup(resp2.text, "lxml")))
        except httpx.HTTPError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.error("XING search failed for %r: %s", query.keyword, exc)
            raise
        seen_urls: set[str] = set()
        unique: list[Job] = []
        for job in jobs:
            key = (job.url or job.id).lower()
            if key in seen_urls:
                continue
            seen_urls.add(key)
            unique.append(job)
        return unique[: query.max_results]

    def _parse_page(self, soup: BeautifulSoup) -> list[Job]:
        jobs: list[Job] = []
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "")
            except Exception:
                continue
            for item in iter_job_postings(data):
                job = self.normalize(item)
                if job:
                    jobs.append(job)
        if jobs:
            return jobs

        cards = (
            soup.select("[data-testid='job-card']")
            or soup.select("article")
            or soup.select("[class*='job-listing']")
        )
        for card in cards:
            job = self._parse_card(card)
            if job:
                jobs.append(job)
        if jobs:
            return jobs

        seen: set[str] = set()
        for link in soup.find_all("a", href=True):
            href = str(link.get("href") or "")
            if "/jobs/" not in href:
                continue
            if any(x in href for x in ("/search", "/login", "/signup", "/jobs/recommendations")):
                continue
            full_url = href if href.startswith("http") else f"https://www.xing.com{href}"
            if full_url in seen:
                continue
            seen.add(full_url)
            job = job_from_list_card(
                source=self.source_id,
                title=link.get_text(strip=True),
                url=full_url,
                min_title_len=_MIN_TITLE_LEN,
            )
            if job:
                jobs.append(job)
        return jobs

    def _parse_card(self, card: Any) -> Job | None:
        try:
            title_el = (
                card.select_one("[data-testid='job-card-title']")
                or card.select_one("h2")
                or card.select_one("h3")
                or card.select_one("a")
            )
            title = title_el.get_text(strip=True) if title_el else ""
            link_el = card.select_one("a[href*='/jobs/']") or card.select_one("a[href]")
            href = link_el.get("href", "") if link_el else ""
            job_url = href if href.startswith("http") else f"https://www.xing.com{href}"
            company_el = card.select_one("[data-testid='job-card-company']") or card.select_one(
                "[class*='company']"
            )
            company = company_el.get_text(strip=True) if company_el else ""
            location_el = card.select_one("[data-testid='job-card-location']") or card.select_one(
                "[class*='location']"
            )
            city = location_el.get_text(strip=True) if location_el else ""
            return job_from_list_card(
                source=self.source_id,
                title=title,
                url=job_url,
                company=company,
                city=city,
                min_title_len=_MIN_TITLE_LEN,
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("Failed to parse XING card: %s", exc)
            return None

    def normalize(self, raw: Any) -> Job | None:
        return job_from_job_posting(
            raw if isinstance(raw, dict) else {},
            source=self.source_id,
            min_title_len=4,
        )
