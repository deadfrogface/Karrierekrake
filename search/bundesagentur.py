"""Bundesagentur für Arbeit: Jobsuche (public job exchange API).

Written for Karrierekrake from the public API description (github.com/bundesAPI/jobsuche-api):
``GET /pc/v6/jobs`` searches, ``GET /pc/v4/jobdetails/{base64(refnr)}`` returns one posting. Both are
called with the published client id in the ``X-API-Key`` header.
"""
from __future__ import annotations

import base64
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import httpx

from core.cancel import (
    current_cancel_generation,
    register_executor,
    searches_cancelled,
    unregister_executor,
)
from core.deduplicator import make_job_id
from core.models import Job
from search.base import JobSource, PartialResultsError, SearchQuery, is_source_blocked
from search.job_schema import normalize_portal_job, strip_markup
from search.remote_text import classify_remote, truthy_flag

logger = logging.getLogger("karrierekrake")

_BASE = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service"
_LIST_URL = f"{_BASE}/pc/v6/jobs"
_DETAIL_URL = f"{_BASE}/pc/v4/jobdetails"
_API_KEY = "jobboerse-jobsuche"
_PAGE_SIZE = 25
_DETAIL_WORKERS = 8
_TIMEOUT = 20.0
_HEADERS = {"X-API-Key": _API_KEY, "Accept": "application/json", "User-Agent": "Karrierekrake/1.0"}
_PUBLIC_URL = "https://www.arbeitsagentur.de/jobsuche/jobdetail/"

_WORKING_TIME = {"VOLLZEIT": "Vollzeit", "TEILZEIT": "Teilzeit", "MINIJOB": "Minijob",
                 "HEIM_TELEARBEIT": "Heim-/Telearbeit", "SCHICHT_NACHTARBEIT_WOCHENENDE": "Schicht/Nacht/Wochenende"}


def _first(item: dict, *names: str) -> Any:
    for name in names:
        value = item.get(name)
        if value not in (None, "", [], {}):
            return value
    return None


def _detect_remote(item: dict, text: str = "") -> str:
    """Work model from the posting's text and its ``homeofficemoeglich`` flag (a bare True means hybrid)."""
    flag = truthy_flag(item.get("homeofficemoeglich")) if isinstance(item, dict) else None
    return classify_remote(text, flag=flag, flag_true="hybrid")


def _employment_type(item: dict) -> str:
    models = item.get("arbeitszeitmodelle")
    if isinstance(models, str):
        models = [models]
    labels = [_WORKING_TIME.get(str(m).upper(), str(m).title()) for m in models or [] if m]
    if labels:
        return ", ".join(labels)
    return strip_markup(_first(item, "arbeitszeit", "anstellungsart") or "")


def _places(item: dict) -> list[dict]:
    """All work places of a posting as flat dicts (ort, plz, strasse, land, lat, lon)."""
    raw: list[Any] = []
    if isinstance(item.get("arbeitsort"), dict):
        raw.append(item["arbeitsort"])
    raw.extend(p for p in item.get("arbeitsorte") or [] if isinstance(p, dict))
    for place in item.get("stellenlokationen") or []:
        if isinstance(place, dict):
            raw.append(place.get("adresse") if isinstance(place.get("adresse"), dict) else place)
    flat = []
    for place in raw:
        coords = place.get("koordinaten") if isinstance(place.get("koordinaten"), dict) else {}
        flat.append({"ort": place.get("ort") or "", "plz": str(place.get("plz") or ""),
                     "strasse": place.get("strasse") or place.get("strassenname") or "",
                     "land": place.get("land") or "", "lat": coords.get("lat"), "lon": coords.get("lon")})
    return flat


def _number(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


class BundesagenturSource(JobSource):
    source_id = "bundesagentur"

    def health_check(self) -> tuple[bool, str]:
        try:
            with httpx.Client(timeout=10.0, headers=_HEADERS) as client:
                response = client.get(_LIST_URL, params={"was": "Sachbearbeiter", "size": 1, "page": 1})
                response.raise_for_status()
            return True, "ok"
        except Exception as exc:  # noqa: BLE001 - any failure is a failed probe, not a crash
            return False, f"Bundesagentur nicht erreichbar: {type(exc).__name__}"

    def search(self, queries: list[SearchQuery]) -> list[Job]:
        generation = current_cancel_generation()
        found: dict[str, Job] = {}
        errors: list[Exception] = []
        for query in queries:
            if searches_cancelled(generation):
                break
            try:
                for job in self._search_one(query):
                    found.setdefault(job.id, job)
            except Exception as exc:  # noqa: BLE001 - one failing query must not hide the others
                logger.warning("Bundesagentur query %r failed: %s", query.keyword, exc)
                errors.append(exc)
                if is_source_blocked(exc):
                    break
        jobs = list(found.values())
        if errors and jobs:
            raise PartialResultsError(jobs, f"{len(errors)} von {len(queries)} Suchen fehlgeschlagen: {errors[0]}")
        if errors:
            raise errors[0]
        return jobs

    def _search_one(self, query: SearchQuery) -> list[Job]:
        wanted = max(1, int(query.max_results or 50))
        params: dict[str, Any] = {"was": query.keyword, "angebotsart": 1,
                                  "veroeffentlichtseit": max(0, min(int(query.published_within_days or 14), 100))}
        if query.location:
            params["wo"] = query.location
            params["umkreis"] = max(0, int(query.radius_km or 0))
        generation = current_cancel_generation()
        stubs: list[Job] = []
        with httpx.Client(timeout=_TIMEOUT, headers=_HEADERS) as client:
            page = 1
            while len(stubs) < wanted and not searches_cancelled(generation):
                response = client.get(_LIST_URL, params={**params, "size": min(_PAGE_SIZE, wanted), "page": page})
                response.raise_for_status()
                rows = (response.json() or {}).get("stellenangebote") or []
                for row in rows:
                    job = self.normalize(row)
                    if job is not None:
                        stubs.append(job)
                if len(rows) < min(_PAGE_SIZE, wanted):
                    break
                page += 1
            return self._fetch_details(stubs[:wanted], client)

    def normalize(self, raw: Any) -> Job | None:
        if not isinstance(raw, dict):
            return None
        refnr = str(_first(raw, "refnr", "referenznummer") or "")
        title = strip_markup(_first(raw, "titel", "stellenangebotsTitel", "beruf", "hauptberuf") or "")
        if not title:
            return None
        description = strip_markup(_first(raw, "stellenangebotsBeschreibung", "stellenbeschreibung", "hauptberuf",
                                          "beruf") or "", keep_lines=True)
        places = _places(raw)
        place = places[0] if places else {}
        url = str(_first(raw, "externeUrl") or (_PUBLIC_URL + refnr if refnr else ""))
        job = Job(
            id=make_job_id(self.source_id, refnr, url, title, str(_first(raw, "arbeitgeber", "firma") or "")),
            source=self.source_id, source_job_id=refnr, title=title,
            company=strip_markup(_first(raw, "arbeitgeber", "firma") or ""),
            description=description, city=str(place.get("ort") or ""), postal_code=str(place.get("plz") or ""),
            address=str(place.get("strasse") or ""), country_code="DE" if place and not place.get("land") else "",
            latitude=_number(place.get("lat")), longitude=_number(place.get("lon")),
            employment_type=_employment_type(raw),
            published_at=str(_first(raw, "aktuelleVeroeffentlichungsdatum", "ersteVeroeffentlichungsdatum") or ""),
            url=url, application_url=str(_first(raw, "externeUrl") or url),
        )
        job.remote_type = _detect_remote(raw, f"{title}\n{description}")
        if place.get("land") and "deutschland" in str(place["land"]).casefold():
            job.country_code = "DE"
        return normalize_portal_job(job)

    def _fetch_details(self, stubs: list[Job], client: httpx.Client) -> list[Job]:
        """Fill description and address from the detail endpoint; a failed detail keeps the stub."""
        if not stubs:
            return stubs
        generation = current_cancel_generation()

        def one(job: Job) -> Job:
            if not job.source_job_id or searches_cancelled(generation):
                return job
            token = base64.b64encode(job.source_job_id.encode()).decode()
            try:
                response = client.get(f"{_DETAIL_URL}/{token}")
                response.raise_for_status()
                detail = self.normalize({**(response.json() or {}), "refnr": job.source_job_id})
            except Exception as exc:
                if is_source_blocked(exc):
                    raise
                logger.info("Bundesagentur detail %s failed: %s", job.source_job_id, exc)
                return job
            if detail is None:
                return job
            for name in ("description", "address", "postal_code", "employment_type", "remote_type"):
                value = getattr(detail, name)
                if value and (not getattr(job, name) or name in {"description", "remote_type"}):
                    setattr(job, name, value)
            return job

        pool = ThreadPoolExecutor(max_workers=_DETAIL_WORKERS)
        register_executor(pool)
        try:
            return list(pool.map(one, stubs))
        finally:
            unregister_executor(pool)
            pool.shutdown(wait=False)
