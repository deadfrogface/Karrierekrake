"""CI check: every shipped HR approval points at a FERTIG item in the PR144 ledger.

The runtime gate (guenther.setup_models.hr_unapproved) only checks the record
format and never reads docs/project/PR144_WORK_ITEMS.json. This test closes
the gap in CI: for every non-None entry in ``HR_APPROVAL`` the referenced
``work_item_id`` must exist in the ledger AND have ``"status": "FERTIG"``.
With the shipped (empty) registry it passes trivially.
"""
from __future__ import annotations

import json

import pytest

from guenther import setup_models as setup
from tests.hr_approval_ledger import LEDGER_PATH, hr_ledger_violations, load_ledger

M4, M8 = "qwen3.5-4b-gsq", "qwen3-8b-gsq"


def _record(mid, item):
    return {"model_sha256": setup.SETUP_MODEL_CATALOG[mid]["sha256"], "work_item_id": item,
            "verdict_file": "docs/project/PR144_WORK_ITEMS.json", "verdict_commit": "0" * 40,
            "approver": "Personaler", "decided_on": "2026-10-19"}


@pytest.fixture
def ledger_file(tmp_path):
    """Fixture work-items JSON in the real ledger shape (packages[].items[] with id/status)."""
    data = {"schema": "karrierekrake.pr144.work-items.v1", "packages": [
        {"id": "T02", "name": "Modellinstallation", "items": [
            {"id": "T02.09", "status": "OFFEN", "acceptance": "x"},
            {"id": "T02.10", "status": "FERTIG", "acceptance": "y"},
            {"id": "T02.11", "status": "IMPLEMENTIERT – PRÜFUNG OFFEN", "acceptance": "z"},
        ]}]}
    path = tmp_path / "PR144_WORK_ITEMS.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def test_shipped_hr_approvals_reference_fertig_ledger_items():
    """The CI gate itself, on the real registry and the real ledger."""
    assert hr_ledger_violations(setup.HR_APPROVAL, load_ledger(LEDGER_PATH)) == []


def test_ledger_status_field_is_status_with_value_fertig():
    ledger = load_ledger(LEDGER_PATH)
    assert "FERTIG" in set(ledger.values())
    assert len(ledger) > 100


def test_unknown_work_item_fails(ledger_file):
    violations = hr_ledger_violations({M4: _record(M4, "T99.99")}, load_ledger(ledger_file))
    assert violations == [f"{M4}: work_item_id T99.99 not in ledger"]


def test_existing_but_offen_work_item_fails(ledger_file):
    violations = hr_ledger_violations({M4: _record(M4, "T02.09")}, load_ledger(ledger_file))
    assert violations == [f"{M4}: work_item_id T02.09 status OFFEN, not FERTIG"]


def test_pruefung_offen_is_not_fertig(ledger_file):
    assert hr_ledger_violations({M4: _record(M4, "T02.11")}, load_ledger(ledger_file)) != []


def test_fertig_work_item_passes(ledger_file):
    approvals = {M4: _record(M4, "T02.10"), M8: None}
    assert hr_ledger_violations(approvals, load_ledger(ledger_file)) == []


def test_every_non_none_entry_is_checked(ledger_file):
    approvals = {M4: _record(M4, "T02.10"), M8: _record(M8, "T02.09")}
    assert hr_ledger_violations(approvals, load_ledger(ledger_file)) == [
        f"{M8}: work_item_id T02.09 status OFFEN, not FERTIG"]


@pytest.mark.parametrize("entry", [True, "T02.10", {"work_item_id": None}, {}])
def test_malformed_non_none_entry_fails(ledger_file, entry):
    assert hr_ledger_violations({M4: entry}, load_ledger(ledger_file)) != []


def test_monkeypatched_registry_is_what_the_ci_gate_checks(monkeypatch, ledger_file):
    monkeypatch.setattr(setup, "HR_APPROVAL", {M4: _record(M4, "T02.09")})
    assert hr_ledger_violations(setup.HR_APPROVAL, load_ledger(ledger_file)) != []
    monkeypatch.setattr(setup, "HR_APPROVAL", {M4: _record(M4, "T02.10")})
    assert hr_ledger_violations(setup.HR_APPROVAL, load_ledger(ledger_file)) == []
