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
