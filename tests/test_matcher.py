"""Matcher and hard-filter tests."""

from core.config import (
    AppConfig,
    EmploymentConfig,
    ExperienceEntry,
    FiltersConfig,
    JobsConfig,
    LanguageEntry,
    LocationConfig,
    ProfileConfig,
    QualificationsConfig,
    SettingsConfig,
)
from core.matcher import score_job
from core.models import Job


def _config(**qual_overrides) -> AppConfig:
    quals = QualificationsConfig(
        skills=["Excel", "Kommunikation"],
        languages=[LanguageEntry(language="Deutsch", level="C2")],
        driving_license=["Klasse B (PKW)"],
        software=["Shopify"],
        certificates=[],
        education=[],
        work_experience=[],
    )
    for k, v in qual_overrides.items():
        setattr(quals, k, v)
    return AppConfig(
        profile=ProfileConfig(
            location=LocationConfig(max_distance_km=20, allow_remote_germany=True, allow_hybrid=True),
            jobs=JobsConfig(desired_titles=["Sachbearbeiter"], unwanted_titles=["Praktikant"]),
            employment=EmploymentConfig(full_time=True, remote=True, hybrid=True, onsite=True),
            qualifications=quals,
            filters=FiltersConfig(desired_keywords=["Verwaltung"], excluded_companies=["BadCorp"]),
        ),
        settings=SettingsConfig(published_within_days=30),
    )


def test_exclude_far_onsite():
    from core.hard_filter import distance_exclude
    from core.matcher import apply_distance_scoring

    job = Job(
        title="Sachbearbeiter",
        company="ACME",
        remote_type="onsite",
        distance_km=35,
        description="Excel Verwaltung Deutsch",
    )
    result = score_job(job, _config(), apply_distance=False)
    assert not result.excluded  # fachlich OK
    job.match_score = result.score
    job.match_reasons = list(result.match_reasons)
    job.rejection_reasons = list(result.rejection_reasons)
    assert distance_exclude(job, _config()) is not None
    apply_distance_scoring(job, _config())
    assert job.status == "ignored" or any("km" in (r or "") for r in job.rejection_reasons)


def test_remote_no_distance_penalty():
    job = Job(
        title="Sachbearbeiter Verwaltung",
        company="ACME",
        remote_type="remote",
        distance_km=500,
        description="Excel Kommunikation Deutsch Verwaltung",
        employment_type="fulltime",
    )
    result = score_job(job, _config())
    assert not result.excluded
    assert result.score >= 60
    assert any("remote" in r.lower() for r in result.match_reasons)


def test_excluded_company():
    job = Job(title="Sachbearbeiter", company="BadCorp AG", remote_type="remote", description="x")
    result = score_job(job, _config())
    assert result.excluded


def test_nearby_score_reasons():
    job = Job(
        title="Sachbearbeiter",
        company="Good",
        remote_type="onsite",
        distance_km=7.2,
        description="Excel Verwaltung Deutsch Kommunikation",
        employment_type="Vollzeit",
    )
    result = score_job(job, _config())
    assert result.score > 50
    assert result.match_reasons


def test_distance_soft_score_respects_max_distance_km():
    """Soft scoring must not hardcode ≤20 km when the user configured a wider commute."""
    from core.matcher import _distance_points

    pts, reason, issue = _distance_points(35.0, "onsite", max_distance_km=50.0)
    assert pts > 0
    assert issue is None
    assert reason is not None
    assert "35" in reason

    pts_over, reason_over, issue_over = _distance_points(55.0, "onsite", max_distance_km=50.0)
    assert pts_over == 0
    assert issue_over is not None
    assert reason_over is None

    cfg = _config()
    cfg.profile.location.max_distance_km = 50.0
    job = Job(
        title="Sachbearbeiter",
        company="Good",
        remote_type="onsite",
        distance_km=35.0,
        description="Excel Verwaltung Deutsch Kommunikation",
        employment_type="Vollzeit",
    )
    result = score_job(job, cfg, apply_distance=True)
    assert not result.excluded
    assert any("35" in r and ("50" in r or "Luftlinie" in r) for r in result.match_reasons)


def test_matcher_uses_driving_license_class_b():
    job = Job(
        title="Aufriebsfahrer",
        company="Logistik",
        remote_type="onsite",
        distance_km=5,
        description="Führerschein Klasse B erforderlich Excel",
        employment_type="Vollzeit",
    )
    result = score_job(job, _config())
    assert any("klasse b" in r.lower() or "driving" in r.lower() for r in result.match_reasons)


def test_matcher_uses_language_level():
    job = Job(
        title="Sachbearbeiter",
        company="Intl",
        remote_type="remote",
        description="Englisch C1 und Deutsch erforderlich Verwaltung Excel",
        employment_type="Vollzeit",
    )
    cfg = _config(
        languages=[
            LanguageEntry(language="Deutsch", level="C2"),
            LanguageEntry(language="Englisch", level="C1"),
        ]
    )
    result = score_job(job, cfg)
    assert any("language" in r.lower() or "englisch" in r.lower() for r in result.match_reasons)


def test_matcher_uses_experience_responsibilities():
    cfg = _config(
        work_experience=[
            ExperienceEntry(
                title="Disponentin",
                company="Nordhafen Logistik",
                responsibilities=[
                    "Tourenplanung und Disposition",
                    "Reklamationsbearbeitung im Versand",
                ],
            )
        ]
    )
    job = Job(
        title="Disponent",
        company="Shop",
        remote_type="remote",
        description="Reklamationsbearbeitung Disposition Tourenplanung Excel Deutsch",
        employment_type="Vollzeit",
    )
    result = score_job(job, cfg)
    assert any("experience" in r.lower() or "reklamation" in r.lower() or "touren" in r.lower() for r in result.match_reasons)


def test_empty_default_profile_has_no_fake_skills():
    from core.config import load_config, CONFIG_DIR

    cfg = load_config(
        profile_path=CONFIG_DIR / "profile.yaml.example",
        strip_placeholders=True,
    )
    assert cfg.profile.qualifications.skills == []
    assert cfg.profile.qualifications.software == []
    assert cfg.profile.qualifications.languages == []
