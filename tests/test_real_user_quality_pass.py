"""Real-user quality pass regressions — fictional fixtures only (example.com)."""

from __future__ import annotations

from pathlib import Path

import pytest

from apply.preview import build_application_preview
from core.config import (
    AppConfig,
    ApplicationProfile,
    EmploymentConfig,
    ExperienceEntry,
    JobsConfig,
    LanguageEntry,
    LocationConfig,
    ProfileConfig,
    QualificationsConfig,
    SettingsConfig,
    SourcedText,
    soft_migrate_jobs_config,
    normalize_jobs_per_search,
)
from core.cover_letter import CoverLetterRefused, pick_relevant_experience, render_cover_letter
from core.cv_parser import MISSING_IN_DOCUMENT, parse_cv_text
from core.documents import active_cv_variant, normalize_variants
from core.matcher import score_job
from core.models import Job
from core.text_normalize import clean_company, extract_german_phones, is_blankish
from app.main import build_queries, resolve_search_titles


def _cfg(**qual_overrides) -> AppConfig:
    quals = QualificationsConfig(
        skills=[SourcedText(value="Excel", source="manual")],
        software=[SourcedText(value="DATEV", source="cv")],
        languages=[LanguageEntry(language="Deutsch", level="C2", source="manual")],
        work_experience=[
            ExperienceEntry(
                title="Zahnmedizinische Abrechnungskraft",
                company="Praxis Beispiel",
                responsibilities=[
                    "GOZ/BEMA Abrechnung sowie Terminverwaltung",
                    "Patientenaufnahme an der Rezeption",
                ],
                source="cv",
            ),
            ExperienceEntry(
                title="Barkeeper",
                company="Bar Test",
                responsibilities=["Getränke zubereiten"],
                source="cv",
            ),
        ],
    )
    for k, v in qual_overrides.items():
        setattr(quals, k, v)
    return AppConfig(
        profile=ProfileConfig(
            location=LocationConfig(max_distance_km=30, allow_remote_germany=True),
            jobs=JobsConfig(desired_titles=["Medizinische Verwaltung"]),
            employment=EmploymentConfig(full_time=True, remote=True, hybrid=True, onsite=True),
            qualifications=quals,
        ),
        application=ApplicationProfile(
            first_name="Erika",
            last_name="Beispiel",
            email="erika.beispiel@example.com",
            phone="+49 170 0000000",
            cv_path="",
        ),
        settings=SettingsConfig(dry_run=True, mode="search_only", published_within_days=30),
    )


def test_sowie_is_not_experience_evidence():
    """Confirmed bug: glue word 'sowie' must never boost match score."""
    cfg = _cfg(
        work_experience=[
            ExperienceEntry(
                title="Hilfskraft",
                company="Firma",
                responsibilities=["sowie Teamarbeit und Kommunikation"],
            )
        ],
        skills=[],
        software=[],
    )
    cfg.profile.jobs.desired_titles = ["Quantenphysiker"]
    job = Job(
        title="Quantenphysiker",
        company="Lab",
        remote_type="remote",
        description="Wir suchen sowie Motivation und Freude an Physik.",
        employment_type="Vollzeit",
    )
    result = score_job(job, cfg)
    blob = " ".join(result.match_reasons).lower()
    assert "sowie" not in blob
    for ev in result.evidence or []:
        assert "sowie" not in str(ev.get("token", "")).lower()


def test_dental_billing_related_without_patient_record_hallucination():
    cfg = _cfg()
    job = Job(
        title="Medizinische Verwaltungskraft",
        company="Klinik Beispiel",
        remote_type="onsite",
        distance_km=8,
        description=(
            "Verwaltung einer Arztpraxis. Zwingend: Patientenakten führen. "
            "Wünschenswert: Abrechnungskenntnisse."
        ),
        employment_type="Vollzeit",
    )
    result = score_job(job, cfg)
    classes = {e.get("evidence_class") for e in (result.evidence or [])}
    assert "RELATED" in classes or any("Verwandt" in r or "RELATED" in r for r in result.match_reasons)
    # Must NOT invent patient-record competence.
    assert not any(
        "patientenakte" in str(e.get("note", "")).lower()
        and e.get("evidence_class") == "DIRECT"
        for e in (result.evidence or [])
    )
    assert any(
        e.get("evidence_class") == "NOT_SUPPORTED"
        and "patientenakte" in str(e.get("token", "")).lower()
        for e in (result.evidence or [])
    ) or any("patientenakte" in r.lower() for r in result.rejection_reasons)


def test_street_parse_strips_name_and_bullets():
    text = """
Erika Beispiel
• Erika Beispiel, Musterstraße 12, 80331 München
erika.beispiel@example.com
(089) 12345678

Berufserfahrung
Sachbearbeiterin
"""
    parsed = parse_cv_text(text)
    street = parsed["personal"].get("street", "")
    assert "Musterstraße" in street or "Musterstrasse" in street
    assert "Erika" not in street
    assert not street.startswith("•")
    phones = parsed["phones"]
    assert phones
    assert any("089" in p or "12345678" in p for p in phones)


def test_missing_fields_use_document_wording():
    parsed = parse_cv_text("Nur ein Name\nErika Beispiel\n")
    assert parsed["confidence"]["languages"] == MISSING_IN_DOCUMENT
    assert "Nicht erkannt" not in parsed["confidence"].values()
    assert "fehlgeschlagen" not in str(parsed["confidence"]).lower()


def test_german_phone_formats():
    text = "Kontakt: (030) 9876543 und +49 151 2345678 sowie 0170/1122334"
    phones = extract_german_phones(text)
    assert len(phones) >= 2


def test_nan_company_never_in_cover_letter():
    cfg = _cfg()
    job = Job(title="Sachbearbeiter", company=float("nan"), description="Excel DATEV")
    assert is_blankish(job.company) or clean_company(job.company) == ""
    with pytest.raises(CoverLetterRefused) as caught:
        render_cover_letter(job, cfg)
    blob = str(caught.value).lower()
    assert caught.value.refusal.reason_code == "company_missing"
    assert "bei nan" not in blob
    assert "nan" not in blob.split()


def test_cover_letter_ranks_relevant_experience_not_newest():
    cfg = _cfg()
    job = Job(
        title="Zahnmedizinische Abrechnung",
        company="Praxis Test GmbH",
        description="GOZ BEMA Abrechnung Praxisverwaltung",
    )
    picked = pick_relevant_experience(list(cfg.profile.qualifications.work_experience), job)
    assert picked is not None
    assert "Abrechnung" in (picked.title or "")
    letter = render_cover_letter(job, cfg)
    assert "Barkeeper" not in letter
    assert "Abrechnung" in letter or "relevant" in letter.lower()


def test_preview_gate_blocked_without_cv(tmp_path: Path):
    cfg = _cfg()
    cfg.root = tmp_path
    cfg.application.cv_path = str(tmp_path / "missing.pdf")
    job = Job(title="Sachbearbeiter", company="ACME", url="https://boards.greenhouse.io/x")
    preview = build_application_preview(job, cfg, meta={"cv_variants": []})
    assert preview.quality_gate == "BLOCKED"


def test_preview_shows_document_role_and_filename(tmp_path: Path):
    cv = tmp_path / "erika_cv.pdf"
    cv.write_bytes(b"%PDF-1.4 fictional")
    cfg = _cfg()
    cfg.root = tmp_path
    cfg.application.cv_path = str(cv)
    meta = {
        "active_cv_id": "abc123",
        "cv_variants": [
            {"id": "abc123", "label": "CV", "path": str(cv), "role": "cv"},
            {
                "id": "cov9",
                "label": "Anschreiben",
                "path": str(tmp_path / "letter.pdf"),
                "role": "cover_letter",
            },
        ],
    }
    job = Job(title="Sachbearbeiter", company="ACME Example", url="https://boards.greenhouse.io/x")
    preview = build_application_preview(job, cfg, meta=meta)
    assert preview.document_role == "cv"
    assert preview.document_filename == "erika_cv.pdf"
    assert preview.quality_gate in {"READY", "WARNING"}


def test_cover_letter_role_never_becomes_active_cv():
    meta = {
        "active_cv_id": "cov9",
        "cv_variants": [
            {"id": "cv1", "path": "/tmp/cv.pdf", "role": "cv", "label": "CV"},
            {"id": "cov9", "path": "/tmp/letter.pdf", "role": "cover_letter", "label": "CL"},
        ],
    }
    # active_cv_id pointing at cover letter must fall back to a real CV.
    variant = active_cv_variant(meta, fallback_cv_path="/tmp/cv.pdf")
    assert variant is not None
    assert variant["role"] == "cv"


def test_soft_migrate_alternative_titles():
    jobs = JobsConfig(desired_titles=["A"], alternative_titles=["B", "A"])
    out = soft_migrate_jobs_config(jobs)
    assert out.desired_titles == ["A", "B"]
    assert out.alternative_titles == []


def test_jobs_per_search_choices_and_max():
    assert normalize_jobs_per_search(40) == 40
    assert normalize_jobs_per_search(0) == 0
    assert normalize_jobs_per_search(100) == 100
    assert normalize_jobs_per_search(37) in {30, 40}


def test_mode_a_discovery_without_desired_titles():
    cfg = _cfg()
    cfg.profile.jobs.desired_titles = []
    cfg.profile.jobs.alternative_titles = []
    cfg.settings.search_mode = "profile_discovery"
    cfg.profile.location.home_address = "80331 München"
    titles = resolve_search_titles(cfg)
    assert titles, "discovery mode must derive titles from experience"
    queries = build_queries(cfg)
    assert queries
    assert all(q.max_results > 0 for q in queries)


def test_mode_b_explicit_requires_titles():
    cfg = _cfg()
    cfg.profile.jobs.desired_titles = []
    cfg.settings.search_mode = "explicit_titles"
    assert resolve_search_titles(cfg) == []


def test_jobs_per_search_max_terminates_with_finite_cap():
    cfg = _cfg()
    cfg.profile.jobs.desired_titles = ["Sachbearbeiter"]
    cfg.profile.location.home_address = "Berlin"
    cfg.settings.jobs_per_search = 0  # Max
    queries = build_queries(cfg)
    assert queries
    assert all(q.max_results >= 50 for q in queries)
    # Finite — sources terminate; not infinite.
    assert all(q.max_results <= 250 for q in queries)


def test_variant_normalize_adds_role_and_id():
    variants = normalize_variants([{"path": "/x/cv.pdf", "label": "x"}])
    assert len(variants) == 1
    assert variants[0]["role"] == "cv"
    assert variants[0]["id"]
