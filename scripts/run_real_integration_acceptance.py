#!/usr/bin/env python3
"""NEXT-04 real integration acceptance harness.

Requires dedicated TEST account credentials via environment / private files.
Refuses to invent results. Packaged EXE path is required for final PASS.

Env (examples — never commit secrets):
  KARRIEREKRAKE_GMAIL_CREDENTIALS=private/gmail_credentials.json
  KARRIEREKRAKE_MS_CLIENT_ID=...
  KARRIEREKRAKE_IMAP_HOST=...
  KARRIEREKRAKE_IMAP_USER=...
  KARRIEREKRAKE_IMAP_PASSWORD=...   # loaded into keyring only at runtime
  KARRIEREKRAKE_CALDAV_URL=...
  KARRIEREKRAKE_ACCEPTANCE_EXE=/path/to/Karrierekrake.exe
  KARRIEREKRAKE_RUN_LIVE=1          # must be set to attempt live probes
"""

from __future__ import annotations

import json
import os
import platform
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

REPORT_PATH = ROOT / "docs" / "project" / "next-04-real-integration-acceptance.md"


@dataclass
class ProviderGate:
    provider: str
    AUTH: str = "NOT_RUN"
    API: str = "NOT_RUN"
    SYNC: str = "NOT_RUN"
    RESTART: str = "NOT_RUN"
    REVOKE: str = "NOT_RUN"
    OFFLINE_FAILURE: str = "NOT_RUN"
    PACKAGED_EXE: str = "NOT_RUN"
    notes: list[str] = field(default_factory=list)

    def to_row(self) -> str:
        return (
            f"| {self.provider} | {self.AUTH} | {self.API} | {self.SYNC} | "
            f"{self.RESTART} | {self.REVOKE} | {self.OFFLINE_FAILURE} | {self.PACKAGED_EXE} |"
        )


PROVIDERS = [
    "GOOGLE_GMAIL",
    "GOOGLE_CALENDAR",
    "MICROSOFT_MAIL",
    "MICROSOFT_CALENDAR",
    "IMAP",
    "CALDAV",
]


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes"}


def assess_environment() -> dict:
    exe = os.environ.get("KARRIEREKRAKE_ACCEPTANCE_EXE", "").strip()
    return {
        "os": platform.system(),
        "is_windows": platform.system() == "Windows",
        "run_live": _env_truthy("KARRIEREKRAKE_RUN_LIVE"),
        "exe_path": exe,
        "exe_exists": bool(exe) and Path(exe).is_file(),
        "gmail_credentials": bool(
            os.environ.get("KARRIEREKRAKE_GMAIL_CREDENTIALS")
            or (ROOT / "private" / "gmail_credentials.json").is_file()
        ),
        "ms_client_id": bool(os.environ.get("KARRIEREKRAKE_MS_CLIENT_ID")),
        "imap_configured": bool(
            os.environ.get("KARRIEREKRAKE_IMAP_HOST")
            and os.environ.get("KARRIEREKRAKE_IMAP_USER")
        ),
        "caldav_configured": bool(os.environ.get("KARRIEREKRAKE_CALDAV_URL")),
    }


def run() -> dict:
    from integrations.providers.diagnostics import DiagStage, clear_events, log_stage, recent_events

    clear_events()
    log_stage(DiagStage.CONFIG_LOAD, provider="acceptance", ok=True, detail="harness_start")
    env = assess_environment()
    gates = {p: ProviderGate(provider=p) for p in PROVIDERS}

    blockers: list[str] = []
    if not env["run_live"]:
        blockers.append("KARRIEREKRAKE_RUN_LIVE not set — refusing to claim live PASS")
    if not env["is_windows"]:
        blockers.append(f"Host OS is {env['os']} — packaged Karrierekrake.exe acceptance requires Windows")
    if not env["exe_exists"]:
        blockers.append("Packaged EXE path missing/unusable (KARRIEREKRAKE_ACCEPTANCE_EXE)")
    if not env["gmail_credentials"]:
        blockers.append("No Google OAuth client credentials for dedicated test account")
    if not env["ms_client_id"]:
        blockers.append("No Microsoft client id (KARRIEREKRAKE_MS_CLIENT_ID)")
    if not env["imap_configured"]:
        blockers.append("No IMAP test account env")
    if not env["caldav_configured"]:
        blockers.append("No CalDAV test account env")

    # Without live credentials / Windows EXE we mark honest NOT_RUN / BLOCKED.
    for g in gates.values():
        if blockers:
            g.notes.extend(blockers)
            g.AUTH = "BLOCKED"
            g.API = "BLOCKED"
            g.SYNC = "BLOCKED"
            g.RESTART = "BLOCKED"
            g.REVOKE = "BLOCKED"
            g.OFFLINE_FAILURE = "BLOCKED"
            g.PACKAGED_EXE = "BLOCKED" if not env["exe_exists"] or not env["is_windows"] else "NOT_RUN"

    # Infrastructure unit checks that do NOT count as provider acceptance:
    infra_ok = True
    try:
        from integrations.providers.connection_probe import (
            ConnectionState,
            ProbeResult,
            clear_probe_cache,
        )
        from integrations.providers.diagnostics import DiagStage as DS

        clear_probe_cache()
        assert ConnectionState.PROBE_OK.value == "probe_ok"
        log_stage(DS.API_PROBE, provider="acceptance", ok=True, detail="infra_ok")
    except Exception as exc:
        infra_ok = False
        blockers.append(f"infra:{type(exc).__name__}")

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "environment": env,
        "blockers": blockers,
        "infra_probe_module_ok": infra_ok,
        "gates": {k: asdict(v) for k, v in gates.items()},
        "diag_tail": [e.to_dict() for e in recent_events(limit=30)],
        "policy": {
            "mock_tests_do_not_accept": True,
            "connected_requires_api_probe": True,
            "packaged_exe_required": True,
        },
    }
    _write_report(payload, gates, blockers, env, infra_ok)
    return payload


def _write_report(payload: dict, gates: dict, blockers: list[str], env: dict, infra_ok: bool) -> None:
    lines = [
        "# NEXT-04 — Real Integration Acceptance",
        "",
        f"**Generated:** {payload['generated_at']}",
        "",
        "## Verdict",
        "",
        "**NO PROVIDER ACCEPTED** based on mocks. Live packaged-EXE acceptance is "
        + ("**BLOCKED** on this agent." if blockers else "ready to run."),
        "",
        "## Environment",
        "",
        f"- OS: `{env['os']}`",
        f"- RUN_LIVE: `{env['run_live']}`",
        f"- EXE present: `{env['exe_exists']}` (`{env['exe_path'] or '—'}`)",
        f"- Google credentials present: `{env['gmail_credentials']}`",
        f"- Microsoft client id present: `{env['ms_client_id']}`",
        f"- IMAP env present: `{env['imap_configured']}`",
        f"- CalDAV env present: `{env['caldav_configured']}`",
        f"- Probe/diag infra module: `{'OK' if infra_ok else 'FAIL'}`",
        "",
        "## Blockers",
        "",
    ]
    if blockers:
        for b in blockers:
            lines.append(f"- {b}")
    else:
        lines.append("- (none)")
    lines += [
        "",
        "## Provider gates",
        "",
        "| Provider | AUTH | API | SYNC | RESTART | REVOKE | OFFLINE FAILURE | PACKAGED EXE |",
        "|----------|------|-----|------|---------|--------|-----------------|--------------|",
    ]
    for p in PROVIDERS:
        lines.append(gates[p].to_row())
    lines += [
        "",
        "## Rules",
        "",
        "- Never show UI **Verbunden** until API probe succeeds.",
        "- Diagnostic stages: CONFIG_LOAD → AUTH_START → BROWSER_OPEN → CALLBACK → "
        "TOKEN_EXCHANGE → TOKEN_STORE → SERVICE_BUILD → API_PROBE → SYNC → CONNECTED.",
        "- No token values in logs.",
        "- Dedicated test accounts only (see `docs/google/oauth-test-accounts.md`).",
        "",
        "## How to run live (Windows + secrets)",
        "",
        "```bat",
        "set KARRIEREKRAKE_RUN_LIVE=1",
        "set KARRIEREKRAKE_ACCEPTANCE_EXE=C:\\path\\Karrierekrake.exe",
        "set KARRIEREKRAKE_GMAIL_CREDENTIALS=private\\gmail_credentials.json",
        "set KARRIEREKRAKE_MS_CLIENT_ID=...",
        "python scripts/run_real_integration_acceptance.py",
        "```",
        "",
        "Machine-readable twin: `artifacts/acceptance/next04_gates.json` (when written).",
        "",
    ]
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    out_json = ROOT / "artifacts" / "acceptance" / "next04_gates.json"
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")


if __name__ == "__main__":
    result = run()
    print(json.dumps({"blockers": result["blockers"], "report": str(REPORT_PATH)}, indent=2))
    # Non-zero when blocked — CI should not treat as provider PASS.
    sys.exit(0 if not result["blockers"] else 2)
