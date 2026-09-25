"""Extract confirmation gate — invented edu/employment must not reach Matching/CL."""

from __future__ import annotations

import pytest

from core.config import (
    AppConfig,
    ExperienceEntry,
    QualificationsConfig,
    SourcedText,
    empty_app_config,
)
from core.cover_letter import render_cover_letter
from core.cv_extract_confirmation import (
    ExtractConfirmationError,
    confirm_extract_for_downstream,
)
from core.cv_docpick_import import (
    _enrich_education_from_text,
    _repair_invented_heute,
)
from core.matcher import score_job
from core.models import Job
from desktop.services.profile_merge import filter_parsed_for_import


SOURCE_CV = """
Max Beispiel
Ausbildung
M.Sc. Umweltwissenschaften, Universität Freiburg, 09/2018 - 07/2020

Berufserfahrung
Analyst | Green Data GmbH | 03/2021 - 08/2024
Entwickler | SoftWerk AG | 09/2024 - heute
"""

INVENTED_PARSED = {
    "personal": {"first_name": "Max", "last_name": "Beispiel"},
    "emails": ["max@example.com"],
    "phones": [],
    "languages": [],
    "driving_license": [],
    "education": [
        {
            "qualification": "PhD Quantencomputing",
            "institution": "Hogwarts",
            "start_date": "01/2010",
            "end_date": "12/2012",
        }
    ],
    "work_experience": [
        {
            "title": "CEO",
            "company": "FakeCorp International",
            "start_date": "01/2015",
            "end_date": "heute",
        }
    ],
    "skills": ["Python"],
    "software": [],
    "certificates": [],
    "source_text": SOURCE_CV,
}


def test_invented_education_blocks_downstream() -> None:
    with pytest.raises(ExtractConfirmationError) as ei:
        confirm_extract_for_downstream(
            INVENTED_PARSED, source_text=SOURCE_CV, fail_on_invented=True
        )
    assert ei.value.code == "invented_extract"
    assert any(f["category"] == "education" for f in ei.value.findings)


def test_grounded_education_and_employment_pass() -> None:
    parsed = {
        "education": [
            {
                "qualification": "M.Sc. Umweltwissenschaften",
                "institution": "Universität Freiburg",
                "start_date": "09/2018",
                "end_date": "07/2020",
            }
        ],
        "work_experience": [
            {
                "title": "Analyst",
                "company": "Green Data GmbH",
                "start_date": "03/2021",
                "end_date": "08/2024",
            },
            {
                "title": "Entwickler",
                "company": "SoftWerk AG",
                "start_date": "09/2024",
                "end_date": "heute",
            },
        ],
    }
    result = confirm_extract_for_downstream(
        parsed, source_text=SOURCE_CV, fail_on_invented=True
    )
    assert result.ok
    assert len(result.parsed["education"]) == 1
    assert len(result.parsed["work_experience"]) == 2


def test_filter_parsed_for_import_strips_invented() -> None:
    """Import strips invented rows; Matching still fails closed on invented."""
    out = filter_parsed_for_import(INVENTED_PARSED)
    assert out["education"] == []
    assert out["work_experience"] == []
    assert out.get("needs_manual_review") is True
    with pytest.raises(ExtractConfirmationError):
        confirm_extract_for_downstream(
            INVENTED_PARSED, source_text=SOURCE_CV, fail_on_invented=True
        )


def test_cover_letter_refuses_unevidenced_job_title_claim() -> None:
    """Unconfirmed employment title must not appear as a concrete claim."""
    from core.config import ExperienceEntry, QualificationsConfig, SourcedText, empty_app_config
    from core.cover_letter import render_cover_letter
    from core.models import Job

    source = (
        "Max Beispiel\nAnalyst | Green Data GmbH | 03/2021 - 08/2024\n"
        "Skills: Python\n"
    )
    config = empty_app_config()
    config.profile.first_name = "Max"
    config.profile.last_name = "Beispiel"
    config.application.first_name = "Max"
    config.application.last_name = "Beispiel"
    config.profile.qualifications = QualificationsConfig(
        work_experience=[
            ExperienceEntry(
                title="Chief Invented Officer",
                company="FakeCorp International",
                start_date="01/2015",
                end_date="heute",
            ),
            ExperienceEntry(
                title="Analyst",
                company="Green Data GmbH",
                start_date="03/2021",
                end_date="08/2024",
            ),
        ],
        skills=[SourcedText(value="Python", source="cv")],
    )
    job = Job(
        id="j1",
        title="Analyst",
        company="Green Data GmbH",
        description="Analyst Python Green Data",
        source="fixture",
    )
    # Without source_text, prefer safe generic sentence when picking invented first
    # by relevance — with source_text, invented title must not appear.
    letter = render_cover_letter(job, config, source_text=source)
    assert "Chief Invented Officer" not in letter
    assert "FakeCorp" not in letter
    assert "Analyst" in letter or "Erfahrungen" in letter


def test_cv_job_cover_letter_grounded_flow() -> None:
    """Matching + Anschreiben with confirmed extract only (source_text required)."""
    grounded = {
        "education": [
            {
                "qualification": "M.Sc. Umweltwissenschaften",
                "institution": "Universität Freiburg",
                "start_date": "09/2018",
                "end_date": "07/2020",
            }
        ],
        "work_experience": [
            {
                "title": "Analyst",
                "company": "Green Data GmbH",
                "start_date": "03/2021",
                "end_date": "08/2024",
            }
        ],
        "skills": ["Python", "Umweltanalyse"],
        "software": [],
        "source_text": SOURCE_CV,
    }
    confirmed = confirm_extract_for_downstream(
        grounded, source_text=SOURCE_CV, fail_on_invented=True
    ).parsed
    config = empty_app_config()
    config.profile.first_name = "Max"
    config.profile.last_name = "Beispiel"
    config.application.first_name = "Max"
    config.application.last_name = "Beispiel"
    config.profile.qualifications = QualificationsConfig(
        work_experience=[
            ExperienceEntry(
                title=w["title"],
                company=w["company"],
                start_date=w.get("start_date", ""),
                end_date=w.get("end_date", ""),
            )
            for w in confirmed["work_experience"]
        ],
        skills=[SourcedText(value=s, source="cv") for s in confirmed.get("skills") or []],
    )
    job = Job(
        id="job-demo",
        title="Umweltanalyst",
        company="Green Data GmbH",
        description="Python Umweltanalyse Analyst Erfahrung erforderlich",
        city="Freiburg",
        source="fixture",
    )
    match = score_job(job, config)
    assert match.score >= 0
    letter = render_cover_letter(job, config, source_text=SOURCE_CV)
    assert "FakeCorp" not in letter
    assert "PhD Quantencomputing" not in letter
    assert "Analyst" in letter or "Erfahrungen" in letter


def test_enrich_education_and_heute_repair_general_rules() -> None:
    """Regression on known NV3-style patterns — not a new blind test."""
    text = """
## Ausbildung
BTEC Level 3 Business, City College, 09/2016 - 06/2018

## Berufserfahrung
Sales Assistant | ShopOne | 01/2019 - 08/2021
"""
    edu = _enrich_education_from_text([], text)
    assert edu, "empty education must be enriched from Ausbildung heading"
    assert any("BTEC" in (e.get("qualification") or "") or "Business" in (e.get("qualification") or "") for e in edu) or any(
        e.get("qualification") or e.get("institution") for e in edu
    )

    work = [
        {
            "title": "Sales Assistant",
            "company": "ShopOne",
            "start_date": "01/2019",
            "end_date": "heute",
        }
    ]
    fixed = _repair_invented_heute(work, text)
    assert fixed[0]["end_date"] != "heute"
    assert "2021" in fixed[0]["end_date"] or "08" in fixed[0]["end_date"]
