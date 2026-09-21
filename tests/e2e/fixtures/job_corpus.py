"""Deterministic synthetic job corpus for product E2E (>=100 jobs)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from core.models import Job

_INTENT_CORPUS = Path(__file__).resolve().parents[2] / "fixtures" / "intent_jobs_corpus.json"

# Extra edge-case jobs beyond the intent corpus slice.
_EDGE_SPECS: list[dict[str, Any]] = [
    {"id": "JOB_EDGE_001", "title": "Lohnbuchhalter (m/w/d)", "company": "Nordlicht Beispiel GmbH", "city": "Berlin", "country_code": "DE", "remote_type": "hybrid", "ats_type": "personio", "match": "strong"},
    {"id": "JOB_EDGE_002", "title": "Payroll Specialist", "company": "Alpen HR AG", "city": "Zürich", "country_code": "CH", "remote_type": "onsite", "ats_type": "unknown", "match": "weak"},
    {"id": "JOB_EDGE_003", "title": "Sales Manager", "company": "Wrong Profession GmbH", "city": "München", "country_code": "DE", "remote_type": "remote", "ats_type": "greenhouse", "match": "wrong_profession"},
    {"id": "JOB_EDGE_004", "title": "Lohnbuchhalter", "company": "SAP Pflicht KG", "city": "Frankfurt", "country_code": "DE", "remote_type": "hybrid", "ats_type": "workday", "mandatory": ["SAP"], "match": "mandatory_ok"},
    {"id": "JOB_EDGE_005", "title": "Lohnbuchhalter", "company": "Ohne SAP GmbH", "city": "Köln", "country_code": "DE", "remote_type": "hybrid", "ats_type": "smartrecruiters", "mandatory_missing": ["SAP"], "match": "mandatory_missing"},
    {"id": "JOB_EDGE_006", "title": "Payroll only", "company": "PayrollOnly GmbH", "city": "Hamburg", "country_code": "DE", "remote_type": "remote", "ats_type": "personio", "match": "payroll_only"},
    {"id": "JOB_EDGE_007", "title": "Buchhalter Remote", "company": "Cloud Books GmbH", "city": "", "country_code": "DE", "remote_type": "remote", "ats_type": "unknown", "match": "remote"},
    {"id": "JOB_EDGE_008", "title": "Buchhalter Hybrid", "company": "Hybrid Office GmbH", "city": "Stuttgart", "country_code": "DE", "remote_type": "hybrid", "ats_type": "personio", "match": "hybrid"},
    {"id": "JOB_EDGE_009", "title": "Buchhalter vor Ort", "company": "Onsite Books GmbH", "city": "Düsseldorf", "country_code": "DE", "remote_type": "onsite", "ats_type": "successfactors", "match": "onsite"},
    {"id": "JOB_EDGE_010", "title": "Lohnverrechner", "company": "Wien Payroll GmbH", "city": "Wien", "country_code": "AT", "remote_type": "hybrid", "ats_type": "personio", "match": "at"},
    {"id": "JOB_EDGE_011", "title": "Lohnbuchhalter CH", "company": "Basel Books AG", "city": "Basel", "country_code": "CH", "remote_type": "onsite", "ats_type": "unknown", "match": "ch"},
    {"id": "JOB_EDGE_012", "title": "Grenzgänger Payroll", "company": "Bodensee Cross GmbH", "city": "Konstanz", "country_code": "DE", "remote_type": "hybrid", "ats_type": "personio", "match": "cross_border"},
    {"id": "JOB_EDGE_013", "title": "Lohnbuchhalter", "company": "Radius Innen GmbH", "city": "Berlin", "country_code": "DE", "distance_km": 5.0, "match": "inside_radius"},
    {"id": "JOB_EDGE_014", "title": "Lohnbuchhalter", "company": "Radius Außen GmbH", "city": "Rostock", "country_code": "DE", "distance_km": 250.0, "match": "outside_radius"},
    {"id": "JOB_EDGE_015", "title": "Lohnbuchhalter", "company": "Ort Unbekannt GmbH", "city": "", "country_code": "", "match": "unknown_location"},
    {"id": "JOB_EDGE_016", "title": "", "company": "", "city": "Berlin", "country_code": "DE", "match": "malformed"},
    {"id": "JOB_EDGE_017", "title": "Lohnbuchhalter", "company": "", "city": "Berlin", "country_code": "DE", "match": "missing_company"},
    {"id": "JOB_EDGE_018", "title": "Lohnbuchhalter", "company": "Ohne Gehalt GmbH", "city": "Berlin", "country_code": "DE", "salary_min": None, "match": "missing_salary"},
    {"id": "JOB_EDGE_019", "title": "Lohnbuchhalter", "company": "Ohne Ort GmbH", "city": "", "country_code": "DE", "match": "missing_location"},
    {"id": "JOB_EDGE_020", "title": "Lohnbuchhalter", "company": "Duplikat GmbH", "city": "Berlin", "country_code": "DE", "source": "fake_a", "match": "duplicate_a"},
    {"id": "JOB_EDGE_021", "title": "Lohnbuchhalter", "company": "Duplikat GmbH", "city": "Berlin", "country_code": "DE", "source": "fake_b", "match": "duplicate_b"},
    {"id": "JOB_EDGE_022", "title": "Teamassistenz", "company": "Multi Role AG", "city": "Berlin", "country_code": "DE", "match": "same_company_role_a"},
    {"id": "JOB_EDGE_023", "title": "Office Manager", "company": "Multi Role AG", "city": "Berlin", "country_code": "DE", "match": "same_company_role_b"},
    {"id": "JOB_EDGE_024", "title": "Lohnbuchhalter", "company": "Multi City GmbH", "city": "Berlin", "country_code": "DE", "match": "same_title_city_a"},
    {"id": "JOB_EDGE_025", "title": "Lohnbuchhalter", "company": "Multi City GmbH", "city": "Hamburg", "country_code": "DE", "match": "same_title_city_b"},
    {"id": "JOB_EDGE_026", "title": "Lohnbuchhalter", "company": "ATS Supported GmbH", "city": "Berlin", "country_code": "DE", "ats_type": "personio", "match": "ats_supported"},
    {"id": "JOB_EDGE_027", "title": "Lohnbuchhalter", "company": "ATS Unknown GmbH", "city": "Berlin", "country_code": "DE", "ats_type": "unknown", "match": "ats_unknown"},
    {"id": "JOB_EDGE_028", "title": "Lohnbuchhalter", "company": "Expired Listing GmbH", "city": "Berlin", "country_code": "DE", "published_at": "2020-01-01", "match": "expired"},
    {"id": "JOB_EDGE_029", "title": "Lohnbuchhalter", "company": "Repost GmbH", "city": "Berlin", "country_code": "DE", "published_at": "2026-09-01", "match": "reposted"},
    {"id": "JOB_EDGE_030", "title": "Lohnbuchhalter — " + ("sehr " * 40) + "langer Titel", "company": "Lange Firma " + ("X" * 80), "city": "Berlin", "country_code": "DE", "match": "very_long"},
]


def _stable_id(prefix: str, raw: str) -> str:
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}_{digest}"


def _job_from_intent_row(row: dict[str, Any], idx: int) -> Job:
    jid = str(row.get("id") or _stable_id("JOB", f"intent-{idx}"))
    return Job(
        id=jid,
        source=str(row.get("source") or "intent_corpus"),
        source_job_id=str(row.get("source_job_id") or jid),
        title=str(row.get("title") or ""),
        company=str(row.get("company") or ""),
        description=str(row.get("description") or ""),
        city=str(row.get("city") or row.get("location") or ""),
        country_code=str(row.get("country_code") or row.get("country") or "DE"),
        remote_type=str(row.get("remote_type") or row.get("remote") or ""),
        employment_type=str(row.get("employment_type") or ""),
        salary_min=row.get("salary_min"),
        salary_max=row.get("salary_max"),
        salary_text=str(row.get("salary_text") or ""),
        url=str(row.get("url") or f"https://jobs.example/{jid}"),
        ats_type=str(row.get("ats_type") or ""),
        distance_km=row.get("distance_km"),
        published_at=str(row.get("published_at") or ""),
        match_score=int(row.get("match_score") or 0),
    )


def _job_from_edge(spec: dict[str, Any]) -> Job:
    jid = spec["id"]
    return Job(
        id=jid,
        source=str(spec.get("source") or "e2e_edge"),
        source_job_id=jid,
        title=str(spec.get("title") or ""),
        company=str(spec.get("company") or ""),
        description=f"Synthetic edge job {spec.get('match')}",
        city=str(spec.get("city") or ""),
        country_code=str(spec.get("country_code") or ""),
        remote_type=str(spec.get("remote_type") or ""),
        salary_min=spec.get("salary_min"),
        url=f"https://jobs.example/{jid}",
        ats_type=str(spec.get("ats_type") or ""),
        distance_km=spec.get("distance_km"),
        published_at=str(spec.get("published_at") or ""),
        match_reasons=[str(spec.get("match") or "")],
    )


def load_e2e_job_corpus(*, min_count: int = 100) -> list[Job]:
    """Combine intent corpus jobs + edge cases into a stable >=100 job set."""
    jobs: list[Job] = [_job_from_edge(s) for s in _EDGE_SPECS]
    if _INTENT_CORPUS.is_file():
        raw = json.loads(_INTENT_CORPUS.read_text(encoding="utf-8"))
        rows = raw.get("jobs") if isinstance(raw, dict) else raw
        for i, row in enumerate(rows or []):
            if not isinstance(row, dict):
                continue
            jobs.append(_job_from_intent_row(row, i))
            if len(jobs) >= max(min_count, 130):
                break
    # Pad deterministically if corpus missing/short.
    while len(jobs) < min_count:
        n = len(jobs) + 1
        jobs.append(
            Job(
                id=f"JOB_PAD_{n:04d}",
                source="e2e_pad",
                source_job_id=f"pad-{n}",
                title=f"Lohnbuchhalter Pad {n}",
                company=f"Pad Company {n} GmbH",
                city="Berlin",
                country_code="DE",
                url=f"https://jobs.example/pad/{n}",
                ats_type="personio" if n % 2 == 0 else "unknown",
            )
        )
    return jobs


def seed_jobs(db: Any, jobs: list[Job] | None = None) -> list[Job]:
    jobs = jobs or load_e2e_job_corpus()
    for job in jobs:
        db.upsert_job(job)
    return jobs
