"""Full ad text for a job whose search result carried only a short snippet or none.

XING and StepStone list pages give a title and a teaser. Writing an application needs the whole ad, so it is read
once from the ad's own page (its schema.org ``JobPosting`` data) when the person prepares an application, and stored
with the job. LinkedIn is left out on purpose: its terms rule out fetching job pages (see docs/privacy).
"""
from __future__ import annotations

import logging
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from core.models import Job
from search.job_schema import strip_markup
from search.jsonld import iter_job_postings
from search.portal_html import json_ld_payloads

logger = logging.getLogger("karrierekrake")

FETCHABLE = {"xing": {"www.xing.com"}, "stepstone": {"www.stepstone.de"}}
MIN_FULL_AD_CHARS = 500
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/124.0 Safari/537.36",
    "Accept-Language": "de-DE,de;q=0.9,en;q=0.5",
}


def needs_full_text(job: Job) -> bool:
    return (job.source in FETCHABLE and len((job.description or "").strip()) < MIN_FULL_AD_CHARS
            and bool(job.url))


def fetch_full_description(job: Job, *, timeout: float = 12.0, session: requests.Session | None = None) -> str:
    """The ad text from the job's page, or "" when the page cannot be read (nothing is invented)."""
    parsed = urlparse(job.url or "")
    if parsed.scheme != "https" or parsed.hostname not in FETCHABLE.get(job.source, set()):
        return ""
    try:
        response = (session or requests).get(job.url, headers=_HEADERS, timeout=timeout, allow_redirects=True)
        response.raise_for_status()
        final = urlparse(response.url)
        if final.scheme != "https" or final.hostname not in FETCHABLE[job.source]:
            return ""
        soup = BeautifulSoup(response.content, "html.parser")  # bytes: the parser finds the real encoding
        postings = [p for payload in json_ld_payloads(soup) for p in iter_job_postings(payload)]
    except (requests.RequestException, ValueError) as exc:
        logger.info("job_detail %s failed: %s", job.source, type(exc).__name__)
        return ""
    for posting in postings:
        text = strip_markup(posting.get("description") or "", keep_lines=True)
        if text.lower().startswith("null\n") or text.lower().startswith("null "):
            text = text[4:].lstrip()
        if len(text) >= 80:
            return text
    return ""
