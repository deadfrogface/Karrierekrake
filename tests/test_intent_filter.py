"""Unit tests for deterministic SearchIntent filtering (PR23)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.config import (
    AppConfig,
    EmploymentConfig,
    FiltersConfig,
    JobsConfig,
    LocationConfig,
    ProfileConfig,
    SettingsConfig,
)
from core.intent_aliases import (
    is_sap_false_positive_text,
    ranking_version_token,
    text_has_solid_skill,
    title_matches_role_label,
)
from core.intent_filter import (
    apply_search_intent,
    explanation_for_job,
    filter_jobs,
)
from core.matcher import score_job
from core.models import Job, RemoteType
from core.search_intent import (
    SearchIntent,
    Strictness,
    golden_tester_a_payroll_strict,
    golden_tester_b_sap_mandatory,
)


def _job(**kwargs) -> Job:
    defaults = dict(
        id="j1",
        source="test",
        title="Stelle",
        company="Firma",
        description="",
        city="Berlin",
        remote_type=RemoteType.ONSITE.value,
        employment_type="Vollzeit",
        distance_km=5.0,
        url="https://example.test/j",
    )
    defaults.update(kwargs)
    return Job(**defaults)


def _cfg_with_intent(intent: SearchIntent) -> AppConfig:
    return AppConfig(
        profile=ProfileConfig(
            location=LocationConfig(
                home_address="",
                max_distance_km=50.0,
                allow_remote_germany=True,
                allow_hybrid=True,
                country="DE",
            ),
            employment=EmploymentConfig(full_time=True, part_time=True, remote=True, hybrid=True, onsite=True),
            jobs=JobsConfig(desired_titles=list(intent.target_roles)),
            filters=FiltersConfig(),
            search_intent=intent,
        ),
        settings=SettingsConfig(published_within_days=30, exclude_on_missing_mandatory=False),
    )


# --- Golden Tester A / B ----------------------------------------------------------


def test_tester_a_only_payroll_family():
    intent = golden_tester_a_payroll_strict()
    payroll = _job(title="Lohn- und Gehaltsbuchhalter", description="Entgeltabrechnung")
    other = _job(title="Verkäufer", description="Verkauf im Einzelhandel")
    book = _job(title="Buchhalter", description="Finanzbuchhaltung ohne Lohn")
    r_ok = apply_search_intent(payroll, intent)
    r_no = apply_search_intent(other, intent)
    r_book = apply_search_intent(book, intent)
    assert r_ok.included and not r_ok.excluded
    assert any("target role" in x for x in r_ok.why_shown)
    assert r_no.excluded
    assert r_book.excluded  # general Buchhalter is NOT payroll family


def test_tester_b_sap_mandatory_filters_out():
    intent = golden_tester_b_sap_mandatory()
    ok = _job(title="Berater", description="SAP FI und S/4HANA Erfahrung")
    bad = _job(title="IT Admin", description="Irgendwie IT und ERP")
    r_ok = apply_search_intent(ok, intent)
    r_bad = apply_search_intent(bad, intent)
    assert r_ok.included
    assert any("mandatory skill" in x for x in r_ok.why_shown)
    assert r_bad.excluded
    assert any("SAP" in x for x in r_bad.why_excluded)


def test_score_job_wires_intent_hard_gate():
    intent = golden_tester_b_sap_mandatory()
    cfg = _cfg_with_intent(intent)
    bad = _job(title="Dev", description="Python und Cloud")
    result = score_job(bad, cfg)
    assert result.excluded
    assert result.score == 0
    assert result.ranking_version == ranking_version_token()


# --- SAP variants / false positives -----------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "SAP",
        "Kenntnisse in SAP",
        "SAP HANA",
        "S/4HANA",
        "S4HANA",
        "SAP FI",
        "SAP CO",
        "SAP SuccessFactors",
        "SuccessFactors Administration",
        "SAP Fiori",
        "SAP ERP",
    ],
)
def test_sap_solid_positives(text: str):
    assert text_has_solid_skill(text, "SAP")


@pytest.mark.parametrize(
    "text",
    [
        "IT",
        "Irgendwie IT",
        "ERP",
        "Softwareentwicklung",
        "Microsoft Dynamics",
        "Dynamics 365",
        "Oracle",
        "Navision",
        "DATEV",
        "Sapphire Conference",
        "Informationstechnologie",
    ],
)
def test_sap_false_positives_rejected(text: str):
    assert not text_has_solid_skill(text, "SAP")
    assert is_sap_false_positive_text(text) or "sap" not in text.casefold()


# --- Payroll synonyms -------------------------------------------------------------


@pytest.mark.parametrize(
    "title",
    [
        "Lohnbuchhalter",
        "Gehaltsbuchhalter",
        "Lohn- und Gehaltsbuchhalter",
        "Payroll Specialist",
        "Entgeltabrechnung",
        "Fachkraft Entgeltabrechnung",
        "Sachbearbeiter Lohn und Gehalt",
    ],
)
def test_payroll_title_aliases(title: str):
    assert title_matches_role_label(title, "Lohnbuchhalter")


# --- Strictness -------------------------------------------------------------------


def test_strict_rejects_description_only_role():
    intent = SearchIntent(
        target_roles=["Lohnbuchhalter"],
        strictness=Strictness.STRICT,
    )
    job = _job(
        title="Sachbearbeiter",
        description="Unterstützung der Lohnbuchhaltung und Entgeltabrechnung",
    )
    assert apply_search_intent(job, intent).excluded


def test_explore_allows_description_role_alias():
    intent = SearchIntent(
        target_roles=["Lohnbuchhalter"],
        strictness=Strictness.EXPLORE,
    )
    job = _job(
        title="Sachbearbeiter",
        description="Schwerpunkt Entgeltabrechnung und Payroll",
    )
    assert apply_search_intent(job, intent).included


def test_unset_strictness_with_targets_behaves_strict():
    intent = SearchIntent(target_roles=["Lohnbuchhalter"], strictness=None)
    job = _job(title="Controller", description="Lohnbuchhalter Team Support")
    assert apply_search_intent(job, intent).excluded


# --- Exclusions / mandatory / keywords --------------------------------------------


def test_excluded_keyword_hard():
    intent = SearchIntent(excluded_keywords=["Glücksspiel"])
    job = _job(title="Dealer", description="Arbeit im Glücksspiel")
    r = apply_search_intent(job, intent)
    assert r.excluded
    assert r.rank_score == 0


def test_mandatory_skill_generic():
    intent = SearchIntent(mandatory_skills=["DATEV"])
    ok = _job(title="Buchhalter", description="DATEV Kenntnisse zwingend")
    bad = _job(title="Buchhalter", description="Excel nur")
    assert apply_search_intent(ok, intent).included
    assert apply_search_intent(bad, intent).excluded


def test_required_keyword_hard():
    intent = SearchIntent(required_keywords=["Tarifvertrag"])
    ok = _job(title="HR", description="Arbeit nach Tarifvertrag")
    bad = _job(title="HR", description="ohne besondere Hinweise")
    assert apply_search_intent(ok, intent).included
    assert apply_search_intent(bad, intent).excluded


def test_excluded_role_hard():
    intent = SearchIntent(
        target_roles=["Lohnbuchhalter"],
        excluded_roles=["Teamleiter"],
        strictness=Strictness.STRICT,
    )
    job = _job(title="Teamleiter Lohnbuchhaltung", description="Payroll")
    # Title matches payroll AND excluded role — exclude wins
    assert apply_search_intent(job, intent).excluded


# --- Empty / conflict / no-match --------------------------------------------------


def test_empty_intent_includes():
    intent = SearchIntent()
    job = _job(title="Anything", description="x")
    r = apply_search_intent(job, intent)
    assert r.included and not r.excluded


def test_conflicting_rules_exclude_wins():
    intent = SearchIntent(
        mandatory_skills=["SAP"],
        excluded_skills=["SAP"],
    )
    assert any(str(x).startswith("conflict:") for x in intent.needs_user_review)
    job = _job(title="SAP Berater", description="SAP FI")
    r = apply_search_intent(job, intent)
    assert r.excluded  # excluded_skills checked before mandatory include


# --- Hard fail cannot re-enter ranking --------------------------------------------


def test_hard_fail_never_soft_ranked():
    intent = SearchIntent(
        mandatory_skills=["SAP"],
        preferred_skills=["Python"],
        preferred_industries=["IT"],
        strictness=Strictness.STRICT,
    )
    job = _job(title="Dev", description="Python und IT Branche ohne SAP")
    r = apply_search_intent(job, intent)
    assert r.excluded
    assert r.rank_score == 0
    assert not any(c.kind == "preferred_skill" and c.passed for c in r.criteria)


def test_filter_jobs_sorts_only_included():
    intent = golden_tester_a_payroll_strict()
    jobs = [
        _job(id="1", title="Verkäufer", description="x"),
        _job(id="2", title="Lohnbuchhalter", description="Entgelt"),
        _job(id="3", title="Payroll Specialist", description="Payroll"),
    ]
    included, excluded = filter_jobs(jobs, intent)
    assert len(excluded) == 1
    assert all(r.included for _, r in included)
    assert all(r.excluded for _, r in excluded)
    assert included[0][1].rank_score >= included[-1][1].rank_score


def test_explanation_model():
    intent = golden_tester_b_sap_mandatory()
    job = _job(title="X", description="keine relevanten Kenntnisse")
    r = explanation_for_job(job, intent)
    assert r.why_excluded
    assert r.why_excluded[0].startswith("✗")
    d = r.to_dict()
    assert d["excluded"] is True
    assert d["ranking_version"] == ranking_version_token()


def test_preferred_skills_boost_rank_only_when_included():
    intent = SearchIntent(
        mandatory_skills=["SAP"],
        preferred_skills=["Python"],
    )
    base = _job(title="Berater", description="SAP FI")
    boosted = _job(title="Berater", description="SAP FI und Python")
    r0 = apply_search_intent(base, intent)
    r1 = apply_search_intent(boosted, intent)
    assert r0.included and r1.included
    assert r1.rank_score > r0.rank_score


def test_working_time_condition():
    intent = SearchIntent(working_time=["part_time"])
    ok = _job(title="Hilfe", description="x", employment_type="Teilzeit")
    bad = _job(title="Hilfe", description="x", employment_type="Vollzeit")
    assert apply_search_intent(ok, intent).included
    assert apply_search_intent(bad, intent).excluded


def test_remote_mode_condition():
    intent = SearchIntent(remote_mode="remote")
    ok = _job(title="Dev", description="x", remote_type=RemoteType.REMOTE.value)
    bad = _job(title="Dev", description="x", remote_type=RemoteType.ONSITE.value)
    assert apply_search_intent(ok, intent).included
    assert apply_search_intent(bad, intent).excluded
