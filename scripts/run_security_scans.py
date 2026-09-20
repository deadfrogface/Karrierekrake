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


def _write_runtime_freeze(path: Path) -> Path:
    """Write installed packages relevant to the shipped runtime surface."""
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = subprocess.check_output(
        [sys.executable, "-m", "pip", "freeze"],
        cwd=str(ROOT),
        text=True,
    )
    # Drop install/CI tooling and optional AI stacks that are not in
    # requirements-runtime.txt — they create false OSV noise (and in some
    # cases mis-parsed package names like a phantom pip==9.0.3).
    skip_prefixes = (
        "pip==",
        "pip-",
        "pip_",
        "setuptools==",
        "wheel==",
        "pip-audit==",
        "pip_audit==",
        "bandit==",
        "pytest==",
        "pyinstaller==",
        "ruff==",
        "radon==",
        "vulture==",
        "hypothesis==",
        "freezegun==",
        "jsonschema==",
        "pipdeptree==",
        "dspy==",
        "dspy-ai==",
        "diskcache==",
        "llama_cpp_python==",
        "llama-cpp-python==",
    )
    lines: list[str] = []
    for line in raw.splitlines():
        low = line.strip().lower()
        if not low or low.startswith("#"):
            continue
        if any(low.startswith(p.lower()) for p in skip_prefixes):
            continue
        lines.append(line.strip())
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _osv_max_score(vuln: dict) -> float:
    best = 0.0
    for sev in vuln.get("severity") or []:
        score = str(sev.get("score") or "")
        # CVSS:3.1/AV:... — table also shows numeric; prefer vector base if present
        if score.replace(".", "", 1).isdigit():
            best = max(best, float(score))
            continue
        # Rough parse of CVSS v3/v4 numeric from database_specific if any
    db = vuln.get("database_specific") or {}
    sev_label = str(db.get("severity") or "").upper()
    label_map = {"CRITICAL": 9.5, "HIGH": 8.0, "MODERATE": 5.0, "MEDIUM": 5.0, "LOW": 2.0}
    if sev_label in label_map:
        best = max(best, label_map[sev_label])
    # Parse CVSS vector base score is hard; use OSV's cvss_v3 score field when present
    for sev in vuln.get("severity") or []:
        typ = str(sev.get("type") or "")
        score = str(sev.get("score") or "")
        if typ.startswith("CVSS") and score.startswith("CVSS:"):
            # Fall back to label map via known high vectors containing C:H/I:H
            if "/C:H" in score or "/VC:H" in score or "/I:H" in score or "/VI:H" in score:
                best = max(best, 8.0)
            elif "/A:H" in score or "/VA:H" in score:
                best = max(best, 7.0)
    return best


def run_osv() -> int:
    exe = shutil.which("osv-scanner") or shutil.which("osv-scanner.exe")
    if not exe:
        print("osv-scanner not installed on PATH", file=sys.stderr)
        return 1
    freeze = _write_runtime_freeze(ROOT / "artifacts" / "runtime-freeze.txt")
    json_path = ROOT / "artifacts" / "osv-scanner.json"
    cmd = [
        exe,
        "scan",
        "source",
        "-L",
        f"requirements.txt:{freeze}",
        "-f",
        "json",
        "--output-file",
        str(json_path),
    ]
    # Always emit human table too for CI logs
    table_cmd = [
        exe,
        "scan",
        "source",
        "-L",
        f"requirements.txt:{freeze}",
        "-f",
        "table",
    ]
    _run(table_cmd, check=False)
    try:
        _run(cmd, check=False)
    except subprocess.CalledProcessError:
        pass
    if not json_path.is_file():
        print("osv-scanner produced no JSON report", file=sys.stderr)
        return 1
    try:
        payload = json.loads(json_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        print("osv-scanner JSON unreadable", file=sys.stderr)
        return 1

    high_hits: list[str] = []
    low_hits: list[str] = []
    for result in payload.get("results") or []:
        for pkg in result.get("packages") or []:
            name = (pkg.get("package") or {}).get("name") or "?"
            version = (pkg.get("package") or {}).get("version") or "?"
            for vuln in pkg.get("vulnerabilities") or []:
                vid = vuln.get("id") or "?"
                score = _osv_max_score(vuln)
                row = f"{name}=={version} {vid} score~={score:.1f}"
                if score >= 7.0:
                    high_hits.append(row)
                else:
                    low_hits.append(row)

    if low_hits:
        print(f"OSV non-blocking findings ({len(low_hits)} <7.0):")
        for row in low_hits[:30]:
            print(" -", row)
    if high_hits:
        print("OSV High/Critical findings (release blockers):", file=sys.stderr)
        for row in high_hits:
            print(" -", row, file=sys.stderr)
        print(
            "Document reviewed non-applicable cases in docs/security/dependency-exceptions.md",
            file=sys.stderr,
        )
        return 1
    print("OSV: no High/Critical findings on runtime freeze")
    return 0


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
