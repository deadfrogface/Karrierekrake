"""Small shared helpers for the HTML job portals (StepStone, XING)."""
from __future__ import annotations

import json
import logging
import re
import unicodedata
import urllib.parse
from collections.abc import Callable
from typing import Any

from bs4 import BeautifulSoup

from core.cancel import current_cancel_generation, searches_cancelled
from core.models import Job
from search.base import PartialResultsError, SearchQuery, is_source_blocked

logger = logging.getLogger("karrierekrake")

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/124.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "de-DE,de;q=0.9,en;q=0.6",
}


def slug(text: str) -> str:
    """URL path slug: lower case, umlauts transliterated, words joined by hyphens."""
    text = (text or "").casefold().replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def json_ld_payloads(soup: BeautifulSoup) -> list[Any]:
    """All parseable ``application/ld+json`` documents of a page (broken ones are skipped)."""
    payloads = []
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            payloads.append(json.loads(script.string or script.get_text()))
        except (ValueError, TypeError):
            continue
    return payloads


def absolute(base: str, link: Any) -> str:
    target = str(link or "").strip()
    if not target:
        return ""
    joined = urllib.parse.urljoin(base, target)
    return joined if urllib.parse.urlsplit(joined).scheme in {"http", "https"} else ""


def clean_text(node: Any) -> str:
    return " ".join(node.get_text(" ", strip=True).split()) if node is not None else ""


def raise_first(source_id: str, errors: list[Exception]) -> None:
    """Re-raise the first error; a block (403/429/captcha) becomes a RuntimeError the search guard understands."""
    first = errors[0]
    if is_source_blocked(first):
        raise RuntimeError(f"{source_id} blocked: {first}") from first
    raise first


def run_queries(source_id: str, queries: list[SearchQuery], search_one: Callable[[SearchQuery], list[Job]],
                *, max_queries: int = 6) -> list[Job]:
    """Run each query; one failing query keeps the others' jobs (``PartialResultsError``), a block stops early."""
    generation = current_cancel_generation()
    found: dict[str, Job] = {}
    errors: list[Exception] = []
    for query in list(queries or [])[:max_queries]:
        if searches_cancelled(generation):
            break
        try:
            for job in search_one(query):
                found.setdefault(job.id, job)
        except Exception as exc:  # noqa: BLE001 - isolate one query's failure
            logger.warning("%s query %r failed: %s", source_id, query.keyword, exc)
            errors.append(exc)
            if is_source_blocked(exc):
                break
    jobs = list(found.values())
    if errors and jobs:
        raise PartialResultsError(jobs, f"{len(errors)} Suchen fehlgeschlagen: {errors[0]}")
    if errors:
        raise_first(source_id, errors)
    return jobs
