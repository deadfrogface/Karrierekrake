"""StepStone: public search result pages.

Written for Karrierekrake from what the public pages carry: schema.org ``JobPosting`` JSON-LD where the page
has it, otherwise the visible result cards (``article`` elements with a link to ``/stellenangebote--``, the
company and the place in their ``data-at`` marked spans).
"""
from __future__ import annotations

import logging
from typing import Any

import httpx
from bs4 import BeautifulSoup

from core.models import Job
from search.base import JobSource, SearchQuery
from search.jsonld import iter_job_postings, job_from_job_posting, job_from_list_card
from search.portal_html import (
    BROWSER_HEADERS,
    absolute,
    clean_text,
    json_ld_payloads,
    run_queries,
    slug,
)

logger = logging.getLogger("karrierekrake")

_BASE = "https://www.stepstone.de"
_HEADERS = dict(BROWSER_HEADERS)
_PAGE_LIMIT = 3
_TIMEOUT = 20.0
_CARD_SELECTOR = ('article[data-testid="job-item"], article[data-at="job-item"], article[id^="job-item"], '
                  "article:has(a[href*='stellenangebote--'])")


class StepstoneSource(JobSource):
    source_id = "stepstone"

    def health_check(self) -> tuple[bool, str]:
        try:
            with httpx.Client(timeout=10.0, headers=_HEADERS, follow_redirects=True) as client:
                client.get(_BASE + "/jobs/sachbearbeiter").raise_for_status()
            return True, "ok"
        except Exception as exc:  # noqa: BLE001 - a failed probe, not a crash
            return False, f"StepStone nicht erreichbar: {type(exc).__name__}"

    def search(self, queries: list[SearchQuery]) -> list[Job]:
        return run_queries(self.source_id, queries, self._search_one)

    def _search_one(self, query: SearchQuery) -> list[Job]:
        wanted = max(1, int(query.max_results or 50))
        path = f"{_BASE}/jobs/{slug(query.keyword) or 'jobs'}"
        if (query.location or "").strip():
            path += f"/in-{slug(query.location)}"
        jobs: dict[str, Job] = {}
        with httpx.Client(timeout=_TIMEOUT, headers=_HEADERS, follow_redirects=True) as client:
            for page in range(1, _PAGE_LIMIT + 1):
                params: dict[str, Any] = {"sort": 2, "action": "sort_publish"}
                if (query.location or "").strip():
                    params["radius"] = max(5, int(query.radius_km or 0))
                if page > 1:
                    params["page"] = page
                response = client.get(path, params=params)
                response.raise_for_status()
                fresh = [job for job in self._parse_page(BeautifulSoup(response.text, "lxml")) if job.url not in jobs]
                if not fresh:
                    break
                jobs.update((job.url, job) for job in fresh)
                if len(jobs) >= wanted:
                    break
        return list(jobs.values())[:wanted]

    def _parse_page(self, soup: BeautifulSoup) -> list[Job]:
        found: list[Job] = []
        for payload in json_ld_payloads(soup):
            for item in iter_job_postings(payload):
                item = dict(item)
                item["url"] = absolute(_BASE, item.get("url"))
                job = job_from_job_posting(item, source=self.source_id) if item["url"] else None
                if job is not None:
                    found.append(job)
        if found:
            return found
        for article in soup.select(_CARD_SELECTOR):
            job = self._parse_article(article)
            if job is not None:
                found.append(job)
        return found

    def _parse_article(self, article: Any) -> Job | None:
        link = article.select_one("a[href*='stellenangebote--']") or article.select_one("h2 a, h3 a, a[href]")
        if link is None:
            return None
        heading = article.select_one('[data-at="job-item-title"], h2, h3')
        return job_from_list_card(
            source=self.source_id,
            title=clean_text(heading) or clean_text(link),
            url=absolute(_BASE, link.get("href")),
            company=clean_text(article.select_one('[data-at="job-item-company-name"]')),
            city=clean_text(article.select_one('[data-at="job-item-location"]')),
            description=clean_text(article.select_one('[data-at="jobcard-content"], [data-at="job-item-content"]')),
        )

    def normalize(self, raw: Any) -> Job | None:
        return job_from_job_posting(raw if isinstance(raw, dict) else {}, source=self.source_id)
