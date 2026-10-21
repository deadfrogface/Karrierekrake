"""Filled beta session files (T15.03) must stay valid and never claim approval silently."""
import json
from pathlib import Path

import pytest

from scripts.beta_acceptance_report import summarize_session

SESSIONS = sorted((Path(__file__).resolve().parents[1] / "docs" / "beta" / "sessions").glob("*.json"))


def test_session_files_exist():
    assert SESSIONS, "docs/beta/sessions/*.json missing"


@pytest.mark.parametrize("path", SESSIONS, ids=lambda p: p.name)
def test_session_file_validates_and_identity_is_consistent(path):
    session = json.loads(path.read_text(encoding="utf-8"))
    summary = summarize_session(session)
    statuses = {row["status"] for row in session["results"]}
    # Approval only if every case passed; an identity-only entry is never approved.
    assert summary["approved"] is (statuses == {"pass"})
    identity = session.get("package_identity")
    if identity is not None:
        assert len(identity["pr_head_commit"]) == 40
        assert identity["artifact_zip_sha256"] != session["package_sha256"]


def _git_tree(commit):
    import subprocess
    try:
        out = subprocess.run(["git", "rev-parse", commit + "^{tree}"], cwd=Path(__file__).resolve().parents[1],
                             capture_output=True, text=True, timeout=30, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    tree = out.stdout.strip()
    return tree if out.returncode == 0 and len(tree) == 40 else None


@pytest.mark.parametrize("path", SESSIONS, ids=lambda p: p.name)
def test_merge_build_counts_for_head_only_via_same_tree(path):
    """Teamlead/Kritiker 19.10.2026: PR CI builds the merge commit; head evidence only via identical tree."""
    session = json.loads(path.read_text(encoding="utf-8"))
    identity = session.get("package_identity")
    if identity is None or session["commit"] == identity["pr_head_commit"]:
        return
    assert identity.get("build_kind") == "merge_build"
    assert identity.get("head_evidence_basis") == "same_tree"
    assert identity.get("head_evidence") is True
    tree = identity.get("tree", "")
    assert len(tree) == 40
    for commit in (session["commit"], identity["pr_head_commit"]):
        actual = _git_tree(commit)
        if actual is not None:  # commit objects present (shallow/partial clones may lack the merge commit)
            assert actual == tree, (commit, actual, tree)
    assert identity.get("pr_head_tree", tree) == tree


IDENTITIES_DOC = Path(__file__).resolve().parents[1] / "docs" / "beta" / "PR144_PACKAGE_IDENTITIES_2470ca16.md"
_SHA256 = __import__("re").compile(r"(?<![0-9a-f])[0-9a-f]{64}(?![0-9a-f])")


def test_identity_doc_every_table_hash_names_merge_build_origin():
    """Kritiker 19.10.2026: no hash may be attributed to the PR head 2470ca16."""
    rows = [line for line in IDENTITIES_DOC.read_text(encoding="utf-8").splitlines()
            if line.startswith("|") and _SHA256.search(line)]
    assert rows
    for line in rows:
        assert "gebaut aus `e0f9c383`" in line, line[:120]
        # every single hash on the row carries the origin, not just one per row
        assert line.count("gebaut aus `e0f9c383`") >= len(_SHA256.findall(line)), line[:120]


@pytest.mark.parametrize("path", SESSIONS, ids=lambda p: p.name)
def test_session_hashes_carry_built_from(path):
    session = json.loads(path.read_text(encoding="utf-8"))
    identity = session.get("package_identity")
    if identity is None:
        return
    built_from = identity.get("built_from", {})
    for key in ("package_sha256", "artifact_zip_sha256", "executable_sha256"):
        assert built_from.get(key) == session["commit"], key


_ROOT = Path(__file__).resolve().parents[1]
_T15_T16_DOCS = [
    _ROOT / "docs" / "beta" / "PR144_PACKAGE_IDENTITIES_2470ca16.md",
    _ROOT / "docs" / "commercial" / "PR144_DEMO_PROTOKOLL_2026-10-19.md",
]


def _t15_t16_coverage_rows():
    text = (_ROOT / "docs" / "project" / "PR144_COVERAGE_AND_GATES.md").read_text(encoding="utf-8")
    t15 = [l for l in text.splitlines() if "docs(beta): T15.03" in l]
    t16 = [l for l in text.splitlines() if "docs(demo): T16.03" in l]
    assert len(t15) == 1 and len(t16) == 1
    return t15[0], t16[0]


def test_t15_t16_docs_have_no_self_referencing_commit():
    texts = [p.read_text(encoding="utf-8") for p in _T15_T16_DOCS] + list(_t15_t16_coverage_rows())
    for t in texts:
        assert "dieser commit" not in t.lower()
        assert "this commit" not in t.lower()


def test_t15_t16_coverage_rows_name_real_beleg_commits():
    t15, t16 = _t15_t16_coverage_rows()
    assert "Beleg-Commit: `42ed77a4`" in t15
    assert "Beleg-Commit: `a4f626b2`" in t16


def test_t15_t16_docs_state_final_ci_status_of_39200083213():
    texts = [p.read_text(encoding="utf-8") for p in _T15_T16_DOCS] + list(_t15_t16_coverage_rows())
    for t in texts:
        assert "39200083213" in t
        assert "läuft/UNSICHER" not in t.split("39200083213", 1)[1][:200]
        assert "07:18:59 MESZ" in t
        assert "21/21" in t
