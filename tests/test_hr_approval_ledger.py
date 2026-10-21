"""CI check: every shipped HR approval points at a FERTIG item in the PR144 ledger.

The runtime gate (guenther.setup_models.hr_unapproved) only checks the record
format and never reads docs/project/PR144_WORK_ITEMS.json. This test closes
the gap in CI: for every non-None entry in ``HR_APPROVAL`` the referenced
``work_item_id`` must exist in the ledger AND have ``"status": "FERTIG"``.
Additionally ``verdict_commit`` must be a commit in the history of HEAD
(``git merge-base --is-ancestor <sha> HEAD``). In a shallow checkout the
check fails closed with a clear message instead of skipping.
With the shipped (empty) registry it passes trivially.
"""
from __future__ import annotations

import json
import subprocess

import pytest

from guenther import setup_models as setup
from tests import hr_approval_ledger as ledger_check
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


def test_shipped_hr_approvals_reference_verdict_commits_in_history():
    """The CI gate itself: every verdict_commit is an ancestor of HEAD of this repo."""
    assert ledger_check.hr_commit_violations(setup.HR_APPROVAL, ledger_check.REPO_ROOT) == []


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


# ---- verdict_commit must exist in the git history ----------------------

def _git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True,
                          text=True).stdout.strip()


@pytest.fixture
def repo(tmp_path):
    """Throwaway repo: main has commits A <- B; branch 'side' has commit S (not in HEAD)."""
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "t@example.invalid")
    _git(root, "config", "user.name", "t")
    _git(root, "config", "commit.gpgsign", "false")
    shas = {}
    for name in ("A", "B"):
        (root / "f.txt").write_text(name, encoding="utf-8")
        _git(root, "add", "f.txt")
        _git(root, "commit", "-q", "-m", name)
        shas[name] = _git(root, "rev-parse", "HEAD")
    _git(root, "checkout", "-q", "-b", "side", shas["A"])
    (root / "g.txt").write_text("S", encoding="utf-8")
    _git(root, "add", "g.txt")
    _git(root, "commit", "-q", "-m", "S")
    shas["S"] = _git(root, "rev-parse", "HEAD")
    _git(root, "checkout", "-q", "main")
    return root, shas


def _with_commit(mid, sha):
    record = _record(mid, "T02.10")
    record["verdict_commit"] = sha
    return record


def test_verdict_commit_in_history_passes(repo):
    root, shas = repo
    approvals = {M4: _with_commit(M4, shas["A"]), M8: None}
    assert ledger_check.hr_commit_violations(approvals, root) == []


def test_nonexistent_verdict_commit_fails(repo):
    root, _ = repo
    missing = "1234567890abcdef1234567890abcdef12345678"
    assert ledger_check.hr_commit_violations({M4: _with_commit(M4, missing)}, root) == [
        f"{M4}: verdict_commit {missing} not in the history of HEAD"]


def test_verdict_commit_outside_head_history_fails(repo):
    root, shas = repo
    assert ledger_check.hr_commit_violations({M4: _with_commit(M4, shas["S"])}, root) == [
        f"{M4}: verdict_commit {shas['S']} not in the history of HEAD"]


@pytest.mark.parametrize("bad", [None, "", "abc1234", "G" * 40])
def test_malformed_verdict_commit_fails(repo, bad):
    root, _ = repo
    assert ledger_check.hr_commit_violations({M4: _with_commit(M4, bad)}, root) != []


def test_shallow_checkout_fails_closed_with_clear_message(repo, tmp_path):
    root, shas = repo
    shallow = tmp_path / "shallow"
    subprocess.run(["git", "clone", "-q", "--depth", "1", "--branch", "main", root.as_uri(), str(shallow)],
                   check=True, capture_output=True)
    assert _git(shallow, "rev-parse", "--is-shallow-repository") == "true"
    # Even a commit that IS in the real history is not accepted from a shallow clone.
    violations = ledger_check.hr_commit_violations({M4: _with_commit(M4, shas["A"])}, shallow)
    assert len(violations) == 1 and "shallow" in violations[0] and "fetch-depth: 0" in violations[0]


def test_shallow_checkout_with_empty_registry_passes(repo, tmp_path):
    root, _ = repo
    shallow = tmp_path / "shallow"
    subprocess.run(["git", "clone", "-q", "--depth", "1", root.as_uri(), str(shallow)],
                   check=True, capture_output=True)
    assert ledger_check.hr_commit_violations({M4: None, M8: None}, shallow) == []


def test_not_a_git_repo_fails_closed(tmp_path):
    violations = ledger_check.hr_commit_violations({M4: _with_commit(M4, "a" * 40)}, tmp_path)
    assert len(violations) == 1 and "git" in violations[0]
