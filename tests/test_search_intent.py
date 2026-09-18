"""PR22: SearchIntent domain — validation, roundtrip, migration, Tester A/B goldens."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from core.config import (
    EmploymentConfig,
    FiltersConfig,
    JobsConfig,
    LocationConfig,
    QualificationsConfig,
    SearchPreferences,
    empty_app_config,
    ensure_search_intent,
    load_config,
    save_config,
)
from core.config import ExperienceEntry, SourcedText
from core.search_intent import (
    SEARCH_INTENT_SCHEMA_VERSION,
    SearchIntent,
    Strictness,
    apply_clear_jobs_edit_to_intent,
    empty_search_intent,
    golden_tester_a_payroll_strict,
    golden_tester_b_sap_mandatory,
    migrate_legacy_search_preferences,
    parse_search_intent,
    sync_legacy_jobs_from_intent,
)


def _paths(tmp_path: Path) -> dict:
    cfg = tmp_path / "config"
    cfg.mkdir(parents=True, exist_ok=True)
    return dict(
        profile_path=cfg / "profile.yaml",
        application_path=cfg / "application_profile.yaml",
        settings_path=cfg / "settings.yaml",
    )


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------


def test_schema_version_constant():
    assert SEARCH_INTENT_SCHEMA_VERSION >= 1
    assert empty_search_intent().schema_version == SEARCH_INTENT_SCHEMA_VERSION


def test_empty_intent_ignores_geo_defaults_for_is_empty():
    """Location defaults must not make intent 'non-empty' and block title lift."""
    intent = SearchIntent(countries=["DE"], radius_km=20.0, working_time=["full_time"])
    assert intent.is_empty()
    intent2 = SearchIntent(target_roles=["Buchhalter"], countries=["DE"])
    assert not intent2.is_empty()


def test_save_lifts_desired_titles_when_intent_only_has_geo(tmp_path: Path):
    cfg = empty_app_config(root=tmp_path)
    cfg.profile.search_intent = SearchIntent(countries=["DE"], radius_km=20.0)
    cfg.profile.jobs.desired_titles = ["Sachbearbeiter", "Assistent"]
    paths = _paths(tmp_path)
    save_config(cfg, **paths)
    text = paths["profile_path"].read_text(encoding="utf-8")
    assert "Sachbearbeiter" in text
    loaded = load_config(**paths, root=tmp_path, strip_placeholders=False)
    assert loaded.profile.jobs.desired_titles == ["Sachbearbeiter", "Assistent"]
    assert loaded.profile.search_intent.target_roles == ["Sachbearbeiter", "Assistent"]



def test_rejects_unknown_strictness():
    with pytest.raises(ValidationError):
        SearchIntent(strictness="aggressive")


def test_rejects_unknown_remote_mode():
    with pytest.raises(ValidationError):
        SearchIntent(remote_mode="wherever")


def test_rejects_extra_fields():
    with pytest.raises(ValidationError):
        SearchIntent.model_validate({"schema_version": 1, "mystery": True})


def test_missing_fields_default_safely():
    intent = parse_search_intent({"schema_version": 1, "target_roles": ["Buchhalter"]})
    assert intent.mandatory_skills == []
    assert intent.strictness is None


def test_unicode_roles_and_skills():
    intent = SearchIntent(
        target_roles=["Lohn- und Gehaltsbuchhalter", "Bürohilfe Größe"],
        mandatory_skills=["DATEV", "Überstunden"],
    )
    assert "Größe" in intent.target_roles[1]
    assert "Überstunden" in intent.mandatory_skills


def test_whitespace_and_dupes_normalized():
    intent = SearchIntent(
        target_roles=["  SAP ", "SAP", "", "Buchhalter"],
        mandatory_skills=[" sap ", "SAP"],
    )
    assert intent.target_roles == ["SAP", "Buchhalter"]
    assert intent.mandatory_skills == ["sap"]


def test_conflicting_include_exclude_flagged_not_dropped():
    intent = SearchIntent(
        target_roles=["Buchhalter", "Controller"],
        excluded_roles=["Buchhalter"],
        mandatory_skills=["SAP"],
        excluded_skills=["SAP"],
    )
    assert "Buchhalter" in intent.target_roles
    assert "Buchhalter" in intent.excluded_roles
    assert any(x.startswith("conflict:roles_target:") for x in intent.needs_user_review)
    assert any(x.startswith("conflict:skills_mandatory:") for x in intent.needs_user_review)


def test_strictness_enum_roundtrip_json():
    intent = SearchIntent(strictness=Strictness.STRICT, target_roles=["A"])
    raw = intent.model_dump(mode="json")
    assert raw["strictness"] == "strict"
    again = SearchIntent.model_validate(raw)
    assert again.strictness is Strictness.STRICT


def test_json_schema_exportable():
    schema = SearchIntent.model_json_schema()
    assert schema["title"] == "SearchIntent" or "properties" in schema
    assert "target_roles" in schema["properties"]
    assert "strictness" in schema["properties"]


# ---------------------------------------------------------------------------
# YAML / config roundtrip
# ---------------------------------------------------------------------------


def test_yaml_roundtrip_search_intent(tmp_path: Path):
    cfg = empty_app_config(root=tmp_path)
    cfg.profile.search_intent = SearchIntent(
        target_roles=["Gehaltsbuchhalter"],
        mandatory_skills=["DATEV"],
        strictness=Strictness.BALANCED,
        countries=["DE"],
        radius_km=25,
    )
    paths = _paths(tmp_path)
    save_config(cfg, **paths)
    loaded = load_config(**paths, root=tmp_path, strip_placeholders=False)
    intent = loaded.profile.search_intent
    assert intent.target_roles == ["Gehaltsbuchhalter"]
    assert intent.mandatory_skills == ["DATEV"]
    assert intent.strictness is Strictness.BALANCED
    assert intent.countries == ["DE"]
    assert intent.radius_km == 25.0


def test_profile_qualifications_unchanged_on_intent_save(tmp_path: Path):
    cfg = empty_app_config(root=tmp_path)
    cfg.profile.qualifications.skills = [SourcedText(value="Excel", source="cv")]
    cfg.profile.qualifications.work_experience = [
        ExperienceEntry(title="Verkäufer", company="Alt GmbH", source="cv")
    ]
    cfg.profile.search_intent = golden_tester_a_payroll_strict()
    paths = _paths(tmp_path)
    save_config(cfg, **paths)
    loaded = load_config(**paths, root=tmp_path, strip_placeholders=False)
    assert loaded.profile.qualifications.skill_values() == ["Excel"]
    assert loaded.profile.qualifications.work_experience[0].title == "Verkäufer"
    assert loaded.profile.search_intent.target_roles[0] == "Lohnbuchhalter"


def test_empty_intent_roundtrip(tmp_path: Path):
    cfg = empty_app_config(root=tmp_path)
    cfg.profile.search_intent = empty_search_intent()
    paths = _paths(tmp_path)
    save_config(cfg, **paths)
    text = paths["profile_path"].read_text(encoding="utf-8")
    assert "search_intent:" in text
    loaded = load_config(**paths, root=tmp_path, strip_placeholders=False)
    assert loaded.profile.search_intent.is_empty() or loaded.profile.search_intent.target_roles == []


# ---------------------------------------------------------------------------
# Migration from legacy jobs/filters
# ---------------------------------------------------------------------------


def test_migrate_clear_title_mappings():
    jobs = JobsConfig(
        desired_titles=["Sachbearbeiter"],
        unwanted_titles=["Praktikant"],
        desired_industries=["Verwaltung"],
        excluded_industries=["Gastronomie"],
        alternative_titles=[],
    )
    filters = FiltersConfig(exclusion_keywords=["Provision"])
    location = LocationConfig(country="DE", max_distance_km=30)
    employment = EmploymentConfig(
        full_time=True, part_time=False, remote=True, hybrid=False, onsite=False, minimum_salary=40000
    )
    result = migrate_legacy_search_preferences(
        jobs=jobs, filters=filters, location=location, employment=employment
    )
    assert result.intent.target_roles == ["Sachbearbeiter"]
    assert result.intent.excluded_roles == ["Praktikant"]
    assert result.intent.preferred_industries == ["Verwaltung"]
    assert result.intent.excluded_industries == ["Gastronomie"]
    assert result.intent.excluded_keywords == ["Provision"]
    assert result.intent.salary_min == 40000.0
    assert result.intent.countries == ["DE"]
    assert result.intent.radius_km == 30.0
    assert result.intent.working_time == ["full_time"]
    assert result.intent.remote_mode == "remote"
    assert result.intent.strictness is None
    assert "strictness_unset_confirm_with_user" in result.needs_user_review
    assert result.preserved_legacy is True


def test_migrate_does_not_guess_desired_keywords():
    filters = FiltersConfig(desired_keywords=["SAP", "Excel"])
    result = migrate_legacy_search_preferences(
        jobs=JobsConfig(),
        filters=filters,
        location=LocationConfig(),
        employment=EmploymentConfig(),
    )
    assert result.intent.required_keywords == []
    assert result.intent.mandatory_skills == []
    assert result.intent.preferred_skills == []
    assert "legacy_desired_keywords_unmapped" in result.needs_user_review


def test_migrate_ambiguous_remote_flags():
    employment = EmploymentConfig(remote=True, hybrid=True, onsite=True)
    result = migrate_legacy_search_preferences(
        jobs=JobsConfig(),
        filters=FiltersConfig(),
        location=LocationConfig(),
        employment=employment,
    )
    assert result.intent.remote_mode is None
    assert "legacy_remote_flags_ambiguous" in result.needs_user_review


def test_migrate_never_copies_qualifications_into_intent():
    """Profile evidence must not become search targets during migration."""
    jobs = JobsConfig(desired_titles=["Lohnbuchhalter"])
    # Qualifications are not passed into migrate — ensure helper contract.
    result = migrate_legacy_search_preferences(
        jobs=jobs,
        filters=FiltersConfig(),
        location=LocationConfig(),
        employment=EmploymentConfig(),
    )
    assert result.intent.target_roles == ["Lohnbuchhalter"]
    assert result.intent.mandatory_skills == []
    assert result.intent.preferred_skills == []


def test_load_legacy_yaml_without_search_intent_migrates(tmp_path: Path):
    paths = _paths(tmp_path)
    paths["profile_path"].write_text(
        """
location:
  home_address: ""
  max_distance_km: 20
  country: "DE"
jobs:
  desired_titles: ["Bürokaufmann"]
  alternative_titles: []
  unwanted_titles: []
  desired_industries: []
  excluded_industries: []
employment:
  full_time: true
  part_time: false
  remote: true
  hybrid: true
  onsite: true
  minimum_salary: null
qualifications:
  skills: []
  software: []
  languages: []
  education: []
  work_experience: []
  certificates: []
  driving_license: []
filters:
  desired_keywords: ["Teamfähig"]
  exclusion_keywords: []
  preferred_companies: []
  excluded_companies: []
""".strip()
        + "\n",
        encoding="utf-8",
    )
    paths["application_path"].write_text("country: DE\n", encoding="utf-8")
    paths["settings_path"].write_text("dry_run: true\n", encoding="utf-8")
    loaded = load_config(**paths, root=tmp_path, strip_placeholders=False)
    assert loaded.profile.search_intent is not None
    assert loaded.profile.search_intent.target_roles == ["Bürokaufmann"]
    assert "legacy_desired_keywords_unmapped" in loaded.profile.search_intent.needs_user_review
    # Legacy jobs preserved / dual-written
    assert loaded.profile.jobs.desired_titles == ["Bürokaufmann"]
    assert "Teamfähig" in loaded.profile.filters.desired_keywords


def test_existing_intent_not_overwritten_by_legacy(tmp_path: Path):
    paths = _paths(tmp_path)
    cfg = empty_app_config(root=tmp_path)
    cfg.profile.jobs.desired_titles = ["Alt"]
    cfg.profile.search_intent = SearchIntent(
        target_roles=["Neu"],
        strictness=Strictness.STRICT,
    )
    save_config(cfg, **paths)
    # Corrupt dual-write jobs to differ
    text = paths["profile_path"].read_text(encoding="utf-8")
    # reload should keep Neu from search_intent
    loaded = load_config(**paths, root=tmp_path, strip_placeholders=False)
    assert loaded.profile.search_intent.target_roles == ["Neu"]
    assert loaded.profile.search_intent.strictness is Strictness.STRICT


def test_ensure_search_intent_idempotent():
    profile = SearchPreferences(
        jobs=JobsConfig(desired_titles=["A"]),
        search_intent=None,
    )
    ensure_search_intent(profile)
    first = profile.search_intent.model_dump()
    ensure_search_intent(profile)
    assert profile.search_intent.model_dump()["target_roles"] == first["target_roles"]


def test_sync_legacy_clears_alternative_titles():
    jobs = JobsConfig(desired_titles=["X"], alternative_titles=["Y"])
    sync_legacy_jobs_from_intent(
        SearchIntent(target_roles=["Z"], excluded_roles=["N"]), jobs
    )
    assert jobs.desired_titles == ["Z"]
    assert jobs.alternative_titles == []
    assert jobs.unwanted_titles == ["N"]


def test_apply_clear_jobs_edit_to_intent():
    intent = SearchIntent(target_roles=["Old"], strictness=Strictness.EXPLORE)
    jobs = JobsConfig(desired_titles=["New"], unwanted_titles=["No"])
    out = apply_clear_jobs_edit_to_intent(intent, jobs)
    assert out.target_roles == ["New"]
    assert out.excluded_roles == ["No"]
    assert out.strictness is Strictness.EXPLORE


# ---------------------------------------------------------------------------
# Tester A / B golden cases
# ---------------------------------------------------------------------------


def test_tester_a_strict_target_roles_only_in_intent():
    intent = golden_tester_a_payroll_strict()
    assert intent.strictness is Strictness.STRICT
    assert intent.target_roles == [
        "Lohnbuchhalter",
        "Gehaltsbuchhalter",
        "Lohn- und Gehaltsbuchhalter",
        "Payroll Specialist",
    ]
    # Profile-like experience must not appear on intent
    assert intent.preferred_skills == []
    assert intent.mandatory_skills == []


def test_tester_a_profile_evidence_stays_on_qualifications(tmp_path: Path):
    cfg = empty_app_config(root=tmp_path)
    cfg.profile.search_intent = golden_tester_a_payroll_strict()
    cfg.profile.qualifications.work_experience = [
        ExperienceEntry(title="Verkäufer", company="Markt AG", source="cv"),
        ExperienceEntry(title="Callcenter Agent", company="Hotline", source="cv"),
    ]
    paths = _paths(tmp_path)
    save_config(cfg, **paths)
    loaded = load_config(**paths, root=tmp_path, strip_placeholders=False)
    titles = [e.title for e in loaded.profile.qualifications.work_experience]
    assert "Verkäufer" in titles
    assert "Callcenter Agent" in titles
    for role in loaded.profile.search_intent.target_roles:
        assert role in {
            "Lohnbuchhalter",
            "Gehaltsbuchhalter",
            "Lohn- und Gehaltsbuchhalter",
            "Payroll Specialist",
        }
    # STRICT contract: profile titles must not leak into target_roles
    assert "Verkäufer" not in loaded.profile.search_intent.target_roles


def test_tester_b_sap_mandatory_skill():
    intent = golden_tester_b_sap_mandatory()
    assert intent.mandatory_skills == ["SAP"]
    assert intent.strictness is Strictness.STRICT
    # PR23 will FILTERED_OUT jobs without SAP — domain only asserts persistence.
    dumped = intent.model_dump(mode="json")
    assert dumped["mandatory_skills"] == ["SAP"]


def test_tester_b_roundtrip(tmp_path: Path):
    cfg = empty_app_config(root=tmp_path)
    cfg.profile.search_intent = golden_tester_b_sap_mandatory()
    paths = _paths(tmp_path)
    save_config(cfg, **paths)
    loaded = load_config(**paths, root=tmp_path, strip_placeholders=False)
    assert loaded.profile.search_intent.mandatory_skills == ["SAP"]


def test_commercial_legacy_alternative_not_secret_driver():
    """alternative_titles must not remain a silent second search list."""
    jobs = JobsConfig(
        desired_titles=["Payroll"],
        alternative_titles=["Verkäufer"],  # residual legacy
    )
    result = migrate_legacy_search_preferences(
        jobs=jobs,
        filters=FiltersConfig(),
        location=LocationConfig(),
        employment=EmploymentConfig(),
    )
    # Without soft-fold, residual alts are flagged — not silently appended.
    assert "Verkäufer" not in result.intent.target_roles
    assert "legacy_alternative_titles_need_review" in result.needs_user_review
