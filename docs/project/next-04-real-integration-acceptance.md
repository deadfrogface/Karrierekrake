# NEXT-04 — Real Integration Acceptance

**Generated:** 2026-09-21T19:00:04.097314+00:00

## Verdict

**NO PROVIDER ACCEPTED** based on mocks. Live packaged-EXE acceptance is **BLOCKED** on this agent.

## Environment

- OS: `Linux`
- RUN_LIVE: `False`
- EXE present: `False` (`—`)
- Google credentials present: `False`
- Microsoft client id present: `False`
- IMAP env present: `False`
- CalDAV env present: `False`
- Probe/diag infra module: `OK`

## Blockers

- KARRIEREKRAKE_RUN_LIVE not set — refusing to claim live PASS
- Host OS is Linux — packaged Karrierekrake.exe acceptance requires Windows
- Packaged EXE path missing/unusable (KARRIEREKRAKE_ACCEPTANCE_EXE)
- No Google OAuth client credentials for dedicated test account
- No Microsoft client id (KARRIEREKRAKE_MS_CLIENT_ID)
- No IMAP test account env
- No CalDAV test account env

## Provider gates

| Provider | AUTH | API | SYNC | RESTART | REVOKE | OFFLINE FAILURE | PACKAGED EXE |
|----------|------|-----|------|---------|--------|-----------------|--------------|
| GOOGLE_GMAIL | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| GOOGLE_CALENDAR | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| MICROSOFT_MAIL | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| MICROSOFT_CALENDAR | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| IMAP | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| CALDAV | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |

## Rules

- Never show UI **Verbunden** until API probe succeeds.
- Diagnostic stages: CONFIG_LOAD → AUTH_START → BROWSER_OPEN → CALLBACK → TOKEN_EXCHANGE → TOKEN_STORE → SERVICE_BUILD → API_PROBE → SYNC → CONNECTED.
- No token values in logs.
- Dedicated test accounts only (see `docs/google/oauth-test-accounts.md`).

## How to run live (Windows + secrets)

```bat
set KARRIEREKRAKE_RUN_LIVE=1
set KARRIEREKRAKE_ACCEPTANCE_EXE=C:\path\Karrierekrake.exe
set KARRIEREKRAKE_GMAIL_CREDENTIALS=private\gmail_credentials.json
set KARRIEREKRAKE_MS_CLIENT_ID=...
python scripts/run_real_integration_acceptance.py
```

Machine-readable twin: `artifacts/acceptance/next04_gates.json` (when written).

