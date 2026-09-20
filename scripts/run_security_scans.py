#!/usr/bin/env python3
"""Run supply-chain / SAST / secret scanners for CI.

Exits non-zero on unresolved High/Critical dependency findings.
Ignores are loaded only from scripts/security_ignore_vulns.txt and must be
documented in docs/security/dependency-exceptions.md.
Does not install malicious packages for testing.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXCEPTIONS_DOC = ROOT / "docs" / "security" / "dependency-exceptions.md"
IGNORE_FILE = ROOT / "scripts" / "security_ignore_vulns.txt"


def _run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    print("+", " ".join(cmd), flush=True)
    return subprocess.run(
        cmd,
        cwd=str(ROOT),
        text=True,
        capture_output=False,
        check=check,
    )


def _load_ignores() -> list[str]:
    if not IGNORE_FILE.is_file():
        return []
    out: list[str] = []
    for line in IGNORE_FILE.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        out.append(s)
    if out and not EXCEPTIONS_DOC.is_file():
        raise SystemExit("security_ignore_vulns.txt present but exceptions doc missing")
    doc = EXCEPTIONS_DOC.read_text(encoding="utf-8") if EXCEPTIONS_DOC.is_file() else ""
    for vid in out:
        if vid not in doc:
            raise SystemExit(
                f"ignore {vid} is not documented in {EXCEPTIONS_DOC} — refuse silent allowlist"
            )
    return out


def run_pip_audit() -> int:
    """Audit the *currently installed* environment (CI installs runtime first)."""
    out = ROOT / "artifacts"
    out.mkdir(parents=True, exist_ok=True)
    json_path = out / "pip-audit.json"
    ignores = _load_ignores()
    cmd = [
        sys.executable,
        "-m",
        "pip_audit",
        "-l",
        "--progress-spinner",
        "off",
        "-f",
        "json",
        "-o",
        str(json_path),
    ]
    for vid in ignores:
        cmd.extend(["--ignore-vuln", vid])
    try:
        _run(cmd, check=True)
        return 0
    except subprocess.CalledProcessError:
        human = [
            sys.executable,
            "-m",
            "pip_audit",
            "-l",
            "--progress-spinner",
            "off",
        ]
        for vid in ignores:
            human.extend(["--ignore-vuln", vid])
        _run(human, check=False)
        print(
            "pip-audit reported unresolved vulnerabilities "
            "(High/Critical are release blockers; see dependency-exceptions.md)",
            file=sys.stderr,
        )
        return 1


def run_bandit() -> int:
    targets = ["core", "guenther", "integrations", "search", "desktop", "scripts"]
    existing = [t for t in targets if (ROOT / t).exists()]
    # Report medium+ for visibility
    _run(
        [
            sys.executable,
            "-m",
            "bandit",
            "-q",
            "-r",
            *existing,
            "-ll",
            "-ii",
            "-c",
            str(ROOT / ".bandit"),
        ],
        check=False,
    )
    # Gate: high severity only
    try:
        _run(
            [
                sys.executable,
                "-m",
                "bandit",
                "-q",
                "-r",
                *existing,
                "-lll",
                "-ii",
                "-c",
                str(ROOT / ".bandit"),
            ],
            check=True,
        )
        return 0
    except subprocess.CalledProcessError:
        return 1


def run_gitleaks() -> int:
    exe = shutil.which("gitleaks")
    if not exe:
        print("gitleaks not installed on PATH", file=sys.stderr)
        return 1
    report = ROOT / "artifacts" / "gitleaks.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    config = ROOT / ".gitleaks.toml"
    cmd = [
        exe,
        "detect",
        "--source",
        str(ROOT),
        "--no-git",
        "--redact",
        "-f",
        "json",
        "-r",
        str(report),
        "-v",
    ]
    if config.is_file():
        cmd.extend(["-c", str(config)])
    try:
        _run(cmd, check=True)
        return 0
    except subprocess.CalledProcessError:
        return 1


def run_osv() -> int:
    exe = shutil.which("osv-scanner")
    if not exe:
        print("osv-scanner not installed on PATH", file=sys.stderr)
        return 1
    # Scan runtime requirements (shipped surface), not the full monorepo lock soup.
    req = ROOT / "requirements-runtime.txt"
    cmd = [exe, "--format", "table", str(req)]
    try:
        _run(cmd, check=True)
        return 0
    except subprocess.CalledProcessError as exc:
        print(
            "OSV findings on requirements-runtime.txt — High/Critical are blockers "
            "unless documented in dependency-exceptions.md",
            file=sys.stderr,
        )
        return int(exc.returncode or 1)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--only",
        choices=("pip-audit", "bandit", "gitleaks", "osv", "all"),
        default="all",
    )
    args = parser.parse_args()
    os.makedirs(ROOT / "artifacts", exist_ok=True)
    steps = {
        "pip-audit": run_pip_audit,
        "bandit": run_bandit,
        "gitleaks": run_gitleaks,
        "osv": run_osv,
    }
    codes: list[int] = []
    selected = list(steps.items()) if args.only == "all" else [(args.only, steps[args.only])]
    for name, fn in selected:
        print(f"\n=== {name} ===", flush=True)
        codes.append(fn())
    worst = max(codes) if codes else 0
    summary = {
        "results": {name: code for (name, _), code in zip(selected, codes)},
        "ok": worst == 0,
    }
    (ROOT / "artifacts" / "security-scan-summary.json").write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2))
    return worst


if __name__ == "__main__":
    raise SystemExit(main())
