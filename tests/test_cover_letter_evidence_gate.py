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
    LanguageEntry,
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
        "cover.profile_changed_evidence_lost",
    ):
        assert key in TRANSLATIONS["de"]
        assert key in TRANSLATIONS["en"]
    assert TRANSLATIONS["de"]["cover.job_incomplete"] == "Die Anzeige hat keinen Beschreibungstext."
    assert TRANSLATIONS["en"]["cover.job_incomplete"] == "The job ad has no description."
    assert TRANSLATIONS["de"]["cover.company_missing"] == "In der Anzeige fehlt der Firmenname."
    assert TRANSLATIONS["en"]["cover.company_missing"] == "The company name is missing from the job ad."
    assert TRANSLATIONS["de"]["cover.profile_changed_evidence_lost"] == (
        "Das Profil hat sich seit der Vorschau geändert. "
        "Der Brief hat nicht mehr zwei verschiedene belegte Bezüge."
    )
    assert TRANSLATIONS["en"]["cover.profile_changed_evidence_lost"] == (
        "The profile changed since the preview. "
        "The letter no longer has two different evidenced references."
    )


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
    cfg = _cfg(
        "Unterricht",
        stations=[
            ExperienceEntry(
                title="Lehrer",
                company="Berufskolleg Beispiel",
                start_date="2019-03",
                end_date="2024-08",
                source="manual",
            ),
        ],
    )
    job = Job(
        id="j-staff",
        source="indeed",
        title="Lehrer",
        company="Stadt Musterhafen",
        description="Wir suchen eine Lehrkraft. Aufgaben: Unterricht als Lehrer.",
    )
    result = compose_cover_letter(job, cfg)
    assert result.ok is True
    assert "als Lehrer" in result.text
    assert "Berufskolleg Beispiel" in result.text
    assert "von 2019 bis 2024" in result.text


def test_one_matching_skill_is_not_enough():
    cfg = _cfg("Tourenplanung")
    job = Job(
        id="j-skill",
        source="indeed",
        title="Disponent",
        company="Nordmole Musterlogistik GmbH",
        description="Wir planen Touren. Anforderungen: Tourenplanung und SAP.",
    )
    result = compose_cover_letter(job, cfg)
    assert result.ok is False
    assert result.reason_code == "no_evidence"
    assert result.text == ""


def test_two_matching_skills_without_a_station_are_not_enough():
    cfg = _cfg("Tourenplanung", "SAP")
    job = Job(
        id="j-skills",
        source="indeed",
        title="Disponent",
        company="Nordmole Musterlogistik GmbH",
        description="Wir planen Touren. Anforderungen: Tourenplanung und SAP.",
    )
    result = compose_cover_letter(job, cfg)
    assert result.ok is False
    assert result.reason_code == "no_evidence"
    assert result.text == ""
    assert "Tourenplanung" in result.found_references
    assert "SAP" in result.found_references


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
    cfg = _cfg(
        "Tourenplanung",
        "Leitstand",
        stations=[
            ExperienceEntry(
                title="Disponent",
                company="Nordkai Spedition GmbH",
                start_date="2019-03",
                end_date="2024-08",
                source="manual",
            )
        ],
    )

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
    cfg = _cfg(
        "Tourenplanung",
        "Leitstand",
        stations=[
            ExperienceEntry(
                title="Disponent",
                company="Nordkai Spedition GmbH",
                responsibilities=["Tourenplanung für Stückgut"],
                source="manual",
            )
        ],
    )
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
    cfg = _cfg(
        "Tourenplanung",
        "SAP",
        stations=[
            ExperienceEntry(
                title="Disponent",
                company="Nordkai Spedition GmbH",
                responsibilities=["Tourenplanung für Stückgut"],
                source="manual",
            )
        ],
    )
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
    assert preview.cover_profile_fingerprint
    path = approve_cover_letter(
        job,
        cfg,
        preview.cover_letter_preview,
        generated_sha256=preview.cover_letter_sha256,
        profile_fingerprint=preview.cover_profile_fingerprint,
    )
    assert path == tmp_path / "cover_letters" / "job-approve-1.txt"
    assert path.is_file()
    body = path.read_text(encoding="utf-8")
    assert "Tourenplanung" in body
    _assert_clean(body)
    meta = json.loads((tmp_path / "cover_letters" / "job-approve-1.meta.json").read_text(encoding="utf-8"))
    assert meta["description_used"] == clean_text(description)
    assert meta["job_id"] == job.id
    assert meta["edited"] is False
    assert meta["generated_sha256"]

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

    cfg = _cfg(
        "Tourenplanung",
        "SAP",
        stations=[
            ExperienceEntry(
                title="Disponent",
                company="Nordkai Spedition GmbH",
                responsibilities=["Tourenplanung für Stückgut"],
                source="manual",
            )
        ],
    )
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
    """Abruf über JobSpy, ungetestet. Deshalb nicht in der Bewerbungsschlange."""
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


def test_n_jobs_do_not_compile_evidence_patterns(monkeypatch):
    """N jobs against one warmed profile must not compile another pattern."""
    import inspect
    import re

    from core.cover_letter import cached_profile_evidence

    cfg = _cfg(
        "Tourenplanung",
        stations=[
            ExperienceEntry(
                title="Disponent",
                company="Nordkai Spedition GmbH",
                responsibilities=["Tourenplanung für Stückgut"],
                source="manual",
            )
        ],
    )
    cached_profile_evidence(cfg)

    compiled: list[str] = []
    real_compile = re.compile
    real_search = re.search
    real_fullmatch = re.fullmatch
    real_split = re.split
    real_findall = re.findall

    def _called_from_cover(pattern: object) -> bool:
        if not isinstance(pattern, str):
            return False
        frame = inspect.currentframe()
        caller = frame.f_back if frame is not None else None
        name = caller.f_code.co_filename if caller is not None else ""
        return name.endswith("cover_letter.py")

    def counting_compile(pattern, flags=0):
        compiled.append(str(pattern))
        return real_compile(pattern, flags)

    def counting_search(pattern, *args, **kwargs):
        if _called_from_cover(pattern):
            compiled.append("search:" + str(pattern))
        return real_search(pattern, *args, **kwargs)

    def counting_fullmatch(pattern, *args, **kwargs):
        if _called_from_cover(pattern):
            compiled.append("fullmatch:" + str(pattern))
        return real_fullmatch(pattern, *args, **kwargs)

    def counting_split(pattern, *args, **kwargs):
        if _called_from_cover(pattern):
            compiled.append("split:" + str(pattern))
        return real_split(pattern, *args, **kwargs)

    def counting_findall(pattern, *args, **kwargs):
        if _called_from_cover(pattern):
            compiled.append("findall:" + str(pattern))
        return real_findall(pattern, *args, **kwargs)

    monkeypatch.setattr(re, "compile", counting_compile)
    monkeypatch.setattr(re, "search", counting_search)
    monkeypatch.setattr(re, "fullmatch", counting_fullmatch)
    monkeypatch.setattr(re, "split", counting_split)
    monkeypatch.setattr(re, "findall", counting_findall)

    jobs = [
        Job(
            id="demo-n",
            source="demo",
            title="Disponent",
            company="Nordmole GmbH",
            description="Tourenplanung im Leitstand.",
        )
    ]
    for index in range(24):
        if index % 7 == 0:
            description = ""
        elif index % 2 == 0:
            description = f"Anforderungen: Tourenplanung und SAP. Schicht {index}."
        else:
            description = f"Backstube, Torten und Dekoration. Fall {index}."
        company = "Ihr Unternehmen" if index % 5 == 0 else f"Nordmole {index} GmbH"
        title = "Disponent" if index % 2 == 0 else "Konditor"
        jobs.append(
            Job(
                id=f"n-{index}",
                source="indeed",
                title=title,
                company=company,
                description=description,
            )
        )
    for job in jobs:
        compose_cover_letter(job, cfg)
    assert compiled == []


def test_fixture_cover_letter_allowed_demo_refused():
    cfg = _cfg(
        "Tourenplanung",
        "SAP",
        stations=[
            ExperienceEntry(
                title="Disponent",
                company="Nordkai Spedition GmbH",
                responsibilities=["Tourenplanung für Stückgut"],
                source="manual",
            )
        ],
    )
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


def test_company_name_only_is_not_a_reference():
    cfg = _cfg(stations=[
        ExperienceEntry(
            title="Disponent",
            company="Nordkai Spedition GmbH",
            responsibilities=["Kommissionierung"],
            source="manual",
        ),
    ])
    job = Job(
        id="j-employer",
        source="indeed",
        title="Konditor",
        company="Zuckerkai Konditorei GmbH",
        description="Frühere Beschäftigung bei der Nordkai Spedition GmbH. Gesucht wird eine Kraft für die Backstube.",
    )
    result = compose_cover_letter(job, cfg)
    assert result.reason_code == "no_evidence"
    assert result.text == ""


def test_one_task_word_does_not_qualify_a_station():
    cfg = _cfg(stations=[
        ExperienceEntry(
            title="Hilfskraft",
            company="Hof Beispiel",
            responsibilities=["Tourenplanung für den Hof"],
            source="manual",
        ),
    ])
    job = Job(
        id="j-one-task",
        source="indeed",
        title="Disponent",
        company="Nordmole Musterlogistik GmbH",
        description="Anforderungen: Tourenplanung im Leitstand.",
    )
    result = compose_cover_letter(job, cfg)
    assert result.reason_code == "no_evidence"
    assert result.text == ""


def test_excel_and_ms_excel_are_one_ad_requirement():
    cfg = _cfg("Excel")
    cfg.profile.qualifications.software = [SourcedText(value="MS Excel", source="manual")]
    job = Job(
        id="j-excel",
        source="indeed",
        title="Sachbearbeitung",
        company="Kontor Beispiel GmbH",
        description="Sicherer Umgang mit MS Excel im Tagesgeschäft.",
    )
    result = compose_cover_letter(job, cfg)
    assert result.reason_code == "no_evidence"
    assert result.text == ""
    from core.cover_letter import cover_letter_reference_hits

    hits, missing = cover_letter_reference_hits("", job, cfg)
    assert hits == ()
    assert len(missing) == 1


def test_sap_station_and_sap_skill_are_one_requirement():
    cfg = _cfg("SAP", stations=[
        ExperienceEntry(title="SAP-Sachbearbeiter", company="Kontor Beispiel", source="manual"),
    ])
    job = Job(
        id="j-sap",
        source="indeed",
        title="Sachbearbeitung",
        company="Nordmole Musterlogistik GmbH",
        description="Kenntnisse in SAP im Tagesgeschäft.",
    )
    result = compose_cover_letter(job, cfg)
    assert result.reason_code == "no_evidence"
    assert result.text == ""


def test_two_stations_are_returned_and_written():
    from core.cover_letter import _matching_stations

    stations = [
        ExperienceEntry(
            title="Disponent",
            company="Nordkai Spedition GmbH",
            start_date="2019-03",
            end_date="2024-08",
            source="manual",
        ),
        ExperienceEntry(
            title="Fachlagerist",
            company="Kistenwerk Ost GmbH",
            start_date="2016-09",
            end_date="2019-02",
            source="manual",
        ),
    ]
    cfg = _cfg(stations=stations)
    job = Job(
        id="j-two",
        source="indeed",
        title="Teamleitung Umschlag",
        company="Kaiwerk GmbH",
        description="Erfahrung als Disponent und eine Station als Fachlagerist.",
    )
    matched = _matching_stations(cfg, job)
    assert [item.title for item in matched] == ["Disponent", "Fachlagerist"]
    result = compose_cover_letter(job, cfg)
    assert result.ok is True
    assert "Disponent" in result.text
    assert "Fachlagerist" in result.text
    assert "Nordkai Spedition GmbH" in result.text
    assert "Kistenwerk Ost GmbH" in result.text


def test_reference_hits_follow_the_saved_text():
    from core.cover_letter import cover_letter_reference_hits

    cfg = _cfg(
        "Tourenplanung",
        "SAP",
        stations=[
            ExperienceEntry(
                title="Disponent",
                company="Nordkai Spedition GmbH",
                responsibilities=["Tourenplanung für Stückgut"],
                source="manual",
            )
        ],
    )
    job = Job(
        id="j-hits",
        source="indeed",
        title="Disponent",
        company="Nordmole Musterlogistik GmbH",
        description="Anforderungen: Tourenplanung und SAP.",
    )
    result = compose_cover_letter(job, cfg)
    hits, missing = cover_letter_reference_hits(result.text, job, cfg)
    assert "Tourenplanung" in hits
    assert "SAP" in hits
    assert missing == ()
    shorter = result.text.replace("SAP", "")
    hits_after, missing_after = cover_letter_reference_hits(shorter, job, cfg)
    assert "SAP" not in hits_after
    assert "SAP" in missing_after


def test_no_evidence_and_blocked_demo_do_not_call_the_model(monkeypatch):
    import core.cover_letter as cover

    monkeypatch.setattr(cover, "_COVER_MODEL_CALLS", 0)

    def boom(job, config, missing, attempt):
        raise AssertionError("model hook must not run")

    monkeypatch.setattr(cover, "_COVER_MODEL_FN", boom)
    cfg = _cfg("Excel")
    no_evidence = Job(
        id="j-none-model",
        source="indeed",
        title="Disponent",
        company="Nordmole Musterlogistik GmbH",
        description="Tourenplanung und SAP in der Disposition.",
    )
    demo = Job(
        id="demo-model",
        source="demo",
        title="Dispatcher",
        company="HafenLogistik",
        description="Tourenplanung und SAP und Excel in der Disposition.",
    )
    refused = compose_cover_letter(no_evidence, cfg)
    blocked = compose_cover_letter(demo, cfg)
    assert refused.reason_code == "no_evidence"
    assert refused.text == ""
    assert blocked.reason_code == "blocked_demo"
    assert blocked.text == ""
    assert cover.cover_model_calls() == 0


def test_model_path_retries_once_then_refuses(monkeypatch):
    import core.cover_letter as cover

    monkeypatch.setattr(cover, "_COVER_MODEL_CALLS", 0)
    attempts: list[int] = []

    def always_short(job, config, missing, attempt):
        attempts.append(attempt)
        return "Hier steht nur Excel."

    monkeypatch.setattr(cover, "_COVER_MODEL_FN", always_short)
    cfg = _cfg(
        "Excel",
        "SAP",
        stations=[
            ExperienceEntry(
                title="Disponent",
                company="Nord GmbH",
                start_date="2019-01",
                end_date="2024-01",
                source="manual",
            )
        ],
    )
    job = Job(
        id="j-model",
        source="indeed",
        title="Sachbearbeitung",
        company="Kontor Beispiel GmbH",
        description="Excel und SAP im Tagesgeschäft eines Disponenten.",
    )
    refused = compose_cover_letter(job, cfg)
    assert refused.reason_code == "no_evidence"
    assert refused.text == ""
    assert attempts == [0, 1]
    assert cover.cover_model_calls() == 2

    monkeypatch.setattr(cover, "_COVER_MODEL_CALLS", 0)
    attempts.clear()

    def second_is_complete(job, config, missing, attempt):
        attempts.append(attempt)
        if attempt == 0:
            return "Hier steht nur Excel."
        assert "SAP" in missing
        return (
            "Bei der Nord GmbH war ich von 2019 bis 2024 als Disponent. "
            "Excel und SAP habe ich in der Anzeige gefunden."
        )

    monkeypatch.setattr(cover, "_COVER_MODEL_FN", second_is_complete)
    saved = compose_cover_letter(job, cfg)
    assert saved.ok is True
    assert "Excel" in saved.text
    assert "SAP" in saved.text
    assert attempts == [0, 1]
    assert cover.cover_model_calls() == 2


def test_approve_saves_user_edit_and_refuses_empty_or_placeholder(tmp_path: Path):
    import hashlib

    cfg = _cfg(
        "Tourenplanung",
        "SAP",
        stations=[
            ExperienceEntry(
                title="Disponent",
                company="Nordkai Spedition GmbH",
                responsibilities=["Tourenplanung für Stückgut"],
                source="manual",
            )
        ],
    )
    cfg.root = tmp_path
    description = "Anforderungen: Tourenplanung und SAP in der Disposition."
    job = Job(
        id="job-edit-1",
        source="indeed",
        title="Disponent",
        company="Nordmole Musterlogistik GmbH",
        description=description,
    )
    generated = compose_cover_letter(job, cfg)
    assert generated.ok is True
    edited = generated.text.replace("SAP", "Tabellen")
    assert "SAP" not in edited
    sha = generated.generated_sha256
    from core.cover_letter import cover_profile_fingerprint

    fingerprint = cover_profile_fingerprint(cfg)
    path = approve_cover_letter(
        job, cfg, edited, generated_sha256=sha, profile_fingerprint=fingerprint
    )
    assert path.read_text(encoding="utf-8") == edited
    meta = json.loads((tmp_path / "cover_letters" / "job-edit-1.meta.json").read_text(encoding="utf-8"))
    assert meta["edited"] is True
    assert meta["generated_sha256"] == hashlib.sha256(generated.text.encode("utf-8")).hexdigest()
    assert "SAP" not in path.read_text(encoding="utf-8")

    with pytest.raises(CoverLetterRefused):
        approve_cover_letter(
            job, cfg, "   \n\t", generated_sha256=sha, profile_fingerprint=fingerprint
        )
    with pytest.raises(CoverLetterRefused):
        approve_cover_letter(
            job,
            cfg,
            "Gern bringe ich meine bisherigen beruflichen Erfahrungen in Ihr Team ein.\n",
            generated_sha256=sha,
            profile_fingerprint=fingerprint,
        )


def test_sap_business_one_covers_sap_not_the_reverse():
    from core.cover_letter import cover_letter_reference_hits

    station = ExperienceEntry(
        title="Rechnungsprüfung",
        company="Kontor Beispiel GmbH",
        start_date="2019-04",
        end_date="2024-06",
        source="manual",
    )
    specific = _cfg(stations=[station])
    specific.profile.qualifications.software = [
        SourcedText(value="SAP Business One", source="manual")
    ]
    ad_sap = Job(
        id="j-sap-family",
        source="indeed",
        title="Rechnungsprüfung",
        company="Buchkontor Beispiel GmbH",
        description="Erfahrung in der Rechnungsprüfung und sicherer Umgang mit SAP.",
    )
    written = compose_cover_letter(ad_sap, specific)
    assert written.ok is True
    assert "SAP Business One" in written.text
    assert "setze ich SAP ein." not in written.text
    assert "Rechnungsprüfung" in written.text
    hits, missing = cover_letter_reference_hits(written.text, ad_sap, specific)
    assert "SAP Business One" in hits
    assert "Rechnungsprüfung" in hits
    assert missing == ()

    only = _cfg()
    only.profile.qualifications.software = [SourcedText(value="SAP Business One", source="manual")]
    alone = compose_cover_letter(ad_sap, only)
    assert alone.reason_code == "no_evidence"
    assert alone.text == ""
    assert alone.found_references == ("SAP Business One",)

    broad = _cfg(stations=[station])
    broad.profile.qualifications.software = [SourcedText(value="SAP", source="manual")]
    ad_product = Job(
        id="j-sap-reverse",
        source="indeed",
        title="Rechnungsprüfung",
        company="Buchkontor Beispiel GmbH",
        description="Erfahrung in der Rechnungsprüfung und SAP Business One im Tagesgeschäft.",
    )
    reverse = compose_cover_letter(ad_product, broad)
    assert reverse.reason_code == "no_evidence"
    assert reverse.text == ""
    reverse_hits, _reverse_missing = cover_letter_reference_hits("", ad_product, broad)
    assert "SAP" not in reverse_hits


def test_sentence_break_splits_sap_and_excel():
    cfg = _cfg(
        "Excel",
        stations=[
            ExperienceEntry(
                title="Büroorganisation",
                company="Nord GmbH",
                start_date="2019-01",
                end_date="2024-01",
                source="manual",
            )
        ],
    )
    job = Job(
        id="j-period",
        source="indeed",
        title="Büroorganisation",
        company="Beispiel GmbH",
        description="Wir suchen Kubernetes-Zertifikat und fünf Jahre SAP. Excel und Büroorganisation sind willkommen.",
    )
    result = compose_cover_letter(job, cfg)
    assert result.ok is True
    low = result.text.casefold()
    assert "excel" in low
    assert "sap" not in low
    assert "kubernetes" not in low


def test_java_does_not_hit_javascript():
    station = ExperienceEntry(
        title="Rechnungsprüfung",
        company="Kontor Beispiel GmbH",
        start_date="2019-04",
        end_date="2024-06",
        source="manual",
    )
    java = _cfg(stations=[station])
    java.profile.qualifications.software = [SourcedText(value="Java", source="manual")]
    javascript_ad = Job(
        id="j-javascript",
        source="indeed",
        title="Rechnungsprüfung",
        company="Buchkontor Beispiel GmbH",
        description="Erfahrung in der Rechnungsprüfung und JavaScript im Frontend.",
    )
    missed = compose_cover_letter(javascript_ad, java)
    assert missed.reason_code == "no_evidence"

    script = _cfg(stations=[station])
    script.profile.qualifications.software = [SourcedText(value="JavaScript", source="manual")]
    java_ad = Job(
        id="j-java",
        source="indeed",
        title="Rechnungsprüfung",
        company="Buchkontor Beispiel GmbH",
        description="Erfahrung in der Rechnungsprüfung und Java im Backend.",
    )
    also_missed = compose_cover_letter(java_ad, script)
    assert also_missed.reason_code == "no_evidence"

    same = compose_cover_letter(java_ad, java)
    assert same.ok is True
    assert "Java" in same.text
    assert "JavaScript" not in same.text


def test_deutsch_and_licence_are_not_references_on_nordmole():
    from core.cover_letter import cover_letter_reference_hits

    job = build_fixture_job()
    payroll = _cfg(
        stations=[
            ExperienceEntry(
                title="Lohnbuchhalterin",
                company="Lohnkontor Beispiel GmbH",
                responsibilities=["Lohnabrechnung erstellen"],
                source="manual",
            )
        ]
    )
    payroll.profile.qualifications.software = [
        SourcedText(value="DATEV", source="manual"),
        SourcedText(value="Excel", source="manual"),
    ]
    payroll.profile.qualifications.languages = [
        LanguageEntry(language="Deutsch", level="C2", source="manual")
    ]
    payroll.profile.qualifications.driving_license = [
        SourcedText(value="Klasse B", source="manual")
    ]
    refused = compose_cover_letter(job, payroll)
    assert refused.reason_code == "no_evidence"
    assert refused.text == ""
    hits, _missing = cover_letter_reference_hits("", job, payroll)
    folded = " ".join(hits).casefold()
    assert "deutsch" not in folded
    assert "führerschein" not in folded
    assert "klasse b" not in folded
    assert "excel" not in folded
    assert "datev" not in folded

    dispatcher = _cfg(
        stations=[
            ExperienceEntry(
                title="Disponent",
                company="Nordkai Spedition GmbH",
                responsibilities=["Tourenplanung", "Fahrer zuordnen"],
                source="manual",
            )
        ]
    )
    dispatcher.profile.qualifications.software = [SourcedText(value="SAP", source="manual")]
    dispatcher.profile.qualifications.languages = [
        LanguageEntry(language="Deutsch", level="C2", source="manual")
    ]
    dispatcher.profile.qualifications.driving_license = [
        SourcedText(value="Klasse B", source="manual")
    ]
    written = compose_cover_letter(job, dispatcher)
    assert written.ok is True
    assert "Disponent" in written.text
    assert "SAP" in written.text
    letter_hits, letter_missing = cover_letter_reference_hits(written.text, job, dispatcher)
    assert "Disponent" in letter_hits
    assert "SAP" in letter_hits
    assert letter_missing == ()
    named = " ".join(letter_hits).casefold()
    assert "deutsch" not in named
    assert "klasse b" not in named
    assert "führerschein" not in named


def test_facts_are_built_once_per_job_and_profile():
    import core.cover_letter as cover

    cover._FACTS_SLOT = None
    counts = {"builder": 0, "station": 0}
    build = cover._build_cover_facts
    station = cover._station_keys

    def counted_build(*args, **kwargs):
        counts["builder"] += 1
        return build(*args, **kwargs)

    def counted_station(*args, **kwargs):
        counts["station"] += 1
        return station(*args, **kwargs)

    cover._build_cover_facts = counted_build
    cover._station_keys = counted_station
    try:
        cfg = _cfg(
            "SAP",
            stations=[
                ExperienceEntry(
                    title="Disponent",
                    company="Nordkai Spedition GmbH",
                    start_date="2019-03",
                    end_date="2024-08",
                    source="manual",
                )
            ],
        )
        job = Job(
            id="j-once",
            source="indeed",
            title="Disponent",
            company="Nordmole Musterlogistik GmbH",
            description="Anforderungen: Disponent und SAP im Leitstand.",
        )
        result = compose_cover_letter(job, cfg)
        assert result.ok is True
        assert counts == {"builder": 1, "station": 1}
        cover.cover_letter_reference_hits("Vorschau ohne die Bezüge.", job, cfg)
        assert counts == {"builder": 1, "station": 1}
    finally:
        cover._build_cover_facts = build
        cover._station_keys = station
        cover._FACTS_SLOT = None


def test_available_references_come_from_facts_not_missing():
    from core.cover_letter import available_cover_references, cover_letter_reference_hits

    cfg = _cfg()
    cfg.profile.qualifications.software = [SourcedText(value="SAP Business One", source="manual")]
    job = Job(
        id="j-available",
        source="indeed",
        title="Buchhaltung",
        company="Buchkontor Beispiel GmbH",
        description="Sicherer Umgang mit SAP.",
    )
    import core.cover_letter as cover

    facts = cover._cover_facts(job, cfg)
    available = available_cover_references(facts)
    hits, missing = cover_letter_reference_hits("", job, cfg, facts=facts)
    assert available == ("SAP Business One",)
    assert hits == ()
    assert len(available) != 0
    result = compose_cover_letter(job, cfg)
    assert result.reason_code == "no_evidence"
    assert result.found_references == available
    assert result.found_references != missing or missing == available


def test_generic_title_word_does_not_qualify_a_station():
    cfg = _cfg(
        stations=[
            ExperienceEntry(title="Sachbearbeiter Lohn", company="Kontor Beispiel GmbH", source="manual")
        ]
    )
    job = Job(
        id="j-generic-title",
        source="indeed",
        title="Sachbearbeiter Einkauf",
        company="Einkauf Beispiel GmbH",
        description="Gesucht wird ein Sachbearbeiter Einkauf für die Beschaffung.",
    )
    result = compose_cover_letter(job, cfg)
    assert result.reason_code == "no_evidence"
    assert result.text == ""


def test_two_generic_task_words_do_not_qualify():
    cfg = _cfg(
        stations=[
            ExperienceEntry(
                title="Hilfskraft",
                company="Hof Beispiel",
                responsibilities=["Betreuung der Ablage", "Erstellung von Listen"],
                source="manual",
            )
        ]
    )
    job = Job(
        id="j-generic-tasks",
        source="indeed",
        title="Bürohilfe",
        company="Amt Beispiel GmbH",
        description="Aufgaben: Betreuung der Vorgänge und Erstellung der Unterlagen.",
    )
    result = compose_cover_letter(job, cfg)
    assert result.reason_code == "no_evidence"
    assert result.text == ""


def test_composite_key_does_not_merge_distinct_requirements():
    from core.cover_letter import _CoverFact, _assign_cover_facts, _unify_requirements

    facts = _unify_requirements(
        [
            _CoverFact("skill:sap", "skill", "SAP", frozenset({"tok:sap"}), 0, "", ""),
            _CoverFact(
                "station:sb",
                "station",
                "Sachbearbeiter",
                frozenset({"tok:sachbearbeiter"}),
                1,
                "Sachbearbeiter",
                "Kontor",
            ),
            _CoverFact(
                "span",
                "station",
                "SAP-Sachbearbeiter",
                frozenset({"tok:sachbearbeiter|sap"}),
                1,
                "SAP-Sachbearbeiter",
                "Kontor",
            ),
        ]
    )
    assigned = _assign_cover_facts(facts)
    roots = {root for _fact, root in assigned}
    assert "tok:sap" in roots or any(root.endswith("sap") and "sachbearbeiter" not in root for root in roots)
    assert any("sachbearbeiter" in root and root != "tok:sachbearbeiter|sap" for root in roots)
    assert len(assigned) >= 2


def test_enumeration_is_not_a_reference_via_text_check():
    from core.cover_letter import cover_letter_reference_hits

    cfg = _cfg("Tourenplanung", "SAP")
    job = Job(
        id="j-list",
        source="indeed",
        title="Disponent",
        company="Nordmole Musterlogistik GmbH",
        description="Anforderungen: Tourenplanung und SAP.",
    )
    listed = "Zu meinen relevanten Kenntnissen zählen insbesondere: SAP, Tourenplanung."
    hits, _missing = cover_letter_reference_hits(listed, job, cfg)
    assert cover_letter_reference_hits.accepted is False
    refused = compose_cover_letter(job, cfg)
    assert refused.reason_code == "no_evidence"
    assert "Tourenplanung" in hits
    assert "SAP" in hits


def test_enumeration_is_not_a_reference_via_model_hook(monkeypatch):
    import core.cover_letter as cover

    monkeypatch.setattr(cover, "_COVER_MODEL_CALLS", 0)

    def only_a_list(job, config, missing, attempt):
        return "Aufzählung: Disponent, Tourenplanung für Stückgut, SAP."

    monkeypatch.setattr(cover, "_COVER_MODEL_FN", only_a_list)
    cfg = _cfg(
        "SAP",
        stations=[
            ExperienceEntry(
                title="Disponent",
                company="Nordkai Spedition GmbH",
                responsibilities=["Tourenplanung für Stückgut"],
                source="manual",
            )
        ],
    )
    job = Job(
        id="j-list-model",
        source="indeed",
        title="Disponent",
        company="Nordmole Musterlogistik GmbH",
        description="Anforderungen: Tourenplanung und SAP.",
    )
    refused = compose_cover_letter(job, cfg)
    assert refused.reason_code == "no_evidence"
    assert refused.text == ""
    assert refused.ok is False
    assert cover.cover_model_calls() == 2


def test_letter_uses_profile_wording_for_sap_business_one():
    cfg = _cfg(
        stations=[
            ExperienceEntry(
                title="Rechnungsprüfung",
                company="Kontor Beispiel GmbH",
                responsibilities=["Belege erfassen"],
                start_date="2019-04",
                end_date="2024-06",
                source="manual",
            )
        ]
    )
    cfg.profile.qualifications.software = [SourcedText(value="SAP Business One", source="manual")]
    job = Job(
        id="j-wording",
        source="indeed",
        title="Rechnungsprüfung",
        company="Buchkontor Beispiel GmbH",
        description="Rechnungsprüfung und SAP im Tagesgeschäft.",
    )
    result = compose_cover_letter(job, cfg)
    assert result.ok is True
    assert "Belege erfassen" in result.text
    assert "SAP Business One" in result.text
    assert "in der Rechnungsprüfung" in result.text
    assert "als Rechnungsprüfung" not in result.text
    assert "Für die ausgeschriebene Aufgabe" not in result.text
    assert "setze ich" not in result.text


def test_shortened_company_still_counts():
    from core.cover_letter import cover_letter_reference_hits

    cfg = _cfg(
        "SAP",
        stations=[
            ExperienceEntry(
                title="Disponent",
                company="Nordmole Musterlogistik GmbH",
                start_date="2019-03",
                end_date="2024-08",
                source="manual",
            )
        ],
    )
    job = Job(
        id="j-short-company",
        source="indeed",
        title="Disponent",
        company="Kaiwerk GmbH",
        description="Anforderungen: Disponent und SAP.",
    )
    generated = compose_cover_letter(job, cfg)
    assert generated.ok is True
    shortened = generated.text.replace("Nordmole Musterlogistik GmbH", "Nordmole")
    assert "Nordmole Musterlogistik GmbH" not in shortened
    hits, missing = cover_letter_reference_hits(shortened, job, cfg)
    assert "Disponent" in hits
    assert "SAP" in hits
    assert missing == ()


def test_crlf_and_trailing_space_are_not_an_edit(tmp_path: Path):
    cfg = _cfg(
        "Tourenplanung",
        "SAP",
        stations=[
            ExperienceEntry(
                title="Disponent",
                company="Nordkai Spedition GmbH",
                responsibilities=["Tourenplanung für Stückgut"],
                source="manual",
            )
        ],
    )
    cfg.root = tmp_path
    job = Job(
        id="job-crlf",
        source="indeed",
        title="Disponent",
        company="Nordmole Musterlogistik GmbH",
        description="Anforderungen: Tourenplanung und SAP.",
    )
    generated = compose_cover_letter(job, cfg)
    assert generated.ok is True
    messy = "\r\n".join(line + "   " for line in generated.text.split("\n"))
    from core.cover_letter import cover_profile_fingerprint

    path = approve_cover_letter(
        job,
        cfg,
        messy,
        generated_sha256=generated.generated_sha256,
        profile_fingerprint=cover_profile_fingerprint(cfg),
    )
    meta = json.loads((tmp_path / "cover_letters" / "job-crlf.meta.json").read_text(encoding="utf-8"))
    assert meta["edited"] is False
    assert meta["generated_sha256"] == generated.generated_sha256
    assert path.read_text(encoding="utf-8") == generated.text


def test_approve_without_preview_hash_is_refused(tmp_path: Path, caplog):
    import logging

    cfg = _cfg(
        "SAP",
        stations=[
            ExperienceEntry(
                title="Disponent",
                company="Nordkai Spedition GmbH",
                responsibilities=["Tourenplanung für Stückgut"],
                source="manual",
            )
        ],
    )
    cfg.root = tmp_path
    job = Job(
        id="job-no-hash",
        source="indeed",
        title="Disponent",
        company="Nordmole Musterlogistik GmbH",
        description="Anforderungen: Tourenplanung für Stückgut und SAP.",
    )
    generated = compose_cover_letter(job, cfg)
    assert generated.ok is True
    with caplog.at_level(logging.ERROR):
        with pytest.raises(ValueError, match="Hash"):
            approve_cover_letter(job, cfg, generated.text)
    assert "hash" in caplog.text.casefold()
    assert not (tmp_path / "cover_letters" / "job-no-hash.txt").exists()


def test_only_the_matching_station_task_counts():
    from core.cover_letter import cover_letter_reference_hits

    cfg = _cfg(
        "SAP",
        stations=[
            ExperienceEntry(
                title="Disponent",
                company="Nordkai Spedition GmbH",
                responsibilities=["Tourenplanung für Stückgut", "Belege erfassen"],
                start_date="2019-03",
                end_date="2024-08",
                source="manual",
            )
        ],
    )
    job = Job(
        id="j-matching-task",
        source="indeed",
        title="Disponent",
        company="HafenLogistik GmbH",
        description="Anforderungen: Tourenplanung für Stückgut und SAP.",
    )
    written = compose_cover_letter(job, cfg)
    assert written.ok is True
    assert "Tourenplanung für Stückgut" in written.text
    assert "Belege erfassen" not in written.text
    bad = (
        "Bei der Nordkai Spedition GmbH war ich von 2019 bis 2024 als Disponent "
        "für die Belege erfassen zuständig. SAP steht in der Anzeige."
    )
    cover_letter_reference_hits(bad, job, cfg)
    assert cover_letter_reference_hits.accepted is False


def test_station_without_tasks_or_period_does_not_count():
    from core.cover_letter import ALLOW_STATION_WITHOUT_TASKS_OR_PERIOD

    assert ALLOW_STATION_WITHOUT_TASKS_OR_PERIOD is False
    cfg = _cfg(
        "Tourenplanung",
        stations=[
            ExperienceEntry(
                title="Disponent",
                company="Nordkai Spedition GmbH",
                source="manual",
            )
        ],
    )
    job = Job(
        id="j-bare-station",
        source="indeed",
        title="Disponent",
        company="HafenLogistik GmbH",
        description="Anforderungen: Disponent und Tourenplanung.",
    )
    result = compose_cover_letter(job, cfg)
    assert result.reason_code == "no_evidence"
    assert result.text == ""
    assert result.stations_without_tasks == ("Nordkai Spedition GmbH, Disponent",)
    assert "Tourenplanung" in result.found_references


def test_unclosed_contact_tag_keeps_the_general_salutation():
    cfg = _cfg(
        "SAP",
        stations=[
            ExperienceEntry(
                title="Disponent",
                company="Nordkai Spedition GmbH",
                responsibilities=["Tourenplanung für Stückgut"],
                source="manual",
            )
        ],
    )
    job = Job(
        id="j-broken-html",
        source="indeed",
        title="Disponent",
        company="HafenLogistik GmbH",
        description=(
            "Anforderungen: Tourenplanung für Stückgut und SAP.\n"
            "Ansprechpartnerin: Frau <Quendel"
        ),
    )
    result = compose_cover_letter(job, cfg)
    assert result.ok is True
    assert result.text.startswith("Sehr geehrte Damen und Herren,")
    assert "Quendel" not in result.text.split("\n", 1)[0]


def _dated_station_cfg() -> AppConfig:
    return _cfg(
        "Tourenplanung",
        "SAP",
        stations=[
            ExperienceEntry(
                title="Disponent",
                company="Nordkai Spedition GmbH",
                responsibilities=["Tourenplanung für Stückgut"],
                start_date="2019-03",
                end_date="2024-08",
                source="manual",
            )
        ],
    )


def _dispatch_job(job_id: str) -> Job:
    return Job(
        id=job_id,
        source="indeed",
        title="Disponent",
        company="Nordmole Musterlogistik GmbH",
        description="Anforderungen: Tourenplanung für Stückgut und SAP.",
    )


def test_approve_same_profile_does_not_rebuild_facts(tmp_path: Path):
    import core.cover_letter as cover

    cfg = _dated_station_cfg()
    cfg.root = tmp_path
    job = _dispatch_job("job-fp-same")
    preview = build_application_preview(job, cfg)
    assert preview.cover_profile_fingerprint == cover.cover_profile_fingerprint(cfg)
    cover._FACTS_SLOT = None
    counts = {"builder": 0}
    build = cover._build_cover_facts

    def counted(*args, **kwargs):
        counts["builder"] += 1
        return build(*args, **kwargs)

    cover._build_cover_facts = counted
    try:
        with pytest.raises(ValueError, match="Hash"):
            approve_cover_letter(
                job,
                cfg,
                preview.cover_letter_preview,
                profile_fingerprint=preview.cover_profile_fingerprint,
            )
        assert counts["builder"] == 0
        assert not (tmp_path / "cover_letters" / "job-fp-same.txt").exists()

        cfg.application.phone = "040 123456"
        assert cover.cover_profile_fingerprint(cfg) == preview.cover_profile_fingerprint
        path = approve_cover_letter(
            job,
            cfg,
            preview.cover_letter_preview,
            generated_sha256=preview.cover_letter_sha256,
            profile_fingerprint=preview.cover_profile_fingerprint,
        )
        assert counts["builder"] == 0
        assert path.is_file()
        meta = json.loads(path.with_suffix(".meta.json").read_text(encoding="utf-8"))
        assert meta["edited"] is False
        assert meta["generated_sha256"] == preview.cover_letter_sha256
    finally:
        cover._build_cover_facts = build
        cover._FACTS_SLOT = None


def test_approve_irrelevant_profile_change_still_saves(tmp_path: Path):
    import core.cover_letter as cover

    cfg = _dated_station_cfg()
    cfg.root = tmp_path
    job = _dispatch_job("job-fp-skill")
    preview = build_application_preview(job, cfg)
    cfg.profile.qualifications.skills.append(SourcedText(value="Origami", source="manual"))
    assert cover.cover_profile_fingerprint(cfg) != preview.cover_profile_fingerprint
    cover._FACTS_SLOT = None
    counts = {"builder": 0}
    build = cover._build_cover_facts

    def counted(*args, **kwargs):
        counts["builder"] += 1
        return build(*args, **kwargs)

    cover._build_cover_facts = counted
    try:
        path = approve_cover_letter(
            job,
            cfg,
            preview.cover_letter_preview,
            generated_sha256=preview.cover_letter_sha256,
            profile_fingerprint=preview.cover_profile_fingerprint,
        )
        assert counts["builder"] == 1
        assert path.is_file()
        body = path.read_text(encoding="utf-8")
        assert body == preview.cover_letter_preview
        assert "Origami" not in body
        meta = json.loads(path.with_suffix(".meta.json").read_text(encoding="utf-8"))
        assert meta["edited"] is False
    finally:
        cover._build_cover_facts = build
        cover._FACTS_SLOT = None


def test_approve_rejects_when_station_deleted_after_preview(tmp_path: Path, caplog):
    import logging

    import core.cover_letter as cover

    cfg = _dated_station_cfg()
    cfg.root = tmp_path
    job = _dispatch_job("job-fp-deleted")
    preview = build_application_preview(job, cfg)
    assert preview.cover_refusal_code == ""
    cfg.profile.qualifications.work_experience.clear()
    assert cover.cover_profile_fingerprint(cfg) != preview.cover_profile_fingerprint
    cover._FACTS_SLOT = None
    counts = {"builder": 0}
    build = cover._build_cover_facts

    def counted(*args, **kwargs):
        counts["builder"] += 1
        return build(*args, **kwargs)

    cover._build_cover_facts = counted
    target = tmp_path / "cover_letters" / "job-fp-deleted.txt"
    try:
        with caplog.at_level(logging.ERROR):
            with pytest.raises(CoverLetterRefused) as exc:
                approve_cover_letter(
                    job,
                    cfg,
                    preview.cover_letter_preview,
                    generated_sha256=preview.cover_letter_sha256,
                    profile_fingerprint=preview.cover_profile_fingerprint,
                )
        assert counts["builder"] == 1
        assert exc.value.refusal.reason_code == "profile_changed_evidence_lost"
        assert exc.value.refusal.message_key == "cover.profile_changed_evidence_lost"
        assert "profile_changed_evidence_lost" in caplog.text
        assert "Ergänze, was du dort gemacht hast." not in exc.value.refusal.text("de")
        assert not target.exists()
        assert not target.with_suffix(".meta.json").exists()
    finally:
        cover._build_cover_facts = build
        cover._FACTS_SLOT = None


def test_requirement_named_by_the_station_is_not_repeated_as_skill():
    cfg = _cfg(
        "Tourenplanung",
        stations=[
            ExperienceEntry(
                title="Disponent",
                company="Nordkai Spedition GmbH",
                responsibilities=["Tourenplanung für Stückgut"],
                start_date="2019-03",
                end_date="2024-08",
                source="manual",
            )
        ],
    )
    cfg.profile.qualifications.software = [SourcedText(value="SAP", source="manual")]
    job = Job(
        id="j-once-req",
        source="indeed",
        title="Disponent",
        company="HafenLogistik GmbH",
        description="Anforderungen: Disponent, Tourenplanung für Stückgut und SAP.",
    )
    result = compose_cover_letter(job, cfg)
    assert result.ok is True
    assert result.text.count("Tourenplanung") == 1
    assert "Praktische Erfahrung habe ich mit SAP." in result.text
    assert "steht in der Anzeige" not in result.text
    assert "deckt einen Punkt der Anzeige ab" not in result.text
    assert "genannt in der Anzeige" not in result.text


def test_skill_context_is_taken_from_the_ad_sentence():
    cfg = _cfg(
        stations=[
            ExperienceEntry(
                title="Disponent",
                company="Nordkai Spedition GmbH",
                responsibilities=["Schichtkoordination im Lager"],
                start_date="2019-03",
                end_date="2024-08",
                source="manual",
            )
        ],
    )
    cfg.profile.qualifications.software = [SourcedText(value="SAP TM", source="manual")]
    cfg.profile.qualifications.skills = [SourcedText(value="Excel", source="manual")]
    marked = Job(
        id="j-skill-context",
        source="indeed",
        title="Disponent",
        company="HafenLogistik GmbH",
        description=(
            "Gesucht wird ein Disponent für die Schichtkoordination im Lager. "
            "Sicherer Umgang mit SAP TM im Tagesgeschäft setzen wir voraus."
        ),
    )
    written = compose_cover_letter(marked, cfg)
    assert written.ok is True
    assert (
        "Mit SAP TM, das Sie im Tagesgeschäft voraussetzen, habe ich praktische Erfahrung."
        in written.text
    )
    assert "Excel" not in written.text

    plain = Job(
        id="j-skill-plain",
        source="indeed",
        title="Disponent",
        company="HafenLogistik GmbH",
        description="Gesucht wird ein Disponent. SAP TM und Excel stehen zur Auswahl.",
    )
    cfg.profile.qualifications.skills = [SourcedText(value="Excel", source="manual")]
    both = compose_cover_letter(plain, cfg)
    assert both.ok is True
    assert "Praktische Erfahrung habe ich mit Excel." in both.text
    assert "Praktische Erfahrung habe ich außerdem mit SAP TM." in both.text


def test_feminine_skill_uses_die_in_the_requirement_clause():
    cfg = _cfg(
        "Tourenplanung",
        stations=[
            ExperienceEntry(
                title="Disponent",
                company="Nordkai Spedition GmbH",
                responsibilities=["Schichtkoordination im Lager"],
                start_date="2019-03",
                end_date="2024-08",
                source="manual",
            )
        ],
    )
    job = Job(
        id="j-feminine-skill",
        source="indeed",
        title="Disponent",
        company="HafenLogistik GmbH",
        description=(
            "Gesucht wird ein Disponent für die Schichtkoordination im Lager. "
            "Umgang mit Tourenplanung im Lager ist erforderlich."
        ),
    )
    result = compose_cover_letter(job, cfg)
    assert result.ok is True
    assert (
        "Mit Tourenplanung, die Sie im Lager voraussetzen, habe ich praktische Erfahrung."
        in result.text
    )


def test_verb_and_noun_tasks_are_not_mixed():
    cfg = _cfg(
        "SAP",
        stations=[
            ExperienceEntry(
                title="Disponent",
                company="Nordkai Spedition GmbH",
                responsibilities=["Tourenplanung", "Fahrer zuordnen"],
                start_date="2019-03",
                end_date="2024-08",
                source="manual",
            )
        ],
    )
    job = Job(
        id="j-verb-noun",
        source="indeed",
        title="Disponent",
        company="Nordmole Musterlogistik GmbH",
        description="Anforderungen: Tourenplanung, Fahrer zuordnen und SAP.",
    )
    result = compose_cover_letter(job, cfg)
    assert result.ok is True
    assert "für die Tourenplanung zuständig." in result.text
    assert "Zu meinen Aufgaben gehörte dort: Fahrer zuordnen." in result.text
    assert "für die Fahrer zuordnen" not in result.text
    assert "übernommen" not in result.text


def test_noun_without_a_known_gender_has_no_article():
    cfg = _cfg(
        "SAP",
        stations=[
            ExperienceEntry(
                title="Disponent",
                company="Nordkai Spedition GmbH",
                responsibilities=["Excel"],
                start_date="2019-03",
                end_date="2024-08",
                source="manual",
            )
        ],
    )
    job = Job(
        id="j-no-article",
        source="indeed",
        title="Disponent",
        company="Nordmole Musterlogistik GmbH",
        description="Anforderungen: Disponent, Excel und SAP im Leitstand.",
    )
    result = compose_cover_letter(job, cfg)
    assert result.ok is True
    assert "für Excel zuständig." in result.text
    assert "für die Excel" not in result.text


def test_bare_stations_use_two_sentence_shapes():
    cfg = _cfg(
        stations=[
            ExperienceEntry(
                title="Disponent",
                company="Nordkai Spedition GmbH",
                start_date="2019-03",
                end_date="2024-08",
                source="manual",
            ),
            ExperienceEntry(
                title="Fachlagerist",
                company="Kistenwerk Ost GmbH",
                start_date="2016-09",
                end_date="2019-02",
                source="manual",
            ),
        ],
    )
    job = Job(
        id="j-two-shapes",
        source="indeed",
        title="Teamleitung Umschlag (m/w/d)",
        company="Kaiwerk GmbH",
        description="Erfahrung als Disponent und eine Station als Fachlagerist.",
    )
    result = compose_cover_letter(job, cfg)
    assert result.ok is True
    assert "Bei der Nordkai Spedition GmbH war ich von 2019 bis 2024 als Disponent tätig." in result.text
    assert (
        "Ich habe von 2016 bis 2019 bei der Kistenwerk Ost GmbH als Fachlagerist gearbeitet."
        in result.text
    )
    assert "als Fachlagerist." not in result.text
    assert result.text.count("war ich") == 1


def test_activity_field_opening_says_stelle():
    cfg = _cfg(
        stations=[
            ExperienceEntry(
                title="Rechnungsprüfung",
                company="Kontor Beispiel GmbH",
                responsibilities=["Belege erfassen"],
                start_date="2019-04",
                end_date="2024-06",
                source="manual",
            )
        ]
    )
    cfg.profile.qualifications.software = [SourcedText(value="SAP Business One", source="manual")]
    job = Job(
        id="j-stelle",
        source="indeed",
        title="Rechnungsprüfung (m/w/d)",
        company="Buchkontor Beispiel GmbH",
        description="Erfahrung in der Rechnungsprüfung und sicherer Umgang mit SAP.",
    )
    result = compose_cover_letter(job, cfg)
    assert result.ok is True
    assert "um die Stelle in der Rechnungsprüfung (m/w/d)" in result.text
    assert "um die Position Rechnungsprüfung" not in result.text
    assert "Zu meinen Aufgaben gehörte dort: Belege erfassen." in result.text
    assert "als Rechnungsprüfung" not in result.text
    assert "übernommen" not in result.text
