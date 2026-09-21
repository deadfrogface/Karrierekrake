# NEXT-06 — Real Windows Black-Box Human E2E

**Generated:** 2026-09-21T20:04:53.575029+00:00

## Verdict

- **REAL PRODUCT ACCEPTANCE READY:** NO
- Journey: `BLOCKED`
- Provider matrix: `BLOCKED`
- Synthetic offline suite: **SEPARATE** (`tests/e2e`) — not acceptance

## Environment

- OS: `Linux`
- can_run: `False`
- EXE: `—`

### Blockers

- Host OS is Linux — black-box requires Windows
- KARRIEREKRAKE_RUN_BLACKBOX (or RUN_LIVE) not set
- KARRIEREKRAKE_ACCEPTANCE_EXE missing or not a file
- pywinauto not installed

## Human flow steps

- [ ] `fresh_start`
- [ ] `onboarding`
- [ ] `profile`
- [ ] `real_local_cv_file_picker`
- [ ] `cv_preview`
- [ ] `verify_berufserfahrung_ausbildung`
- [ ] `save`
- [ ] `restart`
- [ ] `search_intent`
- [ ] `google_road_distance_job_search`
- [ ] `job_detail`
- [ ] `application_preview`
- [ ] `fake_safe_application`
- [ ] `bewerbungen`
- [ ] `inbox`
- [ ] `association`
- [ ] `lifecycle`
- [ ] `interview`
- [ ] `calendar`
- [ ] `reply_draft`
- [ ] `rejection`
- [ ] `separate_offer_case`
- [ ] `restart_2`
- [ ] `export`
- [ ] `delete_reset`

## Provider matrix

| Pair | Mail | Calendar | AUTH | EXE |
|------|------|----------|------|-----|
| google_google | google_gmail | google_calendar | BLOCKED | BLOCKED |
| microsoft_microsoft | microsoft_graph | microsoft_graph | BLOCKED | BLOCKED |
| imap_caldav | generic_imap | generic_caldav | BLOCKED | BLOCKED |
| mixed_gmail_ms_cal | google_gmail | microsoft_graph | BLOCKED | BLOCKED |
| fake_fake | fake_inprocess | fake_inprocess | BLOCKED | BLOCKED |

## Zero gates

false rejection = 0 · false offer = 0 · false confident association = 0 ·
cross-case mutation = 0 · duplicate calendar event = 0 ·
duplicate paid Maps request = 0 · real employer mail = 0 ·
real application submission = 0 · PII committed = 0

## Bug-fix rule

A bug is only fixed when: original visible EXE reproduction → FAIL before → fix → PASS afterward. Unit test green alone is not enough.

## How to run (Windows)

```bat
set KARRIEREKRAKE_RUN_BLACKBOX=1
set KARRIEREKRAKE_ACCEPTANCE_EXE=C:\path\Karrierekrake.exe
pip install pywinauto pillow
python scripts/run_windows_blackbox_e2e.py
```

Machine-readable: `artifacts/blackbox/reports/next06_gates.json`
