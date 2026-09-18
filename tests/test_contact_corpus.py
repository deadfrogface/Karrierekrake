"""Corpus tests: >=200 positive + >=100 NOT_FOUND contact extractions (PR25)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.contacts.api import format_discovery_status
from core.contacts.discovery import (
    DiscoveryContext,
    DiscoveryPolicy,
    discover_contacts,
)
from core.contacts.models import DiscoveryStatus

CORPUS = Path(__file__).parent / "fixtures" / "contacts" / "extraction_corpus.json"


def _load() -> dict:
    assert CORPUS.is_file(), f"missing corpus; run scripts/generate_contact_corpus.py"
    return json.loads(CORPUS.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def corpus() -> dict:
    return _load()


def test_corpus_sizes(corpus: dict):
    assert len(corpus["positives"]) >= 200
    assert len(corpus["not_found"]) >= 100


def _run_fixture(item: dict):
    policy = DiscoveryPolicy(enabled=True, stale_after_days=90)
    variant = item.get("variant") or ""
    if variant in {"company_career_page", "hr_general"}:
        ctx = DiscoveryContext(
            job_id=item["id"],
            career_page_html=item.get("html") or "",
            career_page_url=item.get("source_url") or "",
        )
    elif variant == "company_contact_page":
        ctx = DiscoveryContext(
            job_id=item["id"],
            contact_page_html=item.get("html") or "",
            contact_page_url=item.get("source_url") or "",
        )
    elif variant == "ats_metadata":
        ctx = DiscoveryContext(
            job_id=item["id"],
            ats_metadata=item.get("ats_metadata") or {},
            job_url=item.get("source_url") or "",
        )
    else:
        ctx = DiscoveryContext(
            job_id=item["id"],
            job_url=item.get("source_url") or "",
            job_text=item.get("text") or "",
            job_html=item.get("html") or "",
        )
    return discover_contacts(ctx, policy=policy)


@pytest.mark.parametrize(
    "item",
    _load()["positives"] if CORPUS.is_file() else [],
    ids=lambda x: x["id"] if isinstance(x, dict) else str(x),
)
def test_positive_corpus_item(item: dict):
    result = _run_fixture(item)
    expect = item["expect"]
    assert result.status in {
        DiscoveryStatus.FOUND.value,
        DiscoveryStatus.STALE.value,
    }, (
        item["id"],
        result.status,
        result.message,
        [c.to_dict() for c in result.candidates],
    )
    persons = [c for c in result.candidates if c.is_usable_person()]
    assert persons, item["id"]
    for p in persons:
        assert p.validate_evidence() == [], (item["id"], p.to_dict())

    if expect.get("min_persons"):
        assert len(persons) >= int(expect["min_persons"])
    if expect.get("emails"):
        got = {p.email for p in persons}
        for email in expect["emails"]:
            assert email in got, (item["id"], got)
    if expect.get("email"):
        emails = {p.email for p in persons}
        assert expect["email"] in emails, (item["id"], emails)
    if expect.get("name"):
        names = {p.name for p in persons}
        assert expect["name"] in names, (item["id"], names)

    view = format_discovery_status(result)
    assert view["ok"] is True
    assert view["contact"] is not None
    assert view["contact"]["evidence"]


@pytest.mark.parametrize(
    "item",
    _load()["not_found"] if CORPUS.is_file() else [],
    ids=lambda x: x["id"] if isinstance(x, dict) else str(x),
)
def test_not_found_corpus_item(item: dict):
    result = _run_fixture(item)
    assert result.status == DiscoveryStatus.NOT_FOUND.value, (
        item["id"],
        result.status,
        [c.to_dict() for c in result.candidates],
    )
    assert not any(c.is_usable_person() for c in result.candidates)
    view = format_discovery_status(result)
    assert view["ok"] is True
    assert view["contact"] is None


def test_e2e_job_specific_contact_exact():
    """Acceptance E2E: clear job-specific contact exactly recognized."""
    html = """
    <html><head>
    <script type="application/ld+json">
    {"@type":"JobPosting","title":"Payroll Specialist (m/w/d)",
     "hiringOrganization":{"name":"Nordlicht GmbH"},
     "applicationContact":{
        "name":"Lena Richter","email":"lena.richter@nordlicht.example.com",
        "contactType":"Recruiterin","telephone":"+49 40 111222"}}
    </script></head>
    <body><p>Weitere Infos im Text.</p></body></html>
    """
    result = discover_contacts(
        DiscoveryContext(
            job_id="e2e_job_specific",
            job_html=html,
            job_url="https://jobs.example.com/payroll-specialist",
        ),
        policy=DiscoveryPolicy(enabled=True),
    )
    assert result.status == DiscoveryStatus.FOUND.value
    assert result.best is not None
    assert result.best.name == "Lena Richter"
    assert result.best.email == "lena.richter@nordlicht.example.com"
    assert result.best.validate_evidence() == []


def test_e2e_no_contact_not_found():
    result = discover_contacts(
        DiscoveryContext(
            job_id="e2e_none",
            job_text="Spannende Aufgabe in einem dynamischen Team. Online-Bewerbung.",
            job_url="https://jobs.example.com/none",
        ),
        policy=DiscoveryPolicy(enabled=True),
    )
    assert result.status == DiscoveryStatus.NOT_FOUND.value
    assert format_discovery_status(result)["ok"] is True
