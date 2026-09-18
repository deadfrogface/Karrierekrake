"""Unit tests for provenance-backed recruiting contact discovery (PR25)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.contacts import (
    CONTACT_SCHEMA_VERSION,
    ContactCandidate,
    ContactDiscoveryService,
    ContactEvidence,
    DiscoveryResult,
    DiscoveryStatus,
    SourceType,
    discover_contacts,
)
from core.contacts.api import format_discovery_status
from core.contacts.classify import is_generic_mailbox
from core.contacts.discovery import DiscoveryContext, DiscoveryPolicy
from core.contacts.extract import (
    extract_from_ats_metadata,
    extract_from_html,
    extract_from_jsonld,
    extract_from_visible_text,
)
from core.database import Database
from core.models import Job


def test_schema_version_is_set():
    assert CONTACT_SCHEMA_VERSION >= 1
    c = ContactCandidate(name="Mira Vogel", email="mira.vogel@example.com")
    # Without evidence → invalid
    assert "name" in c.validate_evidence()
    assert "email" in c.validate_evidence()


def test_no_field_without_evidence():
    ev = [
        ContactEvidence(
            field="name",
            quote="Ansprechpartnerin: Mira Vogel",
            source_type=SourceType.JOB_POSTING_TEXT.value,
            source_url="https://jobs.example.com/1",
        ),
        ContactEvidence(
            field="email",
            quote="mira.vogel@example.com",
            source_type=SourceType.JOB_POSTING_TEXT.value,
            source_url="https://jobs.example.com/1",
        ),
    ]
    c = ContactCandidate(
        name="Mira Vogel",
        email="mira.vogel@example.com",
        source_type=SourceType.JOB_POSTING_TEXT.value,
        source_url="https://jobs.example.com/1",
        evidence=ev,
        contact_kind="person",
    )
    assert c.validate_evidence() == []
    assert c.is_usable_person()


def test_info_at_never_becomes_person():
    assert is_generic_mailbox("info@example.com")
    assert is_generic_mailbox("jobs@acme.example.com")
    assert is_generic_mailbox("hr@firma.example.org")
    assert not is_generic_mailbox("mira.vogel@example.com")

    text = "Bewerbungen bitte an info@nordlicht.example.com"
    cands = extract_from_visible_text(text, source_url="https://jobs.example.com/x")
    assert cands
    assert all(not c.is_usable_person() for c in cands)
    assert all(c.contact_kind == "generic_mailbox" for c in cands)


def test_job_specific_recruiter_from_text():
    text = (
        "Wir freuen uns auf Ihre Bewerbung.\n"
        "Ansprechpartnerin: Lena Richter, Recruiterin — "
        "lena.richter@talentwerk.example.com, Tel. +49 30 1234567\n"
    )
    cands = extract_from_visible_text(
        text,
        source_type=SourceType.JOB_POSTING_TEXT,
        source_url="https://jobs.example.com/payroll",
    )
    persons = [c for c in cands if c.is_usable_person()]
    assert len(persons) == 1
    p = persons[0]
    assert p.name == "Lena Richter"
    assert "lena.richter@talentwerk.example.com" == p.email
    assert p.validate_evidence() == []


def test_jsonld_application_contact():
    docs = [
        {
            "@type": "JobPosting",
            "title": "Payroll Specialist",
            "datePosted": "2026-08-01",
            "hiringOrganization": {"name": "Nordlicht GmbH"},
            "applicationContact": {
                "@type": "ContactPoint",
                "name": "Tobias Keller",
                "email": "tobias.keller@nordlicht.example.com",
                "contactType": "Recruiter",
                "telephone": "+49 40 998877",
            },
        }
    ]
    cands = extract_from_jsonld(docs, source_url="https://jobs.example.com/j1")
    persons = [c for c in cands if c.is_usable_person()]
    assert persons
    assert persons[0].name == "Tobias Keller"
    assert persons[0].source_type == SourceType.JOB_POSTING_JSONLD.value


def test_conflicting_structured_data_keeps_provenance():
    docs = [
        {
            "@type": "JobPosting",
            "title": "Controller",
            "applicationContact": {
                "name": "Anna Eins",
                "email": "anna.eins@example.com",
            },
            "hiringOrganization": {
                "name": "Acme",
                "contactPoint": {
                    "name": "Bernd Zwei",
                    "email": "bernd.zwei@example.com",
                    "contactType": "HR",
                },
            },
        }
    ]
    cands = extract_from_jsonld(docs, source_url="https://jobs.example.com/conflict")
    persons = [c for c in cands if c.is_usable_person()]
    assert len(persons) >= 2
    emails = {p.email for p in persons}
    assert "anna.eins@example.com" in emails
    assert "bernd.zwei@example.com" in emails
    for p in persons:
        assert p.validate_evidence() == []


def test_malformed_html_does_not_raise():
    html = "<html><body><script type='application/ld+json'>{not json"
    cands = extract_from_html(
        html,
        source_type=SourceType.JOB_POSTING_TEXT,
        source_url="https://jobs.example.com/bad",
    )
    assert isinstance(cands, list)


def test_ats_metadata_extraction():
    cands = extract_from_ats_metadata(
        {
            "recruiter_name": "Clara Stein",
            "recruiter_email": "clara.stein@ats.example.com",
            "contact_role": "Talent Acquisition",
            "department": "People",
        },
        source_url="https://boards.example.com/1",
    )
    assert len(cands) == 1
    assert cands[0].is_usable_person()
    assert cands[0].source_type == SourceType.ATS_METADATA.value


def test_feature_toggle_disabled():
    job = Job(id="j1", title="X", company="Y", description="Ansprechpartner: A B a.b@example.com")
    result = discover_contacts(
        DiscoveryContext(job=job, job_id="j1"),
        policy=DiscoveryPolicy(enabled=False),
    )
    assert result.status == DiscoveryStatus.DISABLED.value


def test_not_found_is_success_path():
    job = Job(
        id="j2",
        title="Sachbearbeiter",
        company="NoContact AG",
        description="Wir suchen Verstärkung. Keine Kontaktdaten in dieser Anzeige.",
        url="https://jobs.example.com/nocontact",
    )
    result = discover_contacts(
        DiscoveryContext(job=job, job_id="j2", job_text=job.description),
        policy=DiscoveryPolicy(enabled=True),
    )
    assert result.status == DiscoveryStatus.NOT_FOUND.value
    view = format_discovery_status(result)
    assert view["ok"] is True
    assert view["contact"] is None


def test_pipeline_priority_job_text_over_career():
    job_text = (
        "Ansprechpartner: Job Spezifisch — job.spezifisch@firma.example.com"
    )
    career_html = """
    <html><body>
    <p>Ansprechpartnerin: Karriere Allgemein — karriere.allgemein@firma.example.com</p>
    </body></html>
    """
    result = discover_contacts(
        DiscoveryContext(
            job_id="prio1",
            job_text=job_text,
            job_url="https://jobs.example.com/prio",
            career_page_html=career_html,
            career_page_url="https://firma.example.com/karriere",
        ),
        policy=DiscoveryPolicy(enabled=True),
    )
    assert result.status == DiscoveryStatus.FOUND.value
    assert result.best is not None
    assert result.best.email == "job.spezifisch@firma.example.com"
    assert result.best.source_type == SourceType.JOB_POSTING_TEXT.value


def test_stale_page_flagged():
    html = """
    <html><head>
    <script type="application/ld+json">
    {"@type":"JobPosting","title":"X","dateModified":"2020-01-15",
     "applicationContact":{"name":"Old Recruiter","email":"old.recruiter@example.com"}}
    </script></head><body></body></html>
    """
    cands = extract_from_html(
        html,
        source_type=SourceType.JOB_POSTING_TEXT,
        source_url="https://jobs.example.com/old",
        stale_after_days=90,
    )
    persons = [c for c in cands if c.is_usable_person()]
    assert persons
    assert persons[0].stale is True
    assert persons[0].page_timestamp.startswith("2020")


def test_multiple_persons_on_page():
    text = (
        "Ansprechpartner: Alex Eins — alex.eins@example.com\n"
        "Ansprechpartnerin: Bella Zwei — bella.zwei@example.com\n"
    )
    result = discover_contacts(
        DiscoveryContext(job_id="multi", job_text=text, job_url="https://jobs.example.com/m"),
        policy=DiscoveryPolicy(enabled=True),
    )
    assert result.status == DiscoveryStatus.FOUND.value
    assert len(result.candidates) >= 2


def test_signature_requires_confirmed_thread():
    sig = "Mit freundlichen Grüßen\nNora Recruiter\nnora.recruiter@agency.example.com"
    result = discover_contacts(
        DiscoveryContext(
            job_id="sig1",
            signature_text=sig,
            signature_thread_confirmed=False,
        ),
        policy=DiscoveryPolicy(enabled=True),
    )
    assert result.status == DiscoveryStatus.NOT_FOUND.value

    result2 = discover_contacts(
        DiscoveryContext(
            job_id="sig2",
            case_id="c1",
            signature_text=sig,
            signature_thread_confirmed=True,
        ),
        policy=DiscoveryPolicy(enabled=True),
    )
    assert result2.status == DiscoveryStatus.FOUND.value
    assert result2.best and result2.best.source_type == SourceType.RECRUITER_SIGNATURE.value


def test_db_persist_invalidate_delete(tmp_path: Path):
    db = Database(tmp_path / "contacts.db")
    policy = DiscoveryPolicy(enabled=True)
    svc = ContactDiscoveryService(policy=policy, db=db)
    ctx = DiscoveryContext(
        job_id="persist1",
        job_text="Ansprechpartner: Pia Persist — pia.persist@example.com",
        job_url="https://jobs.example.com/persist",
    )
    result = svc.discover(ctx)
    assert result.status == DiscoveryStatus.FOUND.value
    rows = db.list_recruiting_contacts(job_id="persist1")
    assert len(rows) == 1
    assert rows[0]["status"] == DiscoveryStatus.FOUND.value

    n = svc.invalidate(job_id="persist1")
    assert n >= 1
    rows2 = db.list_recruiting_contacts(job_id="persist1", include_invalidated=True)
    assert any(r["status"] == "INVALIDATED" for r in rows2)

    deleted = svc.delete(job_id="persist1")
    assert deleted >= 1
    assert db.list_recruiting_contacts(job_id="persist1", include_invalidated=True) == []


def test_rate_limit_blocks_mass_fetch():
    calls: list[str] = []

    def fetch(url: str):
        calls.append(url)
        return "<html><body>Ansprechpartner: Fetch Me — fetch.me@example.com</body></html>", {
            "status_code": 200
        }

    svc = ContactDiscoveryService(
        policy=DiscoveryPolicy(enabled=True, max_fetches_per_run=1, min_interval_seconds=0),
        fetch_fn=fetch,
    )
    r1 = svc.discover(
        DiscoveryContext(
            job_id="rl1",
            allow_network=True,
            career_page_fetch_url="https://firma.example.com/karriere",
        )
    )
    assert r1.status == DiscoveryStatus.FOUND.value
    r2 = svc.discover(
        DiscoveryContext(
            job_id="rl2",
            allow_network=True,
            career_page_fetch_url="https://firma.example.com/kontakt",
        )
    )
    # Budget exhausted → no person from second fetch
    assert len(calls) == 1
    assert r2.status == DiscoveryStatus.NOT_FOUND.value


def test_blocked_paywall_stops():
    def fetch(url: str):
        return "", {"status_code": 403, "blocked": True, "login_required": True}

    svc = ContactDiscoveryService(
        policy=DiscoveryPolicy(enabled=True),
        fetch_fn=fetch,
    )
    result = svc.discover(
        DiscoveryContext(
            job_id="block1",
            allow_network=True,
            career_page_fetch_url="https://firma.example.com/secret",
        )
    )
    assert result.status == DiscoveryStatus.BLOCKED.value


def test_cache_hit(tmp_path: Path):
    db = Database(tmp_path / "cache.db")
    svc = ContactDiscoveryService(policy=DiscoveryPolicy(enabled=True), db=db)
    ctx = DiscoveryContext(
        job_id="cache1",
        job_text="Ansprechpartner: Cache Hit — cache.hit@example.com",
        job_url="https://jobs.example.com/cache",
    )
    a = svc.discover(ctx)
    b = svc.discover(ctx)
    assert a.status == DiscoveryStatus.FOUND.value
    assert b.cache_hit is True
