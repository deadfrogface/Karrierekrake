"""Indeed job search through Indeed's mobile-app GraphQL endpoint.

Own implementation. The endpoint, the public app key and the request headers are the ones the open-source
JobSpy project (MIT License, Copyright (c) 2023 Cullen Watson) documented; see NOTICE. One session, plain
``requests``, no browser fingerprinting.
"""
from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

import requests

logger = logging.getLogger("karrierekrake")

API_URL = "https://apis.indeed.com/graphql"
PAGE_SIZE = 100
TIMEOUT = 25
KM_PER_MILE = 1.609344
# Indeed's own attribute keys for work model and job type.
REMOTE_KEY = "DSQF7"
HYBRID_KEY = "PAXZC"
JOB_TYPES = {"CF3CP": "fulltime", "75GKK": "parttime", "NJXCK": "contract", "T9BXE": "contract", "T65DZ": "contract",
             "VDTG7": "internship", "4HKF7": "temporary", "CJWTS": "temporary", "TQKYQ": "perdiem", "UXQZ8": "volunteer"}
PAY_INTERVALS = {"HOUR": "hourly", "DAY": "daily", "WEEK": "weekly", "MONTH": "monthly", "YEAR": "yearly"}
# country (as used by Indeed and our settings) -> (domain, ISO code, language)
COUNTRIES = {
    "germany": ("de", "DE", "de"), "austria": ("at", "AT", "de"), "switzerland": ("ch", "CH", "de"),
    "netherlands": ("nl", "NL", "nl"), "belgium": ("be", "BE", "nl"), "luxembourg": ("lu", "LU", "fr"),
}
COUNTRY_NAMES = {"DE": "Germany", "AT": "Austria", "CH": "Switzerland", "NL": "Netherlands", "BE": "Belgium",
                 "LU": "Luxembourg"}
HEADERS = {
    "content-type": "application/json",
    "indeed-api-key": "161092c2017b5bbab13edb12461a62d5a833871e7cad6d9d475304573de67ac8",
    "accept": "application/json",
    "accept-language": "en-US,en;q=0.9",
    "user-agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6_1 like Mac OS X) AppleWebKit/605.1.15 "
                  "(KHTML, like Gecko) Mobile/15E148 Indeed App 193.1",
    "indeed-app-info": "appv=193.1; appid=com.indeed.jobsearch; osv=16.6.1; os=ios; dtype=phone",
}

_RANGE = "range { ... on Range { min max } ... on AtLeast { min } ... on AtMost { max } ... on Exactly { value } }"
_QUERY = """query GetJobData {
  jobSearch(%(what)s %(where)s limit: %(limit)d %(cursor)s sort: RELEVANCE %(filters)s) {
    pageInfo { nextCursor }
    results { job {
      key title sourceEmployerName dateOnIndeed
      description { html }
      location { countryCode admin1Code city }
      compensation {
        estimated { currencyCode baseSalary { unitOfWork %(range)s } }
        baseSalary { unitOfWork %(range)s }
        currencyCode
      }
      attributes { key label }
      employer { name }
      recruit { viewJobUrl }
    } }
  }
}"""


def _attribute(key: str, match: str = "") -> str:
    return f'{{ keyword: {{ field: "attributes", keys: ["{key}"]{match} }} }}'


def build_query(*, term: str, location: str, radius_miles: int, hours_old: int | None, remote_only: bool,
                cursor: str | None) -> str:
    filters = []
    if hours_old:
        filters.append(f'{{ date: {{ field: "dateOnIndeed", start: "{int(hours_old)}h" }} }}')
    if remote_only:
        filters.append(_attribute(REMOTE_KEY))
        filters.append(_attribute(HYBRID_KEY, ", match: MUST_NOT"))
    return _QUERY % {
        "what": f"what: {json.dumps(term, ensure_ascii=False)}" if term else "",
        "where": (f"location: {{where: {json.dumps(location, ensure_ascii=False)}, radius: {radius_miles}, "
                  "radiusUnit: MILES}") if location else "",
        "limit": PAGE_SIZE, "cursor": f'cursor: "{cursor}"' if cursor else "",
        "filters": f"filters: [{', '.join(filters)}]" if filters else "", "range": _RANGE,
    }


def _pay(compensation: dict) -> tuple[str, float | None, float | None, str]:
    """(interval, min, max, currency): the employer's pay, else Indeed's estimate."""
    pay = compensation.get("baseSalary")
    currency = compensation.get("currencyCode") or ""
    if not pay and compensation.get("estimated"):
        pay = compensation["estimated"].get("baseSalary")
        currency = compensation["estimated"].get("currencyCode") or currency
    interval = PAY_INTERVALS.get((pay or {}).get("unitOfWork", ""))
    if not interval:
        return "", None, None, currency
    amounts = pay.get("range") or {}
    low, high = amounts.get("min", amounts.get("value")), amounts.get("max", amounts.get("value"))
    return interval, (round(low, 2) if low is not None else None), (round(high, 2) if high is not None else None), currency


def row_from_job(job: dict, domain: str) -> dict[str, Any]:
    """One GraphQL job -> the flat row the Indeed adapter normalizes."""
    location = job.get("location") or {}
    code = location.get("countryCode") or ""
    attributes = {a.get("key") for a in job.get("attributes") or []}
    apply_url = ((job.get("recruit") or {}).get("viewJobUrl")) or ""
    if f".{urlsplit(apply_url).hostname}".endswith(".indeed.com"):
        apply_url = ""
    interval, low, high, currency = _pay(job.get("compensation") or {})
    posted = job.get("dateOnIndeed")
    return {
        "id": f"in-{job['key']}", "title": job.get("title") or "",
        "company": (job.get("employer") or {}).get("name") or job.get("sourceEmployerName") or "",
        "location": ", ".join(p for p in (location.get("city"), COUNTRY_NAMES.get(code, code)) if p),
        "description": ((job.get("description") or {}).get("html")) or "",
        "job_url": f"https://{domain}.indeed.com/viewjob?jk={job['key']}", "job_url_direct": apply_url,
        "date_posted": datetime.fromtimestamp(posted / 1000, UTC).date() if posted else None,
        "job_type": [JOB_TYPES[k] for k in sorted(attributes) if k in JOB_TYPES],
        "is_remote": REMOTE_KEY in attributes and HYBRID_KEY not in attributes,
        "interval": interval, "min_amount": low, "max_amount": high, "currency": currency,
    }


def search(*, term: str, location: str, radius_km: float, results_wanted: int, hours_old: int | None,
           country: str = "germany", remote_only: bool = False, session: requests.Session | None = None) -> list[dict]:
    domain, code, language = COUNTRIES.get((country or "").lower(), COUNTRIES["germany"])
    headers = {**HEADERS, "indeed-co": code, "indeed-locale": f"{language}-{code}"}
    miles = max(0, round((radius_km or 0) / KM_PER_MILE)) or 31
    own_session = session is None
    session = session or requests.Session()
    rows: list[dict] = []
    seen: set[str] = set()
    cursor = None
    try:
        while len(rows) < results_wanted:
            response = session.post(
                API_URL, headers=headers, timeout=TIMEOUT,
                json={"query": build_query(term=term, location=location, radius_miles=miles, hours_old=hours_old,
                                           remote_only=remote_only, cursor=cursor)})
            if response.status_code != 200:
                raise requests.HTTPError(f"Indeed HTTP {response.status_code}", response=response)
            search_data = (response.json().get("data") or {}).get("jobSearch")
            if not search_data:
                break
            fresh = [r["job"] for r in search_data.get("results") or [] if r.get("job") and r["job"]["key"] not in seen]
            seen.update(job["key"] for job in fresh)
            for job in fresh:
                try:
                    rows.append(row_from_job(job, domain))
                except (KeyError, TypeError, ValueError) as exc:
                    logger.warning("Indeed: skipping a job: %s", exc)
                if len(rows) >= results_wanted:
                    break
            cursor = (search_data.get("pageInfo") or {}).get("nextCursor")
            if not fresh or not cursor:
                break
    finally:
        if own_session:
            session.close()
    return rows
