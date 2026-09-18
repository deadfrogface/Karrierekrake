"""Bundesagentur für Arbeit / Jobsuche adapter (API v6).

Adapted from JobRadar arbeitsagentur patterns (GPL-3.0) and updated to the
public Jobsuche OpenAPI (bund.dev / bundesAPI): list via /pc/v6/jobs,
details via /pc/v4/jobdetails/{base64(refnr)}.
"""

from __future__ import annotations

import base64
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

from core.cancel import (
    current_cancel_generation,
    register_executor,
    searches_cancelled,
    unregister_executor,
)
from typing import Any

import httpx

from core.deduplicator import make_job_id
from core.models import Job, RemoteType
from search.base import JobSource, SearchQuery

logger = logging.getLogger("karrierekrake")

_BASE = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service"
_LIST_URL = f"{_BASE}/pc/v6/jobs"
_DETAIL_URL = f"{_BASE}/pc/v4/jobdetails"
_API_KEY = "jobboerse-jobsuche"
_PAGE_SIZE = 25
_DETAIL_WORKERS = 8
_HEADERS = {
    "X-API-Key": _API_KEY,
    "Accept": "application/json",
    "User-Agent": "Karrierekrake/1.0 (local personal use)",
}


def _truthy_flag(value: object) -> bool:
    if value is True:
        return True
    if value is False or value is None:
        return False
    if isinstance(value, (int, float)):
        return value != 0
    text = str(value).strip().lower()
    if text in {"", "0", "false", "nein", "no", "n"}:
        return False
    if text in {"1", "true", "ja", "yes", "y"}:
        return True
    # Non-empty opaque API strings (e.g. "teilweise") count as offered.
    return bool(text)


def _detect_remote(item: dict, text: str = "") -> str:
    homeoffice_flag = _truthy_flag(
        item.get("homeofficemoeglich") if "homeofficemoeglich" in item else item.get("homeoffice")
    )
    blob = (text or "").lower()
    # Normalize common DE spellings before substring checks.
    blob_norm = (
        blob.replace("home-office", "homeoffice")
        .replace("home office", "homeoffice")
        .replace("homeoffice", "homeoffice")
    )
    # Explicit negations beat loose "homeoffice"/"remote" substrings.
    if re.search(
        r"\b(?:kein|keine|ohne|nicht|no)\s+(?:homeoffice|home[\s\-]?office|remote|telearbeit)\b",
        blob_norm,
    ):
        return RemoteType.ONSITE.value
    # Remote-Desktop / remote access tooling is not a remote job.
    remote_tooling = bool(
        re.search(r"\bremote[\s\-_]?(?:desktop|access|support|verwaltung)\b", blob_norm)
    )
    full_remote = any(
        x in blob_norm
        for x in ("100%", "vollständig remote", "remote only", "rein remote", "100% remote")
    )
    if full_remote and not remote_tooling:
        return RemoteType.REMOTE.value
    mentions_remote = homeoffice_flag or any(
        tok in blob_norm
        for tok in ("homeoffice", "telearbeit", "telecommute", "mobil arbeiten")
    ) or (bool(re.search(r"\bremote\b", blob_norm)) and not remote_tooling)
    mentions_hybrid = "hybrid" in blob_norm or (
        mentions_remote and any(tok in blob_norm for tok in ("tage", "teilweise", "anteil"))
    )
    if mentions_hybrid:
        return RemoteType.HYBRID.value
    if mentions_remote:
        return RemoteType.REMOTE.value
    return RemoteType.ONSITE.value


def _employment_type(item: dict) -> str:
    if item.get("arbeitszeitVollzeit"):
        return "fulltime"
    if any(
        item.get(k)
        for k in (
            "arbeitszeitTeilzeitFlexibel",
            "arbeitszeitTeilzeitVormittag",
            "arbeitszeitTeilzeitNachmittag",
            "arbeitszeitTeilzeitAbend",
        )
    ):
        return "parttime"
    return ""


class BundesagenturSource(JobSource):
    source_id = "bundesagentur"

    def health_check(self) -> tuple[bool, str]:
        try:
            with httpx.Client(timeout=8.0, headers=_HEADERS) as client:
                r = client.get(_LIST_URL, params={"page": 1, "size": 1, "was": "test"})
                if r.status_code >= 500:
                    return False, f"BA API HTTP {r.status_code}"
                return True, f"ok (HTTP {r.status_code})"
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)

    def search(self, queries: list[SearchQuery]) -> list[Job]:
        if not queries:
            raise ValueError("empty query list — refusing Bundesagentur search")
        all_jobs: list[Job] = []
        seen: set[str] = set()
        errors: list[str] = []
        for query in queries:
            try:
                batch = self._search_one(query)
            except Exception as exc:
                logger.error("Bundesagentur query '%s' failed: %s", query.keyword, exc)
                errors.append(f"{query.keyword}: {exc}")
                continue
            for job in batch:
                if job.id not in seen:
                    seen.add(job.id)
                    all_jobs.append(job)
        # If every query failed, do NOT pretend this was a successful empty result.
        if not all_jobs and errors and len(errors) == len(queries):
            raise RuntimeError("; ".join(errors[:3]))
        return all_jobs

    def _search_one(self, query: SearchQuery) -> list[Job]:
        location = query.location
        is_remote_query = location.lower() in {"remote", "deutschland remote"}
        if is_remote_query:
            # BA v6 rejects empty `wo`; search DE-wide and keep remote/hybrid locally.
            location = "Deutschland"
        params = {
            "was": query.keyword,
            "wo": location,
            "umkreis": 0 if location.lower() in {"deutschland", "germany"} else int(query.radius_km),
            "size": min(_PAGE_SIZE, query.max_results),
            "page": 1,
            "veroeffentlichtseit": query.published_within_days,
        }
        stubs: list[Job] = []
        with httpx.Client(timeout=30.0, headers=_HEADERS) as client:
            while len(stubs) < query.max_results:
                resp = client.get(_LIST_URL, params=params)
                resp.raise_for_status()
                data = resp.json()
                page_items = data.get("ergebnisliste") or data.get("stellenangebote") or []
                if not page_items:
                    break
                for item in page_items:
                    job = self.normalize(item)
                    if job:
                        stubs.append(job)
                total = data.get("maxErgebnisse", 0)
                if len(stubs) >= total or len(stubs) >= query.max_results:
                    break
                params["page"] += 1

        stubs = stubs[: query.max_results]
        if is_remote_query:
            stubs = [j for j in stubs if j.remote_type in ("remote", "hybrid")]
        logger.info("Bundesagentur: %d stubs for '%s' — enriching", len(stubs), query.keyword)
        with httpx.Client(timeout=15.0, headers=_HEADERS) as detail_client:
            return self._fetch_details(stubs, detail_client)

    def normalize(self, raw: Any) -> Job | None:
        try:
            item = raw if isinstance(raw, dict) else {}
            ref_nr = str(item.get("referenznummer") or item.get("refnr") or "")
            locs = item.get("stellenlokationen") or []
            loc0 = locs[0] if locs else {}
            addr = loc0.get("adresse") or {}
            city = addr.get("ort") or ""
            postal = str(addr.get("plz") or "")
            region = addr.get("region") or ""
            address_parts = [p for p in (postal, city, region) if p]
            url = item.get("externeURL") or item.get("externeUrl") or ""
            if not url and ref_nr:
                url = f"https://www.arbeitsagentur.de/jobsuche/jobdetail/{ref_nr}"
            lat = loc0.get("breite")
            lon = loc0.get("laenge")
            distance = item.get("entfernung")
            published = ""
            if isinstance(item.get("veroeffentlichungszeitraum"), dict):
                published = str(item["veroeffentlichungszeitraum"].get("von") or "")
            published = published or str(item.get("datumErsteVeroeffentlichung") or "")

            job = Job(
                id=make_job_id("bundesagentur", ref_nr, url),
                source="bundesagentur",
                source_job_id=ref_nr,
                title=item.get("stellenangebotsTitel") or item.get("titel") or "",
                company=item.get("firma") or item.get("arbeitgeber") or "",
                description=item.get("hauptberuf") or item.get("beruf") or "",
                city=city,
                postal_code=postal,
                address=", ".join(address_parts),
                country_code="DE",  # BA Jobsuche is DE-scoped
                latitude=float(lat) if lat is not None else None,
                longitude=float(lon) if lon is not None else None,
                distance_km=float(distance) if distance is not None else None,
                remote_type=_detect_remote(item),
                employment_type=_employment_type(item),
                published_at=published,
                url=url,
                application_url=url,
            )
            return job
        except Exception as exc:
            logger.warning("Failed to parse BA stub: %s", exc)
            return None

    def _fetch_details(self, stubs: list[Job], client: httpx.Client) -> list[Job]:
        if not stubs:
            return stubs

        def enrich(job: Job) -> Job:
            ref = job.source_job_id
            if not ref:
                return job
            enc = base64.b64encode(ref.encode("utf-8")).decode("ascii")
            try:
                resp = client.get(f"{_DETAIL_URL}/{enc}")
                resp.raise_for_status()
                detail = resp.json()
            except Exception as exc:
                logger.debug("Detail fetch failed for %s: %s", ref, exc)
                return job

            parts = []
            for key in (
                "stellenbeschreibung",
                "aufgaben",
                "anforderungen",
                "angebote",
                "stellenbeschreibungHtml",
            ):
                val = detail.get(key, "")
                if val:
                    parts.append(str(val))
            # v6 detail alternate keys
            for key in ("beschreibung", "taetigkeit", "qualifikation"):
                val = detail.get(key)
                if isinstance(val, str) and val.strip():
                    parts.append(val)
                elif isinstance(val, dict):
                    for sub in val.values():
                        if isinstance(sub, str) and sub.strip():
                            parts.append(sub)
            if parts:
                job.description = "\n\n".join(parts)
            lohn = detail.get("verguetung") or detail.get("gehalt") or {}
            if isinstance(lohn, dict):
                low, high, cur = lohn.get("von"), lohn.get("bis"), lohn.get("waehrung", "EUR")
                if low or high:
                    job.salary_text = f"{low or '?'} – {high or '?'} {cur}"
                    try:
                        job.salary_min = float(low) if low is not None else None
                        job.salary_max = float(high) if high is not None else None
                    except (TypeError, ValueError):
                        pass
            job.remote_type = _detect_remote(detail, job.description)
            return job

        order = {job.id: idx for idx, job in enumerate(stubs)}
        enriched: list[Job] = []
        gen = current_cancel_generation()
        if searches_cancelled(gen):
            return stubs
        pool = ThreadPoolExecutor(max_workers=_DETAIL_WORKERS)
        register_executor(pool)
        try:
            futures = {}
            for job in stubs:
                if searches_cancelled(gen):
                    break
                futures[pool.submit(enrich, job)] = job
            for fut in as_completed(futures):
                if searches_cancelled(gen):
                    for pending in futures:
                        pending.cancel()
                    break
                try:
                    enriched.append(fut.result())
                except Exception as exc:
                    logger.warning("Enrichment error: %s", exc)
                    enriched.append(futures[fut])
        finally:
            unregister_executor(pool)
            pool.shutdown(wait=False, cancel_futures=True)
        enriched.sort(key=lambda j: order.get(j.id, 9999))
        return enriched
