"""XING Jobs: public search result pages.

Written for Karrierekrake from what the public pages carry: schema.org ``JobPosting`` JSON-LD (single
postings or an ``ItemList``) where the page has it, otherwise result links to ``/jobs/<place>-<title>-<id>``
with their company and place text.
"""
from __future__ import annotations

import logging
import re
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
)

logger = logging.getLogger("karrierekrake")

_BASE = "https://www.xing.com"
_SEARCH_URL = f"{_BASE}/jobs/search"
_HEADERS = dict(BROWSER_HEADERS)
_MIN_TITLE_LEN = 8
_TIMEOUT = 20.0
_JOB_LINK = re.compile(r"/jobs/(?!search\b)[^/?#]+-\d{4,}")


class XingSource(JobSource):
    source_id = "xing"

    def health_check(self) -> tuple[bool, str]:
        try:
            with httpx.Client(timeout=10.0, headers=_HEADERS, follow_redirects=True) as client:
                client.get(_SEARCH_URL, params={"keywords": "sachbearbeiter"}).raise_for_status()
            return True, "ok"
        except Exception as exc:  # noqa: BLE001 - a failed probe, not a crash
            return False, f"XING nicht erreichbar: {type(exc).__name__}"

    def search(self, queries: list[SearchQuery]) -> list[Job]:
        return run_queries(self.source_id, queries, self._search_one)

    def _search_one(self, query: SearchQuery) -> list[Job]:
        wanted = max(1, int(query.max_results or 50))
        params: dict[str, Any] = {"keywords": query.keyword}
        if (query.location or "").strip():
            params["location"] = query.location
            params["radius"] = max(5, int(query.radius_km or 0))
        with httpx.Client(timeout=_TIMEOUT, headers=_HEADERS, follow_redirects=True) as client:
            response = client.get(_SEARCH_URL, params=params)
            response.raise_for_status()
            jobs = self._parse_page(BeautifulSoup(response.text, "lxml"))
        return jobs[:wanted]

    def _parse_page(self, soup: BeautifulSoup) -> list[Job]:
        found: dict[str, Job] = {}
        for payload in json_ld_payloads(soup):
            for item in iter_job_postings(payload):
                item = dict(item)
                item["url"] = absolute(_BASE, item.get("url"))
                job = (job_from_job_posting(item, source=self.source_id, min_title_len=_MIN_TITLE_LEN)
                       if item["url"] else None)
                if job is not None:
                    found.setdefault(job.url, job)
        if found:
            return list(found.values())
        for card in soup.select("article, li"):
            job = self._parse_card(card)
            if job is not None:
                found.setdefault(job.url, job)
        return list(found.values())

    def _parse_card(self, card: Any) -> Job | None:
        link = next((a for a in card.select("a[href]") if _JOB_LINK.search(a.get("href", ""))), None)
        if link is None:
            return None
        company = card.select_one('[data-testid*="company"], [class*="company"]')
        place = card.select_one('[data-testid*="location"], [class*="location"]')
        heading = card.select_one("h2, h3")
        return job_from_list_card(
            source=self.source_id, title=clean_text(heading) or clean_text(link),
            url=absolute(_BASE, link.get("href")), company=clean_text(company), city=clean_text(place),
            min_title_len=_MIN_TITLE_LEN,
        )

    def normalize(self, raw: Any) -> Job | None:
        return job_from_job_posting(raw if isinstance(raw, dict) else {}, source=self.source_id,
                                    min_title_len=_MIN_TITLE_LEN)
