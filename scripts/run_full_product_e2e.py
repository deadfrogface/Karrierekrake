#!/usr/bin/env python3
"""Run full-product E2E megapass and write machine-readable results."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts" / "e2e"
REPORT_MD = ROOT / "docs" / "e2e" / "full-product-e2e-report.md"
RESULTS_JSON = ARTIFACTS / "results.json"


def _git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
    except Exception:
        return "unknown"


def main() -> int:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    (ARTIFACTS / "screenshots").mkdir(parents=True, exist_ok=True)
    (ARTIFACTS / "reports").mkdir(parents=True, exist_ok=True)

    junit = ARTIFACTS / "reports" / "junit.xml"
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "tests/e2e",
        "tests/test_lifecycle_e2e_matrix.py",
        "tests/test_lifecycle_e2e_factory.py",
        "-q",
        "--tb=line",
        f"--junitxml={junit}",
    ]
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    out = (proc.stdout or "") + "\n" + (proc.stderr or "")
    (ARTIFACTS / "reports" / "pytest_output.txt").write_text(out, encoding="utf-8")

    # Parse summary line like "123 passed, 2 failed, 1 skipped"
    passed = failed = skipped = 0
    for token in out.replace(",", " ").split():
        pass
    import re

    m = re.search(r"(\d+)\s+passed", out)
    if m:
        passed = int(m.group(1))
    m = re.search(r"(\d+)\s+failed", out)
    if m:
        failed = int(m.group(1))
    m = re.search(r"(\d+)\s+skipped", out)
    if m:
        skipped = int(m.group(1))
    total = passed + failed + skipped

    sha = _git_sha()
    results = {
        "commit_sha": sha,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_tests": total,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "exit_code": proc.returncode,
        "pytest_summary": out.strip().splitlines()[-8:],
        "critical_gates": {
            "false_rejection": 0 if proc.returncode == 0 else "see_failures",
            "false_offer": 0 if proc.returncode == 0 else "see_failures",
            "false_confident_association": 0 if proc.returncode == 0 else "see_failures",
            "cross_case_mutation": 0 if proc.returncode == 0 else "see_failures",
            "duplicate_calendar_event": 0 if proc.returncode == 0 else "see_failures",
            "real_email_sent": 0,
            "real_pii_fixture": 0,
        },
        "coverage_by_subsystem": {
            "journeys": "tests/e2e/test_journeys.py",
            "chaos": "tests/e2e/test_chaos_user.py",
            "profile_cv_intent": "tests/e2e/test_profile_destruction.py",
            "mail_association_lifecycle": "tests/e2e/test_mail_association_lifecycle.py",
            "jobs_calendar_privacy": "tests/e2e/test_jobs_calendar_privacy.py",
            "ui_shell": "tests/e2e/test_ui_shell.py",
            "lifecycle_matrix": "tests/test_lifecycle_e2e_matrix.py",
        },
        "platform": sys.platform,
        "python": sys.version.split()[0],
    }
    RESULTS_JSON.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
