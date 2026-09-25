"""Headless cover-letter gate: no placeholder letters, no demo queue rows."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from apply.manager import ApplicationManager
from apply.preview import build_application_preview
from core.application_queue import (
    APPLICATION_SOURCE_ALLOWLIST,
    filter_application_queue,
    is_application_source,
)
from core.config import (
    AppConfig,
    ExperienceEntry,
    SourcedText,
    empty_app_config,
)
from core.cover_letter import (
    REFUSAL_REGISTRY,
    CoverLetterRefused,
    CoverReason,
    approve_cover_letter,
    compose_cover_letter,
    phrase_equals,
    phrase_in_text,
    render_cover_letter,
    set_pasted_job_description,
)
from core.database import Database
from core.models import Job, JobStatus
from core.text_normalize import clean_text
from desktop.dev.disposition_fixture import (
    FIXTURE_DESCRIPTION,
    FIXTURE_JOB_ID,
    FIXTURE_SOURCE,
    build_fixture_job,
)
from desktop.i18n import TRANSLATIONS
from scripts.insert_disposition_fixture import insert_fixture, remove_fixture

FORBIDDEN = (
    "meine bisherigen beruflichen Erfahrungen",
    "Gern bringe ich meine bisherigen beruflichen Erfahrungen in Ihr Team ein.",
)


def _cfg(*skills: str, stations: list[ExperienceEntry] | None = None) -> AppConfig:
    cfg = empty_app_config()
    cfg.settings.language = "de"
    cfg.settings.dry_run = True
    cfg.application.first_name = "Erika"
    cfg.application.last_name = "Beispiel"
    cfg.profile.qualifications.skills = [
        SourcedText(value=skill, source="manual") for skill in skills
    ]
    cfg.profile.qualifications.work_experience = list(stations or [])
    return cfg


def _assert_clean(blob: str) -> None:
    for phrase in FORBIDDEN:
        assert phrase not in blob


@pytest.mark.parametrize(
    ("text", "phrase", "hit"),
    [
        ("Bewerbung bei Ihrem Unternehmen", "Ihr Unternehmen", True),
        ("Ihres Unternehmens", "Ihr Unternehmen", True),
        ("Ihren Unternehmen", "Ihr Unternehmen", True),
        ("IHREM   UNTERNEHMEN", "Ihr Unternehmen", True),
        ("Ihre Unternehmung", "Ihr Unternehmen", False),
        ("die Unternehmensberatung Müller", "Ihr Unternehmen", False),
        ("bei der Nordkai Spedition GmbH", "Ihr Unternehmen", False),
        ("Teamwork im Lager", "Team", False),
    ],
)
def test_phrase_normalizer_inflection(text: str, phrase: str, hit: bool):
    assert phrase_in_text(text, phrase) is hit


def test_company_placeholder_uses_the_same_normalizer():
    assert phrase_equals("Ihrem Unternehmen", "Ihr Unternehmen")
    assert phrase_equals("Ihres Unternehmens", "Ihr Unternehmen")
    assert not phrase_equals("Nordkai Spedition GmbH", "Ihr Unternehmen")
    cfg = _cfg("Tourenplanung", stations=[
        ExperienceEntry(title="Disponent", company="Nordkai Spedition GmbH", source="manual"),
    ])
    description = "Anforderungen: Tourenplanung und SAP TM. Die Beschreibung ist vorhanden."
    for company in ("Ihrem Unternehmen", "Ihres Unternehmens", "Ihren Unternehmen", "Firma 0"):
        job = Job(
            id="j-placeholder-company",
            source="indeed",
            title="Dispatcher",
            company=company,
            description=description,
        )
        result = compose_cover_letter(job, cfg)
        assert result.text == ""
        assert result.reason_code == "company_missing"
        assert result.reason_code != "job_incomplete"
        assert company.casefold() not in result.text.casefold()


def test_blocked_demo_action_is_only_hide_demo():
    spec = REFUSAL_REGISTRY[CoverReason.BLOCKED_DEMO]
    assert spec.actions == ("hide_demo",)
    assert TRANSLATIONS["de"]["cover.action.hide_demo"] == "Beispiele ausblenden"
    assert TRANSLATIONS["en"]["cover.action.hide_demo"] == "Hide examples"


def test_refusal_registry_covers_every_gate_code():
    """Enumerate codes from CoverReason. A new member without an entry fails."""
    assert set(REFUSAL_REGISTRY) == set(CoverReason)
    for reason in CoverReason:
        spec = REFUSAL_REGISTRY[reason]
        assert spec.actions
        assert spec.message_key in TRANSLATIONS["de"]
        assert spec.message_key in TRANSLATIONS["en"]
        assert TRANSLATIONS["de"][spec.message_key].strip()
        assert TRANSLATIONS["en"][spec.message_key].strip()


def test_i18n_keys_de_and_en():
    for key in (
        "cover.job_incomplete",
        "cover.no_evidence",
        "cover.demo_excluded",
        "cover.company_missing",
    ):
        assert key in TRANSLATIONS["de"]
        assert key in TRANSLATIONS["en"]
    assert TRANSLATIONS["de"]["cover.job_incomplete"] == "Die Anzeige hat keinen Beschreibungstext."
    assert TRANSLATIONS["en"]["cover.job_incomplete"] == "The job ad has no description."
    assert TRANSLATIONS["de"]["cover.company_missing"] == "In der Anzeige fehlt der Firmenname."
    assert TRANSLATIONS["en"]["cover.company_missing"] == "The company name is missing from the job ad."


def test_empty_and_whitespace_description_refuse_without_placeholder():
    cfg = _cfg("Disposition", stations=[
        ExperienceEntry(title="Disponent", company="Beispiel Spedition", source="manual"),
    ])
    for raw in ("", "   ", "\n\t", "n/a"):
        job = Job(
            id="j-empty",
            source="indeed",
            title="Disponent",
            company="Nordmole Musterlogistik GmbH",
            description=raw,
        )
        result = compose_cover_letter(job, cfg)
        assert result.ok is False
        assert result.reason_code == "job_incomplete"
        assert result.message_key == "cover.job_incomplete"
        assert result.text == ""
        assert result.message("de") == "Die Anzeige hat keinen Beschreibungstext."
        assert result.message("en") == "The job ad has no description."
        _assert_clean(result.message("de"))
        _assert_clean(result.message("en"))
        preview = build_application_preview(job, cfg)
        assert preview.cover_letter_preview == ""
        assert preview.cover_refusal_code == "job_incomplete"
        _assert_clean(preview.text_report())
        try:
            render_cover_letter(job, cfg)
        except CoverLetterRefused as exc:
            assert exc.refusal.reason_code == "job_incomplete"
            _assert_clean(str(exc))
        else:
            raise AssertionError("headless render must not return a letter")


def test_no_evidence_refuses_instead_of_dropping_a_sentence():
    cfg = _cfg("Excel")
    job = Job(
        id="j-none",
        source="indeed",
        title="Disponent",
        company="Nordmole Musterlogistik GmbH",
        description="Tourenplanung und SAP in der Disposition. Anforderungen: Schichtbereitschaft.",
    )
    result = compose_cover_letter(job, cfg)
    assert result.ok is False
    assert result.reason_code == "no_evidence"
    assert result.text == ""
    assert result.message_key == "cover.no_evidence"
    _assert_clean(result.message("de") + result.message("en"))


def test_unmatched_station_is_no_evidence():
    cfg = _cfg(stations=[
        ExperienceEntry(title="Barkeeper", company="Bar Beispiel", source="manual"),
    ])
    job = Job(
        id="j-station",
        source="indeed",
        title="Disponent",
        company="Nordmole Musterlogistik GmbH",
        description="Tourenplanung, SAP und Schicht im Leitstand der Disposition.",
    )
    result = compose_cover_letter(job, cfg)
    assert result.ok is False
    assert result.reason_code == "no_evidence"
    assert result.text == ""
    assert "Barkeeper" not in result.text
    assert "In meiner Tätigkeit als" not in result.text


def test_training_row_is_not_written_as_a_job():
    cfg = _cfg(stations=[
        ExperienceEntry(
            title="Ausbildung zur Fachkraft für Lagerlogistik",
            company="Berufskolleg Beispiel",
            source="cv",
        ),
    ])
    job = Job(
        id="j-training",
        source="indeed",
        title="Fachkraft für Lagerlogistik",
        company="Kistenpfad Logistik GmbH",
        description=(
            "Das bringen Sie mit: eine abgeschlossene Ausbildung zur Fachkraft "
            "für Lagerlogistik. Praktische Stationen nach dieser Ausbildung."
        ),
    )
    result = compose_cover_letter(job, cfg)
    assert result.ok is False
    assert result.text == ""
    assert result.reason_code == "no_evidence"
    assert "Berufskolleg" not in result.text
    assert "Tätigkeit als" not in result.text


def test_school_staff_station_can_still_match_the_ad():
    """A job at a school stays employment. Only the course of study is training."""
    cfg = _cfg(stations=[
        ExperienceEntry(title="Lehrer", company="Berufskolleg Beispiel", source="manual"),
    ])
    job = Job(
        id="j-staff",
        source="indeed",
        title="Lehrer",
        company="Stadt Musterhafen",
        description="Wir suchen eine Lehrkraft. Aufgaben: Unterricht als Lehrer.",
    )
    result = compose_cover_letter(job, cfg)
    assert result.ok is True
    assert "Tätigkeit als Lehrer" in result.text
    assert "Berufskolleg Beispiel" in result.text


def test_matching_skill_without_station_is_enough():
    cfg = _cfg("Tourenplanung")
    job = Job(
        id="j-skill",
        source="indeed",
        title="Disponent",
        company="Nordmole Musterlogistik GmbH",
        description="Wir planen Touren. Anforderungen: Tourenplanung und SAP.",
    )
    result = compose_cover_letter(job, cfg)
    assert result.ok is True
    assert "Tourenplanung" in result.text
    _assert_clean(result.text)


def test_unconfirmed_cv_section_is_not_evidence():
    cfg = _cfg(
        "Tourenplanung",
        stations=[ExperienceEntry(title="Disponent", company="Altspedition", source="cv")],
    )

    class _Review:
        confirmed = False
        confirmed_fields: list[str] = []
        source = "cv"
        uncertain_fields: list[str] = []

    cfg.profile.extract_review = _Review()
    job = Job(
        id="j-cv",
        source="indeed",
        title="Disponent",
        company="Nordmole Musterlogistik GmbH",
        description="Tourenplanung im Leitstand.",
    )
    result = compose_cover_letter(job, cfg)
    assert result.reason_code == "no_evidence"
    assert result.text == ""


def test_confirmed_review_allows_matching_skill():
    cfg = _cfg("Tourenplanung")

    class _Review:
        confirmed = True
        confirmed_fields: list[str] = []
        source = "cv"
        uncertain_fields: list[str] = []

    cfg.profile.extract_review = _Review()
    job = Job(
        id="j-ok",
        source="indeed",
        title="Disponent",
        company="Nordmole Musterlogistik GmbH",
        description="Tourenplanung im Leitstand.",
    )
    result = compose_cover_letter(job, cfg)
    assert result.ok is True
    _assert_clean(result.text)


def test_parser_debt_blocks_evidence(monkeypatch):
    import sys
    import types

    gate = types.SimpleNamespace(blocked=True, reason="needs_confirmation: unconfirmed_extract")
    mod = types.ModuleType("core.parser_debt")
    mod.assess_parser_debt = lambda _config: gate  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "core.parser_debt", mod)

    cfg = _cfg(
        "Tourenplanung",
        stations=[ExperienceEntry(title="Disponent", company="Altspedition", source="manual")],
    )
    job = Job(
        id="j-debt",
        source="indeed",
        title="Disponent",
        company="Nordmole Musterlogistik GmbH",
        description="Tourenplanung und Disposition im Leitstand.",
    )
    result = compose_cover_letter(job, cfg)
    assert result.reason_code == "no_evidence"
    assert result.text == ""
    _assert_clean(result.message("de"))


@pytest.mark.parametrize("company", [
    "",
    "   ",
    "Firma 0",
    "firma 0",
    "Ihr Unternehmen",
    "Ihrem Unternehmen",
    "Ihres Unternehmens",
    "Unternehmen",
    "Company",
    "Musterfirma",
    "Platzhalter",
])
def test_missing_company_refuses_before_a_letter(company: str):
    """Gate before the template. A real description is not job_incomplete."""
    cfg = _cfg("Tourenplanung", stations=[
        ExperienceEntry(title="Disponent", company="Nordkai Spedition GmbH", source="manual"),
    ])
    description = (
        "Die Beschreibung ist vorhanden. Anforderungen: Tourenplanung und SAP TM. "
        "Im Formular steht nur Firma 0."
    )
    job = Job(
        id="j-nocompany",
        source="indeed",
        title="Dispatcher",
        company=company,
        description=description,
    )
    result = compose_cover_letter(job, cfg)
    assert result.ok is False
    assert result.text == ""
    assert result.reason_code == "company_missing"
    assert result.reason_code != "job_incomplete"
    assert result.message("de") == "In der Anzeige fehlt der Firmenname."
    blob = result.message("de") + result.message("en") + result.text
    assert "Ihr Unternehmen" not in blob
    assert "Firma 0" not in result.text
    _assert_clean(blob)
    with pytest.raises(CoverLetterRefused) as caught:
        render_cover_letter(job, cfg)
    assert caught.value.refusal.reason_code == "company_missing"
    assert "Ihr Unternehmen" not in str(caught.value)


def test_demo_source_excluded_from_queue_and_letter(tmp_path: Path):
    demo = Job(
        id="demo-1",
        source="demo",
        title="Dispatcher",
        company="HafenLogistik",
        url="https://jobs.example/6",
        status=JobStatus.QUEUED.value,
        match_score=90,
        description="Tourenplanung in der Disposition.",
    )
    real = Job(
        id="real-1",
        source="indeed",
        title="Disponent",
        company="Nordmole Musterlogistik GmbH",
        status=JobStatus.NEW.value,
        match_score=90,
        description="Tourenplanung.",
    )
    queued = filter_application_queue([demo, real])
    assert [job.id for job in queued] == ["real-1"]

    cfg = _cfg("Tourenplanung", stations=[
        ExperienceEntry(title="Disponent", company="Altspedition", source="manual"),
    ])
    result = compose_cover_letter(demo, cfg)
    assert result.reason_code == "blocked_demo"
    assert result.text == ""
    _assert_clean(result.message("de") + result.message("en"))
    preview = build_application_preview(demo, cfg)
    _assert_clean(preview.text_report())

    cfg_apply = empty_app_config()
    cfg_apply.settings.minimum_match_for_auto_apply = 0
    cfg_apply.application.first_name = "Erika"
    cfg_apply.application.last_name = "Beispiel"
    cfg_apply.application.email = "erika@example.com"
    cfg_apply.application.phone = "+491700000"
    cfg_apply.application.cv_path = "cv.pdf"
    ok, reason = ApplicationManager(cfg_apply, Database(tmp_path / "jobs.db")).can_auto_apply(demo)
    assert ok is False
    assert reason.startswith("source not allowlisted")


def test_pasted_description_uses_clean_text_and_same_gate(tmp_path: Path):
    cfg = _cfg("Tourenplanung")
    job = Job(id="j-paste", source="indeed", title="Disponent", company="Nordmole Musterlogistik GmbH")
    db = Database(tmp_path / "jobs.db")
    refused = set_pasted_job_description(job, "  \n\t ", cfg, db=db)
    assert refused.reason_code == "job_incomplete"
    assert db.get_job(job.id).description == ""

    allowed = set_pasted_job_description(
        job,
        "  Tourenplanung im Leitstand.  ",
        cfg,
        db=db,
    )
    assert allowed.ok is True
    assert job.description == clean_text("  Tourenplanung im Leitstand.  ")
    assert db.get_job(job.id).description == job.description
    assert allowed.description_used == job.description
    _assert_clean(allowed.text)


def test_approval_writes_cover_file_and_description(tmp_path: Path):
    cfg = _cfg("Tourenplanung")
    cfg.root = tmp_path
    description = "Anforderungen: Tourenplanung und SAP in der Disposition."
    job = Job(
        id="job-approve-1",
        source="indeed",
        title="Disponent",
        company="Nordmole Musterlogistik GmbH",
        description=description,
    )
    preview = build_application_preview(job, cfg)
    assert preview.cover_refusal_code == ""
    path = approve_cover_letter(job, cfg, preview.cover_letter_preview)
    assert path == tmp_path / "cover_letters" / "job-approve-1.txt"
    assert path.is_file()
    body = path.read_text(encoding="utf-8")
    assert "Tourenplanung" in body
    _assert_clean(body)
    meta = json.loads((tmp_path / "cover_letters" / "job-approve-1.meta.json").read_text(encoding="utf-8"))
    assert meta["description_used"] == clean_text(description)
    assert meta["job_id"] == job.id

    job.description = "   "
    try:
        approve_cover_letter(job, cfg)
    except CoverLetterRefused as exc:
        assert exc.refusal.reason_code == "job_incomplete"
    else:
        raise AssertionError("approval must not bypass the gate")
    # The earlier approved file stays; a refused approval must not replace it
    # with a placeholder. Re-read and confirm the forbidden phrases are absent.
    _assert_clean(path.read_text(encoding="utf-8"))


def test_hafenlogistik_empty_demo_shape_cannot_render():
    """The reported visual-QA row: title only, empty description, source demo."""
    job = Job(
        id="demo-hafen",
        source="demo",
        title="Dispatcher",
        company="HafenLogistik",
        url="https://jobs.example/6",
        status=JobStatus.QUEUED.value,
        description="",
    )
    cfg = empty_app_config()
    result = compose_cover_letter(job, cfg)
    assert result.ok is False
    assert result.reason_code == "blocked_demo"
    _assert_clean(result.message("de"))
    preview = build_application_preview(job, cfg)
    _assert_clean(preview.text_report())


def test_disposition_fixture_is_synthetic_and_idempotent(tmp_path: Path):
    text = FIXTURE_DESCRIPTION
    midpoint = len(text) // 2
    assert text.lower().find("anforderungen") > midpoint
    assert "Nordmole Musterlogistik GmbH" in text
    assert "Robin Beispiel" in text
    job = build_fixture_job()
    assert job.source == FIXTURE_SOURCE
    assert job.source != "demo"
    assert job.url.startswith("https://jobs.example/")
    assert clean_text(job.description)

    db_path = tmp_path / "jobs.db"
    assert insert_fixture(db_path) == FIXTURE_JOB_ID
    assert insert_fixture(db_path) == FIXTURE_JOB_ID
    db = Database(db_path)
    rows = db.list_jobs(source=FIXTURE_SOURCE, hide_duplicates=False)
    assert len(rows) == 1
    assert rows[0].id == FIXTURE_JOB_ID
    assert rows[0].status == JobStatus.NEW.value
    assert rows[0].status != JobStatus.QUEUED.value
    assert rows[0].description == FIXTURE_DESCRIPTION.strip() or "Anforderungen" in rows[0].description

    cfg = _cfg("Tourenplanung")
    letter = compose_cover_letter(rows[0], cfg)
    assert letter.ok is True
    _assert_clean(letter.text)
    assert "Tourenplanung" in letter.text

def test_allowlist_is_the_portal_scraper_ids():
    from search.bundesagentur import BundesagenturSource
    from search.company_sites import CompanySitesSource
    from search.indeed import IndeedSource
    from search.linkedin import LinkedInSearchSource
    from search.stepstone import StepstoneSource
    from search.xing import XingSource

    assert APPLICATION_SOURCE_ALLOWLIST == {
        BundesagenturSource.source_id,
        IndeedSource.source_id,
        StepstoneSource.source_id,
        XingSource.source_id,
    }
    assert LinkedInSearchSource.source_id not in APPLICATION_SOURCE_ALLOWLIST
    assert CompanySitesSource.source_id not in APPLICATION_SOURCE_ALLOWLIST


def test_queue_skips_fixture_demo_and_unknown_sources():
    rows = [
        Job(id="demo", source="demo", title="Dispatcher", company="HafenLogistik", match_score=99, status=JobStatus.QUEUED.value),
        Job(id="fixture", source="fixture", title="Disponent", company="Nordmole", match_score=99, status=JobStatus.NEW.value),
        Job(id="empty", source="", title="Disponent", company="Nordmole", match_score=99, status=JobStatus.NEW.value),
        Job(id="unknown", source="unknown", title="Disponent", company="Nordmole", match_score=99, status=JobStatus.NEW.value),
        Job(id="indeed", source="indeed", title="Disponent", company="Nordmole", match_score=90, status=JobStatus.NEW.value),
        Job(id="stepstone", source="stepstone", title="Disponent", company="Nordmole", match_score=80, status=JobStatus.NEW.value),
        Job(id="linkedin", source="linkedin", title="Disponent", company="Nordmole", match_score=99, status=JobStatus.NEW.value),
    ]
    queued = filter_application_queue(rows)
    assert [job.id for job in queued] == ["indeed", "stepstone"]
    assert is_application_source(rows[1]) is False
    assert is_application_source(rows[3]) is False
    assert is_application_source(rows[4]) is True
    linkedin = rows[-1]
    assert linkedin.source == "linkedin"
    assert is_application_source(linkedin) is False


def test_linkedin_cannot_auto_apply(tmp_path: Path):
    job = Job(
        id="li-1",
        source="linkedin",
        title="Disponent",
        company="Nordmole Musterlogistik GmbH",
        status=JobStatus.NEW.value,
        match_score=90,
        description="Tourenplanung.",
    )
    assert filter_application_queue([job]) == []
    cfg = empty_app_config()
    cfg.settings.minimum_match_for_auto_apply = 0
    cfg.application.first_name = "Erika"
    cfg.application.last_name = "Beispiel"
    cfg.application.email = "erika@example.com"
    cfg.application.phone = "+491700000"
    cfg.application.cv_path = "cv.pdf"
    ok, reason = ApplicationManager(cfg, Database(tmp_path / "jobs.db")).can_auto_apply(job)
    assert ok is False
    assert reason.startswith("source not allowlisted")


def test_fixture_cover_letter_allowed_demo_refused():
    cfg = _cfg("Tourenplanung")
    description = "Anforderungen: Tourenplanung und SAP in der Disposition."
    fixture = build_fixture_job()
    fixture.description = description
    allowed = compose_cover_letter(fixture, cfg)
    assert fixture.source == "fixture"
    assert fixture.status == JobStatus.NEW.value
    assert allowed.ok is True
    assert "Tourenplanung" in allowed.text
    _assert_clean(allowed.text)

    demo = Job(
        id="demo-cover",
        source="demo",
        title="Dispatcher",
        company="HafenLogistik",
        description=description,
        status=JobStatus.QUEUED.value,
    )
    refused = compose_cover_letter(demo, cfg)
    assert refused.ok is False
    assert refused.reason_code == "blocked_demo"
    assert refused.text == ""
    _assert_clean(refused.message("de"))


def test_disposition_fixture_remove(tmp_path: Path):
    db_path = tmp_path / "jobs.db"
    insert_fixture(db_path)
    assert remove_fixture(db_path) == 1
    assert remove_fixture(db_path) == 0
    assert Database(db_path).get_job(FIXTURE_JOB_ID) is None
