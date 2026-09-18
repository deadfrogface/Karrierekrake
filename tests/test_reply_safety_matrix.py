"""PR32 reply safety matrix: action drafts, no-send, cross-case isolation.

Synthetic fixtures only (no real recruiting mail / PII). >=150 scenarios.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from integrations.reply_draft import (
    BINDING_ACTIONS,
    ReplyAction,
    SendGate,
    assert_cross_case_isolation,
    build_action_draft,
)

CORPUS = Path(__file__).parent / "fixtures" / "replies" / "reply_safety_corpus.json"


def _load() -> dict:
    return json.loads(CORPUS.read_text(encoding="utf-8"))


def _scenarios() -> list[dict]:
    rows = _load()["scenarios"]
    assert len(rows) >= 150
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
    assert corpus["meta"]["count"] >= 150
    assert len(corpus["scenarios"]) >= 150
    assert set(corpus["meta"]["actions"]) == {a.value for a in ReplyAction}


def test_family_coverage(scenarios: list[dict]):
    counts = Counter(r["family"] for r in scenarios)
    for family in (
        "happy_verified",
        "unverified_core",
        "unverified_dates",
        "cross_case_isolation",
        "no_send_gate",
        "binding_no_invention",
    ):
        assert counts[family] >= 1, family


def _build(row: dict):
    case = row["case"]
    slots = case.get("proposed_slots")
    docs = case.get("documents")
    when = ""
    # Only pass date kwargs when verified — otherwise VerifiedFacts decides.
    if case.get("interview_when_verified"):
        when = case.get("interview_when") or ""
    return build_action_draft(
        row["action"],
        case,
        applicant_name=row.get("applicant_name") or "",
        proposed_slots=slots if slots else None,
        documents=docs if docs else None,
        interview_when=when,
    )


@pytest.mark.parametrize("row", _scenarios(), ids=lambda r: r["id"])
def test_each_reply_scenario(row: dict):
    draft = _build(row)
    exp = row["expect"]

    assert draft.auto_send is False
    assert draft.draft_only is True
    assert draft.action == exp["action"]
    assert draft.case_id == str(row["case"].get("id") or "")

    if "requires_explicit_review" in exp:
        assert draft.requires_explicit_review is exp["requires_explicit_review"]
        if exp["requires_explicit_review"]:
            assert draft.action in BINDING_ACTIONS

    if exp.get("contains_company"):
        assert row["case"]["company"] in draft.body
    if exp.get("contains_position"):
        assert row["case"]["position"] in draft.body
    if exp.get("contains_when"):
        assert row["case"]["interview_when"] in draft.body
    if exp.get("contains_slots"):
        for slot in row["case"].get("proposed_slots") or []:
            assert slot in draft.body

    for token in exp.get("body_must_contain") or []:
        assert token in draft.body
    for token in exp.get("body_must_not_contain") or []:
        assert token not in draft.body, token

    for reason in exp.get("blocking_has") or []:
        assert reason in draft.blocking_reasons

    if "cross_case_violations" in exp:
        violations = assert_cross_case_isolation(draft, row["case"])
        assert violations == exp["cross_case_violations"]

    # Default commercial path: never auto-send
    gate = SendGate(allow_send=False, draft_only=True)
    out = gate.attempt_send(draft, transport=lambda d: (_ for _ in ()).throw(RuntimeError("no")))
    assert out.sent is False
    assert out.send_error

    if row["family"] == "no_send_gate":
        gcfg = row["gate"]
        draft2 = _build(row)
        gate2 = SendGate(allow_send=gcfg["allow_send"], draft_only=gcfg["draft_only"])
        if gcfg["approve"]:
            gate2.approve(draft2)
        if gcfg["binding"]:
            gate2.approve_binding_review(draft2)

        def _ok(_d):
            return None

        def _boom(_d):
            raise ConnectionError("smtp down")

        transport = _boom if gcfg.get("transport_fail") else _ok
        result = gate2.attempt_send(draft2, transport=transport)
        assert result.sent is exp["sent"]
        assert result.auto_send is False
        if exp.get("send_error_contains"):
            assert exp["send_error_contains"] in (result.send_error or "")
        if gcfg.get("transport_fail"):
            assert result.sent is False
            assert "send_failed" in result.send_error
            assert result.body  # draft preserved

    if exp.get("send_with_full_approval_allow_send") == "blocked_unverified_facts":
        draft3 = _build(row)
        gate3 = SendGate(allow_send=True, draft_only=False)
        gate3.approve(draft3)
        gate3.approve_binding_review(draft3)
        result = gate3.attempt_send(draft3, transport=lambda d: None)
        assert result.sent is False
        assert "blocked_unverified_facts" in result.send_error


def test_e2e_draft_belongs_to_exact_case():
    case_a = {
        "id": "case-A",
        "company": "Firma Alpha Demo",
        "position": "Rolle Alpha",
        "company_verified": True,
        "position_verified": True,
        "contact_email": "a@alpha.example",
        "contact_email_verified": True,
    }
    case_b = {
        "id": "case-B",
        "company": "Firma Beta Demo",
        "position": "Rolle Beta",
        "company_verified": True,
        "position_verified": True,
        "contact_email": "b@beta.example",
        "contact_email_verified": True,
    }
    d_a = build_action_draft(ReplyAction.FOLLOWUP, case_a, applicant_name="Max")
    d_b = build_action_draft(ReplyAction.THANK_YOU, case_b, applicant_name="Max")
    assert d_a.case_id == "case-A"
    assert d_b.case_id == "case-B"
    assert "Firma Alpha Demo" in d_a.body and "Firma Beta Demo" not in d_a.body
    assert "Firma Beta Demo" in d_b.body and "Firma Alpha Demo" not in d_b.body
    assert d_a.action == "FOLLOWUP" and d_b.action == "THANK_YOU"


def test_commercial_zero_default_autosend_and_failed_not_sent():
    case = {
        "id": "c-fail",
        "company": "Fail Demo",
        "position": "Role",
        "company_verified": True,
        "position_verified": True,
        "contact_email": "hr@fail.example",
        "contact_email_verified": True,
    }
    draft = build_action_draft(ReplyAction.FOLLOWUP, case, applicant_name="Max")
    assert draft.auto_send is False
    gate = SendGate(allow_send=True, draft_only=False)
    gate.approve(draft)

    def boom(_d):
        raise TimeoutError("down")

    out = gate.attempt_send(draft, transport=boom)
    assert out.sent is False
    assert "send_failed" in out.send_error


def test_binding_actions_need_explicit_review():
    case = {
        "id": "c-bind",
        "company": "Bind Demo",
        "position": "Role",
        "company_verified": True,
        "position_verified": True,
        "contact_email": "hr@bind.example",
        "contact_email_verified": True,
    }
    for action in (ReplyAction.WITHDRAW, ReplyAction.DECLINE_OFFER):
        draft = build_action_draft(action, case, applicant_name="Max")
        assert draft.requires_explicit_review is True
        gate = SendGate(allow_send=True, draft_only=False)
        gate.approve(draft)
        out = gate.attempt_send(draft, transport=lambda d: None)
        assert out.sent is False
        assert "binding_review_required" in out.send_error
        gate.approve_binding_review(draft)
        out = gate.attempt_send(draft, transport=lambda d: None)
        assert out.sent is True
