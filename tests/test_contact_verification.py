"""PR26 tests: block ambiguous / inferred salutations; verification → writer.

Synthetic fixture names only (example.com). No real PII.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from core.config import AppConfig, ApplicationProfile, SettingsConfig, SourcedText
from core.contacts.models import (
    DEFAULT_VERIFICATION_STATUS,
    ContactCandidate,
    ContactEvidence,
    ContactKind,
    DiscoveryResult,
    DiscoveryStatus,
    SourceType,
)
from core.contacts.verification import (
    EvidenceStrength,
    VerificationStatus,
    detects_gender_inference,
    has_explicit_salutation_evidence,
    verify_candidate,
    verify_discovery,
)
from core.contacts.writer_contract import (
    NEUTRAL_SALUTATION,
    WriterContactClaims,
    build_writer_claims,
    claims_from_discovery,
    sanitize_cover_body_for_claims,
    writer_invented_contact_violations,
)
from core.cover_letter import render_cover_letter
from core.models import Job
from guenther.contracts import WritingSuggestion
from guenther.intelligence.writing_validate import validate_writing_grounded
from guenther.runtime.heuristic_provider import HeuristicProvider
from guenther.intelligence.quality_loop.state_machine import run_quality_loop


# ---------------------------------------------------------------------------
# Synthetic name pools (fictional — example.com only)
# ---------------------------------------------------------------------------

_FIRST = [
    "Alex", "Blair", "Casey", "Dana", "Eden", "Finley", "Gray", "Harper",
    "Indigo", "Jordan", "Kai", "Logan", "Morgan", "Noa", "Oakley", "Parker",
    "Quinn", "Riley", "Sage", "Taylor", "Umber", "Val", "Winter", "Yael",
    "Zion", "Adrian", "Blake", "Cameron", "Drew", "Ellis", "Frankie", "Gale",
    "Hayden", "Ira", "Jules", "Kit", "Lane", "Milan", "Nico", "Orion",
    "Peyton", "Remy", "Sky", "Toby", "Uri", "Vesper", "Wren", "Xan",
    "Yuri", "Zephyr", "Ash", "Brook", "Charlie", "Delta",
]
_LAST = [
    "Quell", "Nest", "Bridge", "Harbor", "Meadow", "Canyon", "Pine", "Stone",
    "River", "Field", "Grove", "Hill", "Lake", "Marsh", "North", "Orchard",
    "Peak", "Ridge", "Shore", "Trail", "Vale", "Wood", "Yard", "Beacon",
    "Cliff", "Delta", "Echo", "Frost", "Glen", "Haven", "Isle", "Jade",
    "Knob", "Lumen", "Moss", "Nova", "Oasis", "Prism", "Quartz", "Reef",
    "Summit", "Tide", "Upland", "Vista", "Wave", "Yarrow", "Zenith", "Amber",
    "Birch", "Cedar", "Dove", "Elm", "Fern", "Gale",
]


def _synth_people(n: int = 55) -> list[str]:
    out: list[str] = []
    for i in range(n):
        out.append(f"{_FIRST[i % len(_FIRST)]} {_LAST[i % len(_LAST)]}")
    assert len(out) >= 50
    return out


def _ev(field: str, quote: str, source: str = SourceType.JOB_POSTING_TEXT.value) -> ContactEvidence:
    return ContactEvidence(field=field, quote=quote, source_type=source, source_url="https://jobs.example.com/x")


def _person(
    name: str,
    *,
    source: str = SourceType.JOB_POSTING_TEXT.value,
    email: str | None = None,
    role: str = "Recruiter",
    salutation_quote: str | None = None,
    page_timestamp: str = "",
    stale: bool = False,
) -> ContactCandidate:
    local = name.lower().replace(" ", ".")
    mail = email or f"{local}@jobs.example.com"
    evidence = [
        _ev("name", salutation_quote or f"Ansprechpartner: {name}", source),
        _ev("email", mail, source),
        _ev("role", role, source),
    ]
    return ContactCandidate(
        name=name,
        email=mail,
        role=role,
        source_type=source,
        source_url="https://jobs.example.com/x",
        evidence=evidence,
        contact_kind=ContactKind.PERSON.value,
        page_timestamp=page_timestamp,
        stale=stale,
    )


def _cfg() -> AppConfig:
    return AppConfig(
        application=ApplicationProfile(first_name="Nora", last_name="Bewerber"),
        settings=SettingsConfig(
            contact_verification_enabled=True,
            contact_writer_binding_enabled=True,
            contact_discovery_stale_after_days=90,
        ),
    )


# ---------------------------------------------------------------------------
# Migration / defaults
# ---------------------------------------------------------------------------

def test_legacy_candidate_defaults_unverified():
    c = ContactCandidate(name="Legacy Person")
    assert c.verification_status == DEFAULT_VERIFICATION_STATUS
    assert c.verification_status == VerificationStatus.UNVERIFIED.value


def test_empty_discovery_is_unverified_not_error():
    r = verify_discovery(DiscoveryResult.not_found(job_id="j1"))
    assert r.status == VerificationStatus.UNVERIFIED.value
    assert not r.contact_verified
    claims = build_writer_claims(r)
    assert claims.CONTACT_VERIFIED is False
    assert claims.CONTACT_NAME == ""


# ---------------------------------------------------------------------------
# 50+ ambiguous people → REVIEW / no writer person
# ---------------------------------------------------------------------------

def test_fifty_plus_ambiguous_people_block_writer():
    people = _synth_people(55)
    # Two strong sources with different names → conflict
    cands = [
        _person(people[0], source=SourceType.JOB_POSTING_TEXT.value),
        _person(people[1], source=SourceType.ATS_METADATA.value, email=f"{people[1].lower().replace(' ', '.')}@ats.example.com"),
    ]
    result = DiscoveryResult(
        status=DiscoveryStatus.FOUND.value,
        candidates=cands,
        job_id="ambig-job",
    )
    v = verify_discovery(result)
    assert v.status == VerificationStatus.REVIEW.value
    assert v.uncertainty_visible is True
    claims = build_writer_claims(v)
    assert claims.CONTACT_VERIFIED is False
    assert claims.CONTACT_NAME == ""

    # Batch: each ambiguous pair alone stays REVIEW
    blocked = 0
    for i in range(0, 50, 2):
        pair = [
            _person(people[i], source=SourceType.JOB_POSTING_TEXT.value),
            _person(
                people[i + 1],
                source=SourceType.JOB_POSTING_JSONLD.value,
                email=f"alt{i}@jobs.example.com",
            ),
        ]
        vv = verify_discovery(None, candidates=pair)
        assert vv.status == VerificationStatus.REVIEW.value
        assert build_writer_claims(vv).CONTACT_VERIFIED is False
        blocked += 1
    assert blocked >= 25


# ---------------------------------------------------------------------------
# 50 signatures → weak / not auto job contact
# ---------------------------------------------------------------------------

def test_fifty_signatures_are_display_only_not_verified():
    people = _synth_people(50)
    verified_count = 0
    for i, name in enumerate(people):
        c = _person(
            name,
            source=SourceType.RECRUITER_SIGNATURE.value,
            email=f"sig{i}@mail.example.com",
        )
        v = verify_candidate(c)
        assert v.status == VerificationStatus.UNVERIFIED.value
        assert v.evidence_strength == EvidenceStrength.WEAK.value
        assert v.contact_verified is False
        claims = build_writer_claims(v)
        assert claims.CONTACT_VERIFIED is False
        if claims.CONTACT_VERIFIED:
            verified_count += 1
    assert verified_count == 0
    assert len(people) >= 50


# ---------------------------------------------------------------------------
# Stale contacts
# ---------------------------------------------------------------------------

def test_stale_contacts_not_writer_usable():
    old = (datetime.now(timezone.utc) - timedelta(days=200)).date().isoformat()
    c = _person("Stale Contact", page_timestamp=old)
    v = verify_candidate(c, stale_after_days=90)
    assert v.status == VerificationStatus.STALE.value
    assert v.stale is True
    assert build_writer_claims(v).CONTACT_VERIFIED is False

    flagged = _person("Flagged Stale", stale=True)
    v2 = verify_candidate(flagged)
    assert v2.status == VerificationStatus.STALE.value


# ---------------------------------------------------------------------------
# Generic mailboxes
# ---------------------------------------------------------------------------

def test_generic_mailboxes_rejected():
    for local in ("info", "jobs", "hr", "bewerbung", "recruiting", "karriere"):
        c = ContactCandidate(
            name="",
            email=f"{local}@firma.example.com",
            source_type=SourceType.JOB_POSTING_TEXT.value,
            evidence=[_ev("email", f"{local}@firma.example.com")],
            contact_kind=ContactKind.GENERIC_MAILBOX.value,
        )
        v = verify_candidate(c)
        assert v.status == VerificationStatus.REJECTED.value
        assert build_writer_claims(v).CONTACT_VERIFIED is False


# ---------------------------------------------------------------------------
# Homonyms
# ---------------------------------------------------------------------------

def test_homonyms_require_review():
    a = _person("Jordan Quell", email="jordan.quell@a.example.com", role="Recruiter")
    b = _person(
        "Jordan Quell",
        email="jordan.quell@b.example.com",
        role="HR Business Partner",
        source=SourceType.ATS_METADATA.value,
    )
    v = verify_discovery(None, candidates=[a, b])
    assert v.status == VerificationStatus.REVIEW.value
    assert any(c.kind == "homonym" for c in v.conflicts)
    assert build_writer_claims(v).CONTACT_VERIFIED is False


# ---------------------------------------------------------------------------
# Job page vs company page conflict
# ---------------------------------------------------------------------------

def test_job_vs_company_page_conflict():
    job = _person("Job Page Person", source=SourceType.JOB_POSTING_TEXT.value)
    company = _person(
        "Company Page Person",
        source=SourceType.COMPANY_CAREER_PAGE.value,
        email="company.page@corp.example.com",
    )
    v = verify_discovery(None, candidates=[job, company])
    assert v.status == VerificationStatus.REVIEW.value
    assert any(c.kind == "job_vs_company" for c in v.conflicts)
    claims = build_writer_claims(v)
    assert claims.CONTACT_VERIFIED is False
    assert claims.uncertainty_visible is True


# ---------------------------------------------------------------------------
# Missing salutation evidence / inferred salutations blocked
# ---------------------------------------------------------------------------

def test_missing_salutation_evidence_blocks_personal_opening():
    c = _person("Casey Nest")  # quote has no Frau/Herr
    assert has_explicit_salutation_evidence(c) is False
    v = verify_candidate(c)
    assert v.contact_verified is True
    assert v.salutation_allowed is False
    claims = build_writer_claims(v)
    assert claims.CONTACT_VERIFIED is True
    assert claims.SALUTATION_ALLOWED is False
    assert claims.opening_line().startswith(NEUTRAL_SALUTATION)

    adversarial = "Sehr geehrte Frau Nest, hiermit bewerbe ich mich."
    viol = writer_invented_contact_violations(adversarial, claims)
    assert viol
    assert any(v.startswith("SALUTATION_NOT_ALLOWED") for v in viol)


def test_fifty_inferred_salutations_blocked():
    people = _synth_people(50)
    empty = WriterContactClaims.empty()
    blocked = 0
    for name in people:
        # Gender-inferred opening without verification
        body = f"Sehr geehrte Frau {name.split()[-1]}, ich bewerbe mich."
        viol = writer_invented_contact_violations(body, empty)
        assert viol, name
        blocked += 1
        # Explicit gender-inference notes rejected at verify time
        c = _person(name)
        bad = verify_candidate(
            c,
            allow_inferred_salutation=True,
            inference_notes="Vorname klingt weiblich",
        )
        assert bad.status == VerificationStatus.REJECTED.value
    assert blocked >= 50
    assert detects_gender_inference("Vorname klingt weiblich -> Frau")


def test_explicit_salutation_evidence_allows_flag_only():
    c = _person(
        "Riley Grove",
        salutation_quote="Sehr geehrte Frau Riley Grove, Recruiterin",
    )
    assert has_explicit_salutation_evidence(c) is True
    v = verify_candidate(c)
    assert v.salutation_allowed is True
    claims = build_writer_claims(v)
    assert claims.SALUTATION_ALLOWED is True
    # Still no gender invent from first name alone in opening_line
    assert NEUTRAL_SALUTATION in claims.opening_line()


# ---------------------------------------------------------------------------
# Strong verified contact path
# ---------------------------------------------------------------------------

def test_strong_job_contact_verified_for_writer():
    c = _person("Harper Bridge", role="Talent Acquisition")
    v = verify_candidate(c)
    assert v.status == VerificationStatus.VERIFIED.value
    assert v.evidence_strength == EvidenceStrength.STRONG.value
    claims = build_writer_claims(v)
    assert claims.CONTACT_VERIFIED is True
    assert claims.CONTACT_NAME == "Harper Bridge"
    assert claims.CONTACT_ROLE == "Talent Acquisition"
    assert claims.CONTACT_SOURCE == SourceType.JOB_POSTING_TEXT.value


def test_company_page_alone_not_verified():
    c = _person("Company Only", source=SourceType.COMPANY_CONTACT_PAGE.value)
    v = verify_candidate(c)
    assert v.contact_verified is False
    assert v.display_candidate is not None
    assert build_writer_claims(v).CONTACT_NAME == ""


def test_email_alone_cannot_invent_person():
    c = ContactCandidate(
        name="",
        email="mystery.person@jobs.example.com",
        source_type=SourceType.JOB_POSTING_TEXT.value,
        evidence=[_ev("email", "mystery.person@jobs.example.com")],
        contact_kind=ContactKind.UNKNOWN.value,
    )
    v = verify_candidate(c)
    assert v.status == VerificationStatus.REJECTED.value


# ---------------------------------------------------------------------------
# Adversarial writer tries to add name
# ---------------------------------------------------------------------------

def test_adversarial_writer_name_injection_sanitized():
    claims = WriterContactClaims.empty()
    body = (
        "Sehr geehrte Frau Inventiert-Müller, "
        "Ansprechpartnerin: Fake Person, ich bewerbe mich bei Acme."
    )
    viol = writer_invented_contact_violations(body, claims)
    assert any("UNVERIFIED_PERSON_SALUTATION" in v for v in viol)
    clean = sanitize_cover_body_for_claims(body, claims)
    assert "Frau Inventiert" not in clean
    assert NEUTRAL_SALUTATION in clean


def test_cover_letter_render_never_injects_unverified_person():
    job = Job(
        id="j-cov",
        title="Payroll Specialist",
        company="Nordlicht GmbH",
        description="Buchhaltung DATEV",
        url="https://jobs.example.com/p",
        source="test",
    )
    cfg = _cfg()
    cfg.profile.qualifications.skills.append(
        SourcedText(value="Buchhaltung", source="manual")
    )
    # Unverified / weak claims
    weak = build_writer_claims(
        verify_candidate(_person("Weak Sig", source=SourceType.RECRUITER_SIGNATURE.value))
    )
    letter = render_cover_letter(job, cfg, contact_claims=weak)
    assert "Weak Sig" not in letter
    assert "Sehr geehrte Frau" not in letter
    assert NEUTRAL_SALUTATION in letter


def test_writing_validate_blocks_unverified_person():
    claims = WriterContactClaims.empty()
    model = WritingSuggestion(
        subject="Bewerbung",
        body="Sehr geehrte Frau Halluziniert, hiermit bewerbe ich mich bei Testfirma Example.",
        invented_flag=False,
    )
    out, report = validate_writing_grounded(
        model,
        profile_text="Nora Bewerber\nExcel\nBuchhaltung",
        job_text="Buchhaltung bei Testfirma Example",
        target_company="Testfirma Example",
        contact_claims=claims,
    )
    assert any(e.code == "UNVERIFIED_CONTACT_PERSON" for e in report.errors)
    assert "Frau Halluziniert" not in (out.body or "")
    assert NEUTRAL_SALUTATION in (out.body or "")


def test_e2e_discovery_verification_plan_cover_only_verified():
    """Discovery → Verification → Plan/Cover: only verified contact usable."""
    strong = _person("Verified Talent", role="Recruiterin")
    weak = _person(
        "Company Recruiter",
        source=SourceType.COMPANY_CAREER_PAGE.value,
        email="company.recruiter@corp.example.com",
    )
    discovery = DiscoveryResult(
        status=DiscoveryStatus.FOUND.value,
        candidates=[strong, weak],
        job_id="e2e-1",
    )
    # Conflict path if both differ — use strong alone for verified E2E
    discovery_ok = DiscoveryResult(
        status=DiscoveryStatus.FOUND.value,
        candidates=[strong],
        job_id="e2e-1",
    )
    claims = claims_from_discovery(discovery_ok)
    assert claims.CONTACT_VERIFIED is True
    assert claims.CONTACT_NAME == "Verified Talent"

    job = Job(
        id="e2e-1",
        title="Sachbearbeitung",
        company="Talentwerk Example",
        description="Excel Buchhaltung",
        url="https://jobs.example.com/e2e",
        source="test",
    )
    cfg = _cfg()
    cfg.profile.qualifications.skills.append(
        SourcedText(value="Buchhaltung", source="manual")
    )
    letter = render_cover_letter(job, cfg, contact_claims=claims)
    # Without salutation evidence → neutral, but name not freestyle-injected
    assert "Sehr geehrte Frau Verified" not in letter
    assert NEUTRAL_SALUTATION in letter

    # Heuristic writer with CONTACT_VERIFIED=false must stay neutral
    provider = HeuristicProvider()
    payload = provider._writing(
        "CONTACT_VERIFIED=false\nSALUTATION_ALLOWED=false\nNEUTRAL_SALUTATION=Sehr geehrte Damen und Herren\nPROFILE:\nExcel\n",
        "JOB:\nBuchhaltung",
    )
    assert "Frau " not in payload["body"]
    assert "Herr " not in payload["body"]

    # Quality loop with empty claims
    def _gen(schema, task, trusted, untrusted):
        if schema == "writing_plan":
            from guenther.intelligence.quality_loop.schemas import WritingPlan
            return WritingPlan(target_company="Talentwerk Example", target_role="Sachbearbeitung"), [], {}
        if schema == "writing":
            # Adversarial model tries to add a name
            return (
                WritingSuggestion(
                    subject="Bewerbung",
                    body="Sehr geehrte Frau Fake, ich bewerbe mich bei Talentwerk Example. Excel Erfahrung.",
                ),
                [],
                {},
            )
        return None, [], {}

    result = run_quality_loop(
        generate_fn=_gen,
        profile_text="Excel\nBuchhaltung",
        job_text="Sachbearbeitung Excel Buchhaltung",
        target_company="Talentwerk Example",
        target_role="Sachbearbeitung",
        mode="plan_draft",
        contact_claims=WriterContactClaims.empty(),
    )
    body = (result.suggestion.body if result.suggestion else "") or ""
    assert "Frau Fake" not in body


def test_writer_binding_toggle_rollback():
    c = _person("Bound Contact")
    v = verify_candidate(c)
    assert v.contact_verified is True
    unbound = build_writer_claims(v, writer_binding_enabled=False)
    assert unbound.CONTACT_VERIFIED is False
    assert unbound.CONTACT_NAME == ""
    assert "rollback" in " ".join(unbound.reasons).lower() or "disabled" in " ".join(unbound.reasons).lower()


def test_verification_disabled_status():
    c = _person("Anyone")
    v = verify_discovery(
        DiscoveryResult(status=DiscoveryStatus.FOUND.value, candidates=[c]),
        verification_enabled=False,
    )
    assert v.status == VerificationStatus.DISABLED.value
    assert build_writer_claims(v).CONTACT_VERIFIED is False


def test_unit_gate_zero_invented_contacts_across_matrix():
    """UNIT gate: 0 invented contacts/salutations across synthetic matrix."""
    people = _synth_people(52)
    invented = 0
    for i, name in enumerate(people):
        # Unverified claims + adversarial body
        claims = WriterContactClaims.empty()
        body = f"Sehr geehrter Herr {name}, Anrede erfunden."
        if not writer_invented_contact_violations(body, claims):
            invented += 1
        clean = sanitize_cover_body_for_claims(body, claims)
        if name.split()[-1] in clean and "Herr " in clean:
            # sanitized should remove personal form
            invented += 1
        # Weak company contact must not verify
        weak = verify_candidate(
            _person(name, source=SourceType.COMPANY_CAREER_PAGE.value, email=f"w{i}@corp.example.com")
        )
        if weak.contact_verified:
            invented += 1
    assert invented == 0
