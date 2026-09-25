"""Data-engine rest track: match contract, debt gate, geo, cover claims, portal schema."""

from __future__ import annotations

import pytest

from core.config import (
    AppConfig,
    EducationEntry,
    EmploymentConfig,
    ExperienceEntry,
    ExtractReview,
    JobsConfig,
    LocationConfig,
    QualificationsConfig,
    SearchPreferences,
    SettingsConfig,
    SourcedText,
)
from core.cover_guard import find_unsubstantiated_personal_claims
from core.cover_letter import CoverLetterRefused, render_cover_letter
from core.geo_normalize import normalize_place_fields
from core.geo_resolve import resolve_place
from core.hard_filter import distance_exclude
from core.matcher import score_job
from core.models import Job, RemoteType
from core.parser_debt import assess_parser_debt
from search.bundesagentur import BundesagenturSource
from search.indeed import IndeedSource
from search.job_schema import normalize_portal_job
from search.stepstone import StepstoneSource


def _config(**kwargs) -> AppConfig:
    quals = kwargs.pop("qualifications", None) or QualificationsConfig(
        skills=[SourcedText("Excel", source="manual")],
        work_experience=[
            ExperienceEntry(title="Sachbearbeiter", company="Nord GmbH", source="manual")
        ],
        education=[EducationEntry(qualification="Kaufmann", institution="IHK")],
    )
    review = kwargs.pop("extract_review", None) or ExtractReview()
    loc = kwargs.pop("location", None) or LocationConfig(
        city="Berlin",
        postal_code="10115",
        country="DE",
        home_address="10115 Berlin",
        home_latitude=52.5323,
        home_longitude=13.3846,
        max_distance_km=30,
        allow_remote_germany=True,
        allow_hybrid=True,
    )
    return AppConfig(
        profile=SearchPreferences(
            location=loc,
            jobs=JobsConfig(desired_titles=["Sachbearbeiter"]),
            employment=EmploymentConfig(full_time=True, remote=True, hybrid=True, onsite=True),
            qualifications=quals,
            extract_review=review,
        ),
        settings=SettingsConfig(published_within_days=365, exclude_on_missing_mandatory=False),
    )


def _job(**kwargs) -> Job:
    data = dict(
        title="Sachbearbeiter",
        company="Beispiel GmbH",
        city="Berlin",
        country_code="DE",
        remote_type=RemoteType.ONSITE.value,
        description="Excel Verwaltung im Büro",
        employment_type="Vollzeit",
    )
    data.update(kwargs)
    return Job(**data)


def test_match_decision_requires_title_location_or_work_model_and_verified_home():
    from core.match_contract import evaluate_match_contract

    cfg = _config()
    bare = Job(title="", company="X", remote_type="unknown")
    blocked = evaluate_match_contract(bare, cfg, distance_used=False)
    assert blocked.status == "blocked"
    assert "job_title" in blocked.blockers
    assert "job_location_or_work_model" in blocked.blockers

    remote = Job(title="Sachbearbeiter", company="X", remote_type="remote")
    assert evaluate_match_contract(remote, cfg, distance_used=True).ready

    onsite = Job(title="Sachbearbeiter", company="X", city="Berlin", remote_type="onsite")
    unverified = _config(location=LocationConfig(city="", max_distance_km=25))
    needs_home = evaluate_match_contract(onsite, unverified, distance_used=True)
    assert needs_home.status == "blocked"
    assert "verified_user_location" in needs_home.blockers


def test_missing_cv_fields_are_unknown_and_not_hard_ko():
    cfg = _config(
        qualifications=QualificationsConfig(
            skills=[SourcedText("Excel", source="manual")],
            languages=[],
            education=[],
            driving_license=[],
        )
    )
    cfg.settings.exclude_on_missing_mandatory = True
    job = _job(description="Deutsch C1 erforderlich. Führerschein Klasse B. Excel")
    result = score_job(job, cfg)
    assert result.field_status["languages"] == "unknown"
    assert result.field_status["education"] == "unknown"
    assert result.field_status["driving_license"] == "unknown"
    assert result.field_status["skills"] == "present"
    assert "certificates" in result.field_status
    assert result.exclude_reason != "Mandatory German language missing"
    assert result.exclude_reason != "Mandatory driving license missing"
    assert any("unknown" in r.lower() for r in result.rejection_reasons)


def test_hard_ko_only_when_requirement_evidenced_and_absence_confirmed():
    cfg = _config(
        qualifications=QualificationsConfig(skills=[SourcedText("Excel", source="manual")]),
        extract_review=ExtractReview(
            source="manual",
            confirmed_fields=["languages"],
            field_status={"languages": "absent"},
        ),
    )
    cfg.settings.exclude_on_missing_mandatory = True
    job = _job(description="Deutsch C1 erforderlich. Excel")
    result = score_job(job, cfg)
    assert result.excluded
    assert result.exclude_reason == "Mandatory German language missing"

    # Same absence, but the job text does not evidence a language requirement.
    quiet = _job(description="Excel im Team")
    quiet_result = score_job(quiet, cfg)
    assert quiet_result.exclude_reason != "Mandatory German language missing"


def test_parser_debt_blocks_auto_match_and_cover_letter_until_confirmed():
    quals = QualificationsConfig(
        skills=[SourcedText("Excel", source="cv")],
        education=[],
        work_experience=[
            ExperienceEntry(
                title="Sachbearbeiter",
                company="Alt GmbH",
                end_date="aktuell",
                source="cv",
            )
        ],
    )
    review = ExtractReview(source="cv", uncertain_fields=["education", "work_experience"])
    cfg = _config(qualifications=quals, extract_review=review)
    debt = assess_parser_debt(cfg)
    assert debt.blocked
    assert debt.status == "needs_confirmation"
    assert "missing_education" in debt.patterns
    assert "false_current_job" in debt.patterns

    result = score_job(_job(), cfg)
    assert result.decision_status == "needs_confirmation"
    assert result.score == 0
    assert result.exclude_reason is not None
    assert result.exclude_reason.startswith("needs_confirmation")

    letter = render_cover_letter(_job(description="Kubernetes Zertifikat und SAP"), cfg)
    assert letter == ""

    review.confirmed = True
    opened = assess_parser_debt(cfg)
    assert not opened.blocked
    scored = score_job(_job(), cfg)
    assert scored.decision_status != "needs_confirmation"
    assert scored.score > 0
    confirmed_letter = render_cover_letter(_job(), cfg)
    assert "Sachbearbeiter" in confirmed_letter
    assert confirmed_letter.strip()


def test_manual_current_job_is_not_parser_debt():
    cfg = _config(
        qualifications=QualificationsConfig(
            education=[EducationEntry(qualification="Fachwirt")],
            work_experience=[
                ExperienceEntry(
                    title="Sachbearbeiter",
                    company="Jetzt GmbH",
                    end_date="aktuell",
                    source="manual",
                )
            ],
        )
    )
    assert not assess_parser_debt(cfg).blocked


def _assert_berlin_distance(tmp_path) -> None:
    from core.database import Database
    from core.geo_dataset import GeoDatasetManager
    from core.location import LocationService, enrich_job_locations

    info = GeoDatasetManager(config_root=tmp_path).ensure_active()
    assert info.valid, info.message

    place = normalize_place_fields(city="Berlin, Deutschland")
    resolved = resolve_place(place)
    assert resolved.ok, resolved.reason
    assert resolved.country_code == "DE"
    assert resolved.latitude is not None and 52.3 < resolved.latitude < 52.7
    assert resolved.longitude is not None and 13.0 < resolved.longitude < 13.8
    # Exact name + 35 km spread (same rule as PR #64). Homonyms stay unresolved.
    from core.geo_resolve import resolve_city_pgeocode

    assert resolve_city_pgeocode("Halle", "DE").status == "AMBIGUOUS"
    assert resolve_city_pgeocode("Frankfurt", "DE").status == "AMBIGUOUS"
    halle = resolve_place(normalize_place_fields(city="Halle", country_code="DE"))
    assert not halle.ok
    assert halle.latitude is None and halle.longitude is None

    db = Database(tmp_path / "t.db", recover=False)
    cfg = _config(
        location=LocationConfig(
            city="Berlin",
            postal_code="10115",
            country="DE",
            home_address="10115 Berlin",
            max_distance_km=30,
            allow_remote_germany=True,
            allow_hybrid=True,
        )
    )
    cfg.root = tmp_path
    svc = LocationService(db, cfg)
    job = Job(
        title="Sachbearbeiter",
        company="Beispiel",
        city="Berlin, Deutschland",
        remote_type=RemoteType.ONSITE.value,
    )
    enrich_job_locations([job], svc)
    assert job.distance_km is not None
    assert job.distance_km < 30
    assert distance_exclude(job, cfg) is None
    assert job.country_code == "DE"

    ambiguous = Job(
        title="Sachbearbeiter",
        company="Beispiel",
        city="Halle",
        country_code="DE",
        remote_type=RemoteType.ONSITE.value,
    )
    enrich_job_locations([ambiguous], svc)
    assert ambiguous.latitude is None
    assert ambiguous.longitude is None
    assert ambiguous.distance_km is None
    from core.matcher import apply_distance_scoring

    ambiguous.match_score = 80
    ambiguous.status = "new"
    apply_distance_scoring(ambiguous, cfg)
    assert ambiguous.status != "ignored"
    assert ambiguous.distance_km is None


def test_substring_city_stays_unknown_and_multi_name_stays_ambiguous(monkeypatch):
    """A partial name is never promoted to a centroid.

    One substring hit stays UNKNOWN. Several distinct names are AMBIGUOUS
    and carry no coordinates. Exact place_name still resolves.
    """
    import pandas as pd

    from core.geo_resolve import resolve_city_pgeocode

    class _Nom:
        def __init__(self, names: list[str]) -> None:
            self._data = pd.DataFrame(
                {
                    "place_name": names,
                    "latitude": [52.5 + i * 0.01 for i in range(len(names))],
                    "longitude": [13.4] * len(names),
                }
            )

        def query_location(self, *_args, **_kwargs):
            raise AssertionError("query_location must not resolve a city")

    def _install(names: list[str]) -> None:
        monkeypatch.setattr("core.geo_resolve._ensure_geo_data", lambda: "test")
        monkeypatch.setattr("core.geo_resolve._pgeocode_nominatim", lambda _cc: _Nom(names))

    _install(["Berlin"])
    partial = resolve_city_pgeocode("Berl", "DE")
    assert partial.status == "UNKNOWN"
    assert partial.latitude is None and partial.longitude is None

    exact = resolve_city_pgeocode("Berlin", "DE")
    assert exact.status == "RESOLVED"
    assert exact.latitude is not None and exact.longitude is not None

    _install(["Berlin", "Bernau"])
    many = resolve_city_pgeocode("Ber", "DE")
    assert many.status == "AMBIGUOUS"
    assert many.latitude is None and many.longitude is None


def test_berlin_deutschland_resolves_for_distance_filter(tmp_path):
    from core.geo_dataset import reset_geo_dataset_manager_for_tests
    from core.geo_resolve import reset_pgeocode_index_for_tests

    reset_geo_dataset_manager_for_tests()
    reset_pgeocode_index_for_tests()
    active = tmp_path / "geo_active"
    import os

    previous = os.environ.get("KARRIEREKRAKE_GEO_DATA_DIR")
    os.environ["KARRIEREKRAKE_GEO_DATA_DIR"] = str(active)
    try:
        _assert_berlin_distance(tmp_path)
    finally:
        reset_geo_dataset_manager_for_tests()
        reset_pgeocode_index_for_tests()
        if previous is None:
            os.environ.pop("KARRIEREKRAKE_GEO_DATA_DIR", None)
        else:
            os.environ["KARRIEREKRAKE_GEO_DATA_DIR"] = previous


def test_unconfirmed_extract_blocks_auto_match_without_a_fake_score():
    from core.match_contract import auto_match_allowed

    quals = QualificationsConfig(
        skills=[SourcedText("Excel", source="cv")],
        education=[EducationEntry(qualification="Kaufmann", institution="IHK", source="cv")],
        work_experience=[
            ExperienceEntry(
                title="Sachbearbeiter",
                company="Alt GmbH",
                end_date="2019",
                source="cv",
            )
        ],
    )
    cfg = _config(
        qualifications=quals,
        extract_review=ExtractReview(source="cv", confirmed=False),
    )
    result = score_job(_job(), cfg)
    assert result.decision_status == "needs_confirmation"
    assert result.score == 0
    assert "unconfirmed_extract" in (result.exclude_reason or "")
    allowed, why = auto_match_allowed(cfg, _job(), distance_used=False)
    assert not allowed
    assert why.startswith("needs_confirmation")
    with pytest.raises(CoverLetterRefused):
        render_cover_letter(_job(), cfg)

    cfg.profile.extract_review.confirmed = True
    allowed_after, _ = auto_match_allowed(cfg, _job(), distance_used=False)
    assert allowed_after


def test_cover_letter_does_not_claim_job_ad_requirements():
    cfg = _config()
    job = _job(
        description=(
            "Wir suchen Kubernetes-Zertifikat und fünf Jahre SAP. "
            "Excel ist willkommen."
        )
    )
    letter = render_cover_letter(job, cfg)
    assert letter.strip()
    low = letter.casefold()
    assert "kubernetes" not in low
    assert "sap" not in low
    assert "excel" in low

    violations = find_unsubstantiated_personal_claims(
        "Ich besitze ein Kubernetes-Zertifikat und bringe fünf Jahre SAP mit.",
        confirmed_text="Excel Sachbearbeitung",
        job_text="Kubernetes Zertifikat und SAP",
    )
    assert violations
    assert any("kubernetes" in v.casefold() or "sap" in v.casefold() for v in violations)

    paraphrased = find_unsubstantiated_personal_claims(
        "Ich bringe meine Excel-Kenntnisse in die Sachbearbeitung ein.",
        confirmed_text="Excel Sachbearbeitung Kaufmann",
        job_text="Excel Sachbearbeitung Kubernetes",
    )
    assert paraphrased == []

    invented = find_unsubstantiated_personal_claims(
        "Ich habe bei XYZ Company die Conversion um 20 % gesteigert und Kubernetes genutzt.",
        confirmed_text="Excel Sachbearbeitung",
        job_text="Kubernetes SAP",
        allowed_context="Beispiel GmbH",
    )
    assert invented
    blob = " ".join(invented).casefold()
    assert "xyz" in blob or "20" in blob or "kubernetes" in blob


def test_portal_schema_strips_html_and_normalizes_location():
    indeed = IndeedSource().normalize(
        {
            "title": "<b>Sachbearbeiter (m/w/d)</b>",
            "company": "Beispiel &amp; Sohn",
            "location": "Berlin, Deutschland",
            "job_url": "https://example.com/job/1",
            "description": "<p>Excel im <b>Team</b></p><script>alert(1)</script>",
            "id": "abc",
            "is_remote": False,
        }
    )
    assert indeed is not None
    assert "<" not in indeed.title
    assert "<" not in indeed.description
    assert "alert" not in indeed.description
    assert "Excel" in indeed.description
    assert indeed.city == "Berlin"
    assert indeed.country_code == "DE"
    assert indeed.remote_type in {"onsite", "hybrid", "remote", "unknown"}
    assert "Sohn" in indeed.company

    step = StepstoneSource().normalize(
        {
            "@type": "JobPosting",
            "title": "Kaufmännische Assistenz",
            "url": "https://www.stepstone.de/job/9",
            "hiringOrganization": {"name": "Beispiel AG"},
            "jobLocation": {
                "address": {
                    "addressLocality": "München, Deutschland",
                    "addressCountry": "DE",
                }
            },
            "description": "<div>Homeoffice <i>möglich</i></div>",
            "jobLocationType": "TELECOMMUTE",
        }
    )
    assert step is not None
    assert step.city == "München"
    assert step.country_code == "DE"
    assert "<" not in step.description
    assert step.remote_type == "remote"

    ba = BundesagenturSource().normalize(
        {
            "referenznummer": "10000-1",
            "stellenangebotsTitel": "<b>Bürokaufmann</b>",
            "firma": "Amt GmbH",
            "stellenlokationen": [
                {"adresse": {"ort": "Hamburg, Deutschland", "plz": "20095"}}
            ],
            "hauptberuf": "<p>Verwaltung</p><script>nope()</script>",
        }
    )
    assert ba is not None
    assert "<" not in (ba.title or "")
    assert "<" not in (ba.description or "")
    assert "nope" not in (ba.description or "")
    assert ba.city == "Hamburg"
    assert ba.postal_code == "20095"
    assert ba.country_code == "DE"

    dirty = Job(
        title="  Dev  ",
        company="nan",
        description="<style>.x{}</style><p>Code</p>",
        remote_type="home-office",
        city="Leipzig, Deutschland",
    )
    cleaned = normalize_portal_job(dirty)
    assert cleaned.company == ""
    assert cleaned.description == "Code"
    assert cleaned.remote_type == "remote"
    assert cleaned.city == "Leipzig"
    assert cleaned.country_code == "DE"
