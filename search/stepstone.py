"""StepStone Germany discovery scraper.

Adapted from JobRadar stepstone.py (GPL-3.0): JSON-LD first, then article/card
and stellenangebote link fallbacks, with an optional second results page.
"""

from __future__ import annotations

import json
import logging
import re
import urllib.parse
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
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
}


class StepstoneSource(JobSource):
    source_id = "stepstone"

    def health_check(self) -> tuple[bool, str]:
        try:
            with httpx.Client(timeout=8.0, headers=_HEADERS) as client:
                r = client.get("https://www.stepstone.de/", follow_redirects=True)
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
                logger.error("StepStone query failed for %r: %s", query.keyword, exc)
                errors.append(str(exc))
                if is_source_blocked(exc):
                    break
        if errors and not all_jobs:
            raise RuntimeError(errors[0])
        if errors and all_jobs:
            raise PartialResultsError(all_jobs, errors[0])
        return all_jobs

    def _search_one(self, query: SearchQuery) -> list[Job]:
        keyword_slug = urllib.parse.quote_plus(query.keyword)
        location = (query.location or "").strip()
        if location.lower() == "remote":
            location = ""
        radius = int(getattr(query, "radius_km", 50) or 50)
        if location:
            url = (
                f"https://www.stepstone.de/jobs/{keyword_slug}"
                f"/in-{urllib.parse.quote_plus(location)}"
            )
        else:
            url = f"https://www.stepstone.de/work/{keyword_slug}"
        params: dict[str, Any] = {"radius": radius}
        jobs: list[Job] = []
        try:
            with httpx.Client(timeout=30.0, headers=_HEADERS, follow_redirects=True) as client:
                resp = client.get(url, params=params)
                if resp.status_code != 200:
                    logger.warning("StepStone HTTP %s for %r", resp.status_code, query.keyword)
                    resp.raise_for_status()
                jobs.extend(self._parse_page(BeautifulSoup(resp.text, "lxml")))
                if len(jobs) < query.max_results:
                    resp2 = client.get(url, params={**params, "page": 2})
                    if resp2.status_code == 200:
                        jobs.extend(self._parse_page(BeautifulSoup(resp2.text, "lxml")))
        except httpx.HTTPError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.error("StepStone search failed for %r: %s", query.keyword, exc)
            raise
        # Deduplicate by URL within this query
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

        articles = soup.select("article[data-testid]") or soup.select("article")
        for article in articles:
            job = self._parse_article(article)
            if job:
                jobs.append(job)
        if jobs:
            return jobs

        seen: set[str] = set()
        for link in soup.find_all("a", href=re.compile(r"/stellenangebote--")):
            href = link.get("href") or ""
            if not href:
                continue
            full_url = href if href.startswith("http") else f"https://www.stepstone.de{href}"
            if full_url in seen:
                continue
            seen.add(full_url)
            job = job_from_list_card(
                source=self.source_id,
                title=link.get_text(strip=True),
                url=full_url,
                min_title_len=6,
            )
            if job:
                jobs.append(job)
        return jobs

    def _parse_article(self, article: Any) -> Job | None:
        try:
            title_el = (
                article.select_one("h2 a")
                or article.select_one("[data-at='job-item-title']")
                or article.select_one("a[href*='stellenangebote']")
            )
            title = title_el.get_text(strip=True) if title_el else ""
            link_el = (
                title_el
                if title_el and title_el.get("href")
                else article.select_one("a[href*='stellenangebote']")
                or article.select_one("a[href]")
            )
            href = link_el.get("href", "") if link_el else ""
            job_url = href if href.startswith("http") else f"https://www.stepstone.de{href}"
            company_el = article.select_one("[data-at='job-item-company-name']") or article.select_one(
                "span[class*='company']"
            )
            company = company_el.get_text(strip=True) if company_el else ""
            location_el = article.select_one("[data-at='job-item-location']") or article.select_one(
                "span[class*='location']"
            )
            city = location_el.get_text(strip=True) if location_el else ""
            return job_from_list_card(
                source=self.source_id,
                title=title,
                url=job_url,
                company=company,
                city=city,
                min_title_len=5,
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("Failed to parse StepStone article: %s", exc)
            return None

    def normalize(self, raw: Any) -> Job | None:
        return job_from_job_posting(raw if isinstance(raw, dict) else {}, source=self.source_id)
