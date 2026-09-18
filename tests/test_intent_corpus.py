"""Large synthetic corpus: SearchIntent fixtures + mandatory/exclusion matrix (PR23).

All job texts are fictional — no external scraped JD corpus.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.intent_filter import apply_search_intent, filter_jobs
from core.models import Job, RemoteType
from core.search_intent import (
    SearchIntent,
    Strictness,
    golden_tester_a_payroll_strict,
    golden_tester_b_sap_mandatory,
)

CORPUS = Path(__file__).parent / "fixtures" / "intent_jobs_corpus.json"


def _load_corpus() -> list[dict]:
    data = json.loads(CORPUS.read_text(encoding="utf-8"))
    jobs = data["jobs"]
    assert len(jobs) >= 300
    return jobs


def _as_job(raw: dict) -> Job:
    return Job(
        id=str(raw.get("id") or ""),
        source="corpus",
        title=str(raw.get("title") or ""),
        company=str(raw.get("company") or ""),
        description=str(raw.get("description") or ""),
        city=str(raw.get("city") or ""),
        remote_type=str(raw.get("remote_type") or RemoteType.UNKNOWN.value),
        employment_type=str(raw.get("employment_type") or ""),
        distance_km=raw.get("distance_km"),
        salary_min=raw.get("salary_min"),
        salary_max=raw.get("salary_max"),
        url=f"https://example.test/{raw.get('id')}",
    )


@pytest.fixture(scope="module")
def corpus_jobs() -> list[dict]:
    return _load_corpus()


def test_corpus_size(corpus_jobs: list[dict]):
    assert len(corpus_jobs) >= 300


def test_tester_a_strict_e2e_corpus(corpus_jobs: list[dict]):
    intent = golden_tester_a_payroll_strict()
    jobs = [_as_job(r) for r in corpus_jobs]
    included, excluded = filter_jobs(jobs, intent)
    for job, result in included:
        assert result.included
        assert not result.excluded
        # Title must be payroll-family under STRICT
        assert apply_search_intent(job, intent).included
    # All decoys / pads must not leak in
    included_ids = {j.id for j, _ in included}
    for raw in corpus_jobs:
        tags = set(raw.get("tags") or [])
        if "payroll_negative" in tags or "pad" in tags:
            assert raw["id"] not in included_ids
        if "payroll_positive" in tags:
            # remote payroll positive may still match on title
            if "Payroll" in raw["title"] or "Lohn" in raw["title"] or "Gehalt" in raw["title"] or "Entgelt" in raw["title"]:
                assert raw["id"] in included_ids


def test_tester_b_sap_only_corpus(corpus_jobs: list[dict]):
    intent = golden_tester_b_sap_mandatory()
    jobs = [_as_job(r) for r in corpus_jobs]
    included, excluded = filter_jobs(jobs, intent)
    included_ids = {j.id for j, _ in included}
    for raw in corpus_jobs:
        tags = set(raw.get("tags") or [])
        if "sap_false_positive" in tags:
            assert raw["id"] not in included_ids
        if "sap_positive" in tags:
            assert raw["id"] in included_ids
    # Every included job must have solid SAP evidence
    for job, result in included:
        assert result.included
        assert any("SAP" in w or "mandatory skill" in w for w in result.why_shown)


@pytest.mark.parametrize("raw", _load_corpus(), ids=lambda r: r["id"])
def test_each_corpus_job_deterministic_roundtrip(raw: dict):
    """~300 fixtures: same inputs → same include/exclude (determinism)."""
    job = _as_job(raw)
    intent = SearchIntent(
        target_roles=["Lohnbuchhalter"],
        mandatory_skills=[],
        strictness=Strictness.STRICT,
    )
    a = apply_search_intent(job, intent)
    b = apply_search_intent(job, intent)
    assert a.included == b.included
    assert a.excluded == b.excluded
    assert a.rank_score == b.rank_score
    assert a.exclude_reason == b.exclude_reason


def _matrix_cases() -> list[tuple[str, SearchIntent, dict, bool]]:
    """Build ≥100 mandatory/exclusion expectations from corpus matrix rows."""
    cases: list[tuple[str, SearchIntent, dict, bool]] = []
    for raw in _load_corpus():
        if "matrix" not in (raw.get("tags") or []):
            continue
        meta = raw.get("meta") or {}
        skill = meta.get("skill") or "DATEV"
        # Mandatory skill present/absent
        intent_m = SearchIntent(mandatory_skills=[skill])
        cases.append(
            (f"mand-{raw['id']}", intent_m, raw, bool(meta.get("has_skill")))
        )
        # Exclusion keyword Glücksspiel
        intent_x = SearchIntent(excluded_keywords=["Glücksspiel"])
        expect_include = not bool(meta.get("has_excl_keyword"))
        cases.append(
            (f"excl-{raw['id']}", intent_x, raw, expect_include)
        )
    assert len(cases) >= 100
    return cases


@pytest.mark.parametrize(
    "case_id,intent,raw,expect_included",
    _matrix_cases(),
    ids=[c[0] for c in _matrix_cases()],
)
def test_mandatory_exclusion_matrix(
    case_id: str, intent: SearchIntent, raw: dict, expect_included: bool
):
    result = apply_search_intent(_as_job(raw), intent)
    assert result.included is expect_included
    if not expect_included:
        assert result.rank_score == 0
        assert result.why_excluded


def test_no_hard_excluded_in_ranked_list(corpus_jobs: list[dict]):
    intent = SearchIntent(
        mandatory_skills=["SAP"],
        preferred_skills=["Python"],
        strictness=Strictness.STRICT,
    )
    included, excluded = filter_jobs([_as_job(r) for r in corpus_jobs], intent)
    for _, r in included:
        assert r.included and not r.excluded
        assert r.rank_score >= 0
    for _, r in excluded:
        assert r.excluded
        assert r.rank_score == 0
        # soft preferred must not appear as passed on excluded
        assert not any(c.kind == "preferred_skill" and c.passed for c in r.criteria)


def test_empty_intent_keeps_all(corpus_jobs: list[dict]):
    intent = SearchIntent()
    included, excluded = filter_jobs([_as_job(r) for r in corpus_jobs[:50]], intent)
    assert len(excluded) == 0
    assert len(included) == 50
