"""PR29 association corpus: Mail → Firma → Stelle → ApplicationCase.

Synthetic competing-application fixtures only (no real recruiting mail / PII).
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from integrations.email_associate import (
    ASSOCIATION_POLICY_VERSION,
    associate_email,
    decide_association_write,
)

CORPUS = Path(__file__).parent / "fixtures" / "association" / "competing_application_corpus.json"


def _load() -> dict:
    return json.loads(CORPUS.read_text(encoding="utf-8"))


def _scenarios() -> list[dict]:
    data = _load()
    rows = data["scenarios"]
    assert len(rows) >= 250
    return rows


@pytest.fixture(scope="module")
def corpus() -> dict:
    return _load()


@pytest.fixture(scope="module")
def scenarios(corpus: dict) -> list[dict]:
    return list(corpus["scenarios"])


def test_corpus_size_and_privacy_meta(corpus: dict):
    assert corpus["meta"]["synthetic"] is True
    assert corpus["meta"]["pii"] is False
    assert corpus["meta"]["count"] >= 250
    assert len(corpus["scenarios"]) >= 250
    # Hard-case families must be present
    families = set(corpus["meta"]["families"])
    for required in {
        "same_company_two_roles",
        "same_title_two_cities",
        "holding_subsidiary",
        "recruiting_agency",
        "generic_ats_sender",
        "ats_application_id",
        "exact_thread",
        "forwarded",
        "contradictory_signals",
        "multiple_threads",
    }:
        assert required in families


def test_corpus_uses_only_example_domains(scenarios: list[dict]):
    import re

    email_re = re.compile(r"@([A-Za-z0-9.-]+\.[A-Za-z]{2,})")
    allowed_roots = ("example.com", "example.org", "example.net")
    for row in scenarios:
        blob = json.dumps(row, ensure_ascii=False)
        for dom in email_re.findall(blob):
            d = dom.lower()
            assert any(d == r or d.endswith("." + r) for r in allowed_roots), d


@pytest.mark.parametrize("row", _scenarios(), ids=lambda r: r["id"])
def test_each_association_scenario_deterministic(row: dict):
    """Same inputs → identical AssociationResult (determinism)."""
    kwargs = dict(
        sender=row["sender"],
        subject=row["subject"],
        body=row.get("body") or "",
        cases=row["cases"],
        thread_id=row.get("thread_id") or "",
        message_id=row.get("message_id") or "",
        ats_application_id=row.get("ats_application_id") or "",
        location_hint=row.get("location_hint") or "",
        is_forwarded=bool(row.get("is_forwarded")),
    )
    a = associate_email(**kwargs)
    b = associate_email(**kwargs)
    assert a.case_id == b.case_id
    assert a.ambiguous == b.ambiguous
    assert a.confidence == b.confidence
    assert a.reason == b.reason
    assert a.candidates == b.candidates
    assert a.policy_version == ASSOCIATION_POLICY_VERSION
    assert a.match_status == b.match_status


@pytest.mark.parametrize("row", _scenarios(), ids=lambda r: r["id"])
def test_each_association_scenario_expectation(row: dict):
    """E2E corpus expectations: linked cases correct; ambiguous fail-safe."""
    result = associate_email(
        sender=row["sender"],
        subject=row["subject"],
        body=row.get("body") or "",
        cases=row["cases"],
        thread_id=row.get("thread_id") or "",
        message_id=row.get("message_id") or "",
        ats_application_id=row.get("ats_application_id") or "",
        location_hint=row.get("location_hint") or "",
        is_forwarded=bool(row.get("is_forwarded")),
    )
    expect = row["expect"]
    case_ids = {str(c["id"]) for c in row["cases"]}

    # Never invent a case id outside the candidate set
    if result.case_id is not None:
        assert result.case_id in case_ids

    if expect == "linked":
        assert result.ambiguous is False
        assert result.case_id == row["expected_case_id"]
        assert result.match_status == "linked"
        assert result.confidence >= 0.90
        assert result.explanation
        assert result.evidence
    elif expect in {"ambiguous", "review_required"}:
        assert result.case_id is None
        assert result.ambiguous is True
        assert result.match_status in {"ambiguous", "review_required"}
        # Fail-safe: never auto-link on hard competing cases
        assert row.get("expected_case_id") is None
    else:  # unlinked
        assert result.case_id is None
        assert result.ambiguous is False


def test_e2e_accuracy_gates(scenarios: list[dict]):
    """Acceptance: ≥99% unique correct; 100% ambiguous fail-safe; 0 cross-case."""
    linked_rows = [r for r in scenarios if r["expect"] == "linked"]
    amb_rows = [r for r in scenarios if r["expect"] in {"ambiguous", "review_required"}]
    assert linked_rows and amb_rows

    linked_ok = 0
    cross_mutations = 0
    for row in linked_rows:
        result = associate_email(
            sender=row["sender"],
            subject=row["subject"],
            body=row.get("body") or "",
            cases=row["cases"],
            thread_id=row.get("thread_id") or "",
            message_id=row.get("message_id") or "",
            ats_application_id=row.get("ats_application_id") or "",
            location_hint=row.get("location_hint") or "",
            is_forwarded=bool(row.get("is_forwarded")),
        )
        if result.case_id == row["expected_case_id"] and not result.ambiguous:
            linked_ok += 1
        # Cross-case: linked to a different competing case
        if (
            result.case_id
            and row["expected_case_id"]
            and result.case_id != row["expected_case_id"]
        ):
            cross_mutations += 1

    amb_ok = 0
    for row in amb_rows:
        result = associate_email(
            sender=row["sender"],
            subject=row["subject"],
            body=row.get("body") or "",
            cases=row["cases"],
            thread_id=row.get("thread_id") or "",
            message_id=row.get("message_id") or "",
            ats_application_id=row.get("ats_application_id") or "",
            location_hint=row.get("location_hint") or "",
            is_forwarded=bool(row.get("is_forwarded")),
        )
        if result.case_id is None and result.ambiguous:
            amb_ok += 1
        if result.case_id is not None:
            cross_mutations += 1  # silent best-guess on ambiguous = mutation risk

    linked_rate = linked_ok / len(linked_rows)
    amb_rate = amb_ok / len(amb_rows)
    assert linked_rate >= 0.99, f"linked accuracy {linked_rate:.4f} ({linked_ok}/{len(linked_rows)})"
    assert amb_rate == 1.0, f"ambiguous fail-safe {amb_rate:.4f} ({amb_ok}/{len(amb_rows)})"
    assert cross_mutations == 0


def test_no_silent_max_score_without_threshold():
    """Commercial gate: never link on weak near-tie max(score)."""
    cases = [
        {
            "id": "a",
            "company": "Nordlicht GmbH",
            "position": "Buchhalter",
            "status": "applied",
            "contact_email": "hr@nordlicht.example.com",
        },
        {
            "id": "b",
            "company": "Nordlicht GmbH",
            "position": "Controller",
            "status": "applied",
            "contact_email": "hr@nordlicht.example.com",
        },
    ]
    result = associate_email(
        sender="People <noreply@nordlicht.example.com>",
        subject="Update",
        body="Allgemeine Nachricht",
        cases=cases,
    )
    assert result.case_id is None
    assert result.ambiguous is True
    assert result.match_status in {"ambiguous", "review_required"}


def test_confirmed_association_not_overwritten():
    """Migration/rollback: confirmed links stay; no silent overwrite."""
    proposed = associate_email(
        sender="hr@other.example.com",
        subject="Andere Firma",
        body="Referenz REF-OTHER-1",
        cases=[
            {
                "id": "keep-me",
                "company": "Keep GmbH",
                "position": "Assistenz",
                "status": "applied",
                "contact_email": "hr@keep.example.com",
                "reference": "REF-KEEP-1",
            },
            {
                "id": "other",
                "company": "Other AG",
                "position": "Assistenz",
                "status": "applied",
                "contact_email": "hr@other.example.com",
                "reference": "REF-OTHER-1",
            },
        ],
    )
    protected = decide_association_write(
        existing_status="linked",
        existing_case_id="keep-me",
        existing_confirmed=True,
        existing_policy_version="0.9.0",
        proposed=proposed,
    )
    assert protected.case_id == "keep-me"
    assert protected.match_status == "protected"
    assert protected.reason == "confirmed_association_protected"
    assert protected.policy_version == ASSOCIATION_POLICY_VERSION


def test_family_coverage_counts(scenarios: list[dict]):
    counts = Counter(r["family"] for r in scenarios)
    assert sum(counts.values()) >= 250
    assert counts["clear_unique"] >= 50
    assert counts["same_company_two_roles"] >= 30
