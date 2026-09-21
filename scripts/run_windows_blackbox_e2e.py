#!/usr/bin/env python3
"""NEXT-06 — Real Windows black-box human E2E runner.

Does not claim PASS on Linux. Writes honest gate report.

  set KARRIEREKRAKE_RUN_BLACKBOX=1
  set KARRIEREKRAKE_ACCEPTANCE_EXE=C:\\path\\Karrierekrake.exe
  python scripts/run_windows_blackbox_e2e.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

REPORT_MD = ROOT / "docs" / "project" / "next-06-windows-blackbox-e2e.md"
ARTIFACTS = ROOT / "artifacts" / "blackbox"


def main() -> int:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    (ARTIFACTS / "reports").mkdir(parents=True, exist_ok=True)

    from tests.blackbox.flows.human_journey import run_human_journey
    from tests.blackbox.flows.provider_matrix import run_provider_matrix
    from tests.blackbox.harness import assess_environment

    env = assess_environment()
    journey = run_human_journey()
    matrix = run_provider_matrix()

    # Always run classification tests (Linux-safe).
    class_proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/blackbox/test_classification.py",
            "tests/test_next06_fake_boundary.py",
            "-q",
            "--tb=line",
        ],
        cwd=ROOT,
    )

    # Optional Windows EXE tests
    exe_rc = 0
    if env.can_run:
        exe_proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "tests/blackbox/test_windows_exe.py",
                "-q",
                "--tb=short",
                "-m",
                "blackbox_windows",
            ],
            cwd=ROOT,
        )
        exe_rc = exe_proc.returncode

    payload = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "evidence_class": "real_windows_blackbox_human_e2e",
        "synthetic_offline_e2e": "SEPARATE_SUITE",
        "real_product_acceptance_ready": bool(
            env.can_run and journey.get("status") == "PASS" and class_proc.returncode == 0
        ),
        "env": {
            "os": env.os_name,
            "can_run": env.can_run,
            "blockers": env.blockers,
            "exe": env.exe_path,
        },
        "journey": journey,
        "provider_matrix": matrix,
        "classification_pytest_rc": class_proc.returncode,
        "windows_exe_pytest_rc": exe_rc,
        "bugfix_rule": (
            "A bug is only fixed when: original visible EXE reproduction → FAIL before "
            "→ fix → PASS afterward. Unit test green alone is not enough."
        ),
    }
    (ARTIFACTS / "reports" / "next06_gates.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    _write_md(payload)
    if class_proc.returncode != 0:
        return class_proc.returncode
    if env.can_run and (journey.get("status") != "PASS" or exe_rc != 0):
        return 1
    return 0


def _write_md(payload: dict) -> None:
    env = payload["env"]
    journey = payload["journey"]
    matrix = payload["provider_matrix"]
    lines = [
        "# NEXT-06 — Real Windows Black-Box Human E2E",
        "",
        f"**Generated:** {payload['generated']}",
        "",
        "## Verdict",
        "",
        f"- **REAL PRODUCT ACCEPTANCE READY:** "
        f"{'YES' if payload['real_product_acceptance_ready'] else 'NO'}",
        f"- Journey: `{journey.get('status')}`",
        f"- Provider matrix: `{matrix.get('status')}`",
        f"- Synthetic offline suite: **SEPARATE** (`tests/e2e`) — not acceptance",
        "",
        "## Environment",
        "",
        f"- OS: `{env['os']}`",
        f"- can_run: `{env['can_run']}`",
        f"- EXE: `{env['exe'] or '—'}`",
        "",
        "### Blockers",
        "",
    ]
    if env["blockers"]:
        for b in env["blockers"]:
            lines.append(f"- {b}")
    else:
        lines.append("- (none)")
    lines += [
        "",
        "## Human flow steps",
        "",
    ]
    for s in journey.get("steps_planned") or []:
        done = s in (journey.get("steps_completed") or [])
        lines.append(f"- [{'x' if done else ' '}] `{s}`")
    lines += [
        "",
        "## Provider matrix",
        "",
        "| Pair | Mail | Calendar | AUTH | EXE |",
        "|------|------|----------|------|-----|",
    ]
    for row in matrix.get("pairs") or []:
        lines.append(
            f"| {row['name']} | {row['mail']} | {row['calendar']} | "
            f"{row['AUTH']} | {row['PACKAGED_EXE']} |"
        )
    lines += [
        "",
        "## Zero gates",
        "",
        "false rejection = 0 · false offer = 0 · false confident association = 0 ·",
        "cross-case mutation = 0 · duplicate calendar event = 0 ·",
        "duplicate paid Maps request = 0 · real employer mail = 0 ·",
        "real application submission = 0 · PII committed = 0",
        "",
        "## Bug-fix rule",
        "",
        payload["bugfix_rule"],
        "",
        "## How to run (Windows)",
        "",
        "```bat",
        "set KARRIEREKRAKE_RUN_BLACKBOX=1",
        "set KARRIEREKRAKE_ACCEPTANCE_EXE=C:\\path\\Karrierekrake.exe",
        "pip install pywinauto pillow",
        "python scripts/run_windows_blackbox_e2e.py",
        "```",
        "",
        "Machine-readable: `artifacts/blackbox/reports/next06_gates.json`",
        "",
    ]
    REPORT_MD.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
