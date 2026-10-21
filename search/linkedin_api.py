"""LinkedIn public job search (the guest pages, no login, no bypass).

Own implementation of reading ``/jobs-guest/jobs/api/seeMoreJobPostings/search`` result cards. The endpoint and the
card markup are the ones the open-source JobSpy project (MIT License, Copyright (c) 2023 Cullen Watson) documented;
see NOTICE. Pages are fetched slowly (3 to 7 seconds apart) and the search stops at the first block.
"""
from __future__ import annotations

import logging
import random
import re
import time
from datetime import date
from typing import Any
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger("karrierekrake")

BASE_URL = "https://www.linkedin.com"
SEARCH_URL = f"{BASE_URL}/jobs-guest/jobs/api/seeMoreJobPostings/search"
PAGE_SIZE = 10
MAX_START = 1000
EMPTY_PAGE = "<!DOCTYPE html>\n\n<!---->"
TIMEOUT = 25
KM_PER_MILE = 1.609344
HEADERS = {
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "accept-language": "en-US,en;q=0.9",
    "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36",
}
REMOTE_WORDS = ("remote", "work from home", "wfh", "homeoffice", "home office")


def _text(node: Any) -> str:
    return " ".join(node.get_text(" ", strip=True).split()) if node is not None else ""


def row_from_card(card: Any, job_id: str) -> dict[str, Any]:
    title = _text(card.find("h3", class_="base-search-card__title"))
    subtitle = card.find("h4", class_="base-search-card__subtitle")
    location = _text(card.find("span", class_="job-search-card__location"))
    try:
        posted = date.fromisoformat(card.find("time")["datetime"])
    except (TypeError, KeyError, ValueError):
        posted = None
    return {
        "id": f"li-{job_id}", "title": title, "company": _text(subtitle), "location": location,
        "job_url": f"{BASE_URL}/jobs/view/{job_id}", "date_posted": posted, "description": "",
        "is_remote": any(word in f"{title} {location}".lower() for word in REMOTE_WORDS),
    }


def fetch_details(session: requests.Session, job_id: str) -> dict[str, Any]:
    """The job page's description and employment type; empty when the page cannot be read."""
    try:
        response = session.get(f"{BASE_URL}/jobs/view/{job_id}", timeout=TIMEOUT)
    except requests.RequestException as exc:
        logger.warning("LinkedIn: job %s: %s", job_id, exc)
        return {}
    if response.status_code != 200 or not urlparse(str(getattr(response, "url", ""))).path.startswith("/jobs/view/"):
        return {}
    soup = BeautifulSoup(response.text, "html.parser")
    block = soup.find("div", class_="show-more-less-html__markup")
    heading = soup.find("h3", class_="description__job-criteria-subheader",
                        string=lambda text: bool(text) and "Employment type" in text)
    value = heading.find_next_sibling("span", class_="description__job-criteria-text") if heading else None
    return {"description": block.decode_contents() if block else "", "job_type": _text(value)}


def search(*, term: str, location: str, radius_km: float, results_wanted: int, hours_old: int | None,
           fetch_description: bool = False, session: requests.Session | None = None) -> list[dict]:
    params: dict[str, Any] = {"keywords": term, "location": location,
                              "distance": max(0, round((radius_km or 0) / KM_PER_MILE))}
    if hours_old:
        params["f_TPR"] = f"r{int(hours_old) * 3600}"
    params = {name: value for name, value in params.items() if value not in (None, "")}
    own_session = session is None
    session = session or requests.Session()
    session.headers.update(HEADERS)
    rows: list[dict] = []
    seen: set[str] = set()
    start = 0
    try:
        while len(rows) < results_wanted and start < MAX_START:
            if start:
                time.sleep(random.uniform(3, 7))
            response = session.get(SEARCH_URL, params={**params, "start": start}, timeout=TIMEOUT)
            if response.status_code != 200:
                raise requests.HTTPError(f"LinkedIn HTTP {response.status_code}", response=response)
            cards = BeautifulSoup(response.text, "html.parser").find_all(class_="base-search-card")
            if not cards:
                if response.text.strip() != EMPTY_PAGE:
                    raise requests.HTTPError("LinkedIn: unexpected page without jobs (blocked?)", response=response)
                break
            fresh = []
            for card in cards:
                job_id = re.sub(r"^.*:", "", card.get("data-entity-urn", ""))
                if job_id and job_id not in seen:
                    seen.add(job_id)
                    fresh.append((job_id, card))
            for job_id, card in fresh:
                try:
                    row = row_from_card(card, job_id)
                except (AttributeError, TypeError, ValueError) as exc:
                    logger.warning("LinkedIn: skipping a job: %s", exc)
                    continue
                if fetch_description:
                    row.update(fetch_details(session, job_id))
                rows.append(row)
                if len(rows) >= results_wanted:
                    break
            if not fresh or len(cards) < PAGE_SIZE:
                break
            start += PAGE_SIZE
    finally:
        if own_session:
            session.close()
    return rows
