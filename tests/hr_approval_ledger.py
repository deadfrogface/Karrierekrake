"""CI-only helper (not runtime): check HR approvals against the PR144 ledger.

guenther.setup_models.hr_unapproved checks only the record format; it never
reads docs/project/PR144_WORK_ITEMS.json. This module is used by
tests/test_hr_approval_ledger.py to require that every non-None
HR_APPROVAL entry references an existing work item whose ``status`` is
``"FERTIG"`` (the ledger's packages[].items[] carry ``id`` and ``status``)
and a ``verdict_commit`` that is an ancestor of HEAD
(``git merge-base --is-ancestor``). A shallow checkout cannot prove that, so
the commit check fails closed there (CI needs ``fetch-depth: 0`` once the
registry has entries).
"""
from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Mapping
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
LEDGER_PATH = REPO_ROOT / "docs" / "project" / "PR144_WORK_ITEMS.json"
_COMMIT_RE = re.compile(r"[0-9a-f]{40}")
REQUIRED_STATUS = "FERTIG"


def load_ledger(path: Path = LEDGER_PATH) -> dict[str, str]:
    """``{item id: status}`` for every item of every package in the ledger."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return {item["id"]: item.get("status") for package in data["packages"] for item in package["items"]}


def hr_ledger_violations(approvals: Mapping, ledger: Mapping[str, str]) -> list[str]:
    """One message per non-None approval whose work item is unknown or not FERTIG."""
    violations = []
    for mid, record in approvals.items():
        if record is None:
            continue
        item = record.get("work_item_id") if isinstance(record, Mapping) else None
        if not isinstance(item, str) or not item:
            violations.append(f"{mid}: malformed entry, no work_item_id")
        elif item not in ledger:
            violations.append(f"{mid}: work_item_id {item} not in ledger")
        elif ledger[item] != REQUIRED_STATUS:
            violations.append(f"{mid}: work_item_id {item} status {ledger[item]}, not {REQUIRED_STATUS}")
    return violations


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                          timeout=60, check=False)


def hr_commit_violations(approvals: Mapping, repo: Path = REPO_ROOT) -> list[str]:
    """One message per non-None approval whose ``verdict_commit`` is not in HEAD's history.

    Uses ``git merge-base --is-ancestor <sha> HEAD`` (stricter than
    ``git cat-file -e``: an object fetched from another branch is not
    enough). Fails closed when git or the repository is unavailable and when
    the checkout is shallow.
    """
    entries = {mid: record for mid, record in approvals.items() if record is not None}
    if not entries:
        return []
    try:
        shallow = _git(repo, "rev-parse", "--is-shallow-repository")
    except (OSError, subprocess.SubprocessError) as error:
        return [f"git unavailable, cannot verify verdict_commit: {type(error).__name__}"]
    if shallow.returncode != 0:
        return [f"{repo} is not a git repository, cannot verify verdict_commit"]
    if shallow.stdout.strip() == "true":
        return [("shallow checkout: verdict_commit cannot be verified against the git history; "
                 "check out with fetch-depth: 0 (actions/checkout) to run this gate")]
    violations = []
    for mid, record in entries.items():
        sha = record.get("verdict_commit") if isinstance(record, Mapping) else None
        if not isinstance(sha, str) or _COMMIT_RE.fullmatch(sha) is None:
            violations.append(f"{mid}: malformed verdict_commit")
            continue
        if _git(repo, "merge-base", "--is-ancestor", sha, "HEAD").returncode != 0:
            violations.append(f"{mid}: verdict_commit {sha} not in the history of HEAD")
    return violations
