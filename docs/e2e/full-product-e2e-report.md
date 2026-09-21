# Karrierekrake — Full Product E2E / Chaos Megapass Report

## A. Branch / HEAD

- Branch: `cursor/full-product-e2e-chaos-d85b`
- Commit SHA: `c7b1a3917e127d6b4524acc8f026c5fd46254320`
- Base: `main`

## B. Test environment

- Isolated temp `LOCALAPPDATA` / AppData tree per test (`tests/e2e/harness.py`)
- Isolated SQLite DB per test
- `settings.dry_run = True`, `mode = search_only`
- In-memory keyring (`tests/conftest.py`)
- `QT_QPA_PLATFORM=offscreen` for UI shell tests
- **No real network, no real Gmail, no real calendar write, no real ATS submit**

## C. Fake providers used

| Provider | Path |
|----------|------|
| FakeGmailService / FakeCreds / MemoryCursorStore | `tests/e2e/providers/fake_gmail.py` |
| FakeJobSource | `tests/e2e/providers/fake_calendar.py` |
| MockFreeBusyProvider | `integrations/calendar_freebusy.py` |
| InMemoryCalendarTransport + CalendarWriteGate | `integrations/calendar_write.py` |
| SendGate (draft-only) | `integrations/reply_draft.py` |
| Lifecycle corpora | `tests/fixtures/lifecycle_e2e/` + `tests/lifecycle_e2e/` |

## D. Scenario / fixture volume

| Corpus | Count |
|--------|------:|
| Personas | 8 |
| Jobs (E2E corpus) | ≥100 (130 loaded) |
| Recruiting + injection mails | 575 |
| Association scenarios | 352 |
| Status transitions | 300 |
| Calendar cases | 200 |
| Reply scenarios | 219 |
| Full lifecycles | 50 |
| Automated pytest cases (this run) | 150 (148 passed, 2 skipped) |

Parametrized + corpus-driven cases exercise far more logical scenarios than the pytest node count (classification ≥500, association ≥200, calendar idempotency ×80, etc.).

## E. Full user journeys tested

1. **Happy path** — profile → job → application → confirm → review → interview → calendar (idempotent) → reply draft (not sent) → follow-up → offer → restart persistence
2. **Rejection path** — confirm → review → rejection; other role at another company not auto-rejected
3. **Interview reschedule** — invite → calendar → reschedule mail; no event explosion
4. **Ambiguous mail** — two apps same company → review / no false confident link → manual confirm B persists
5. **Offline** — profile/apps usable; failing job source does not corrupt DB
6. **Persona restarts** — all 8 personas persist across reload

## F–T. Subsystem results

| Area | Result |
|------|--------|
| Profile / CV destruction | PASS |
| SearchIntent variants | PASS (after P1 fix) |
| Search chaos (spam/cancel/fail/malformed) | PASS |
| Jobs corpus / seed | PASS |
| Applications volume 0/1/5/50 | PASS |
| Mail classification gates | PASS |
| Association zero-gates | PASS |
| Lifecycle transitions / full lifecycles | PASS |
| Calendar / interview | PASS |
| Reply / follow-up (never auto-send) | PASS |
| Offline | PASS |
| Recovery / reload mid-flow | PASS |
| Accessibility / Qt shell | PASS (2 optional skips) |
| Layout / visual state seeds | PASS |
| Privacy export / no real PII fixtures | PASS |
| Chaos user / impossible workflows | PASS |
| Prompt injection hostile mail | PASS |
| Dev fixture isolation (fresh env empty) | PASS |

## U–X. Defects

### P0 — none open

### P1 — found & fixed

**SearchIntent geo/salary/remote overwritten by legacy LocationConfig defaults on save when roles empty.**

- Symptom: `radius_km=0`, `remote_mode=remote`, `countries=["AT"]`, `salary_min=1` did not survive `ConfigService.save` / reload; defaults (20 km, DE) won.
- Root cause: `is_empty()` treats geo-only intents as empty (by design for title-lift), then `migrate_legacy_search_preferences` rebuilt intent from location/employment defaults and discarded explicit geo fields.
- Fix: preserve explicit geo/salary/remote/strictness from `existing_intent` during migration (`core/search_intent.py`).
- Regression: `tests/test_search_intent.py::test_explicit_geo_only_intent_not_overwritten_by_location_defaults`

### P2 — documented (no silent data loss)

**`ApplicationProfile.address` is recomposed from street/city/country on every save** (`sync_address`). Free-form writes to `address` alone do not persist when structured fields exist. Tests now write via `street`. Not a corruption bug; UX should prefer structured fields.

### Dual-write note

Clearing `search_intent` alone does not clear `jobs.desired_titles` mirrors; save may lift titles back. Clearing both is required for a full search reset (documented in E2E test).

## Y. Critical zero-gate matrix

| Gate | Value |
|------|------:|
| false rejection | 0 |
| false offer | 0 |
| false confident association | 0 |
| cross-ApplicationCase mutation | 0 |
| duplicate calendar event (idempotent path) | 0 |
| real email sent | 0 |
| real PII fixture | 0 |
| prompt injection → system action | 0 |
| dry-run / draft-only violations | 0 |

## Z. Final readiness verdicts

| Verdict | Result |
|---------|--------|
| FUNCTIONAL E2E | **PASS** |
| DATA INTEGRITY | **PASS** |
| SEARCH | **PASS** |
| APPLICATION LIFECYCLE | **PASS** |
| MAIL | **PASS** |
| ASSOCIATION | **PASS** |
| CALENDAR | **PASS** |
| INTERVIEW | **PASS** |
| GÜNTHER INTEGRATION | **PASS** (offline / draft paths; no live model required) |
| RECOVERY | **PASS** |
| OFFLINE | **PASS** |
| ACCESSIBILITY | **PASS** (keyboard smoke + a11y name probe) |
| PRIVACY | **PASS** |
| SECURITY | **PASS** (hostile content / injection corpora) |
| CHAOS USER | **PASS** |
| **OVERALL PRODUCT E2E** | **PASS** |

---

## Artifacts

- `artifacts/e2e/results.json`
- `artifacts/e2e/reports/pytest_output.txt`
- `artifacts/e2e/reports/junit.xml`
- `artifacts/e2e/screenshots/*.txt` (state markers; optional PNG via `KARRIEREKRAKE_E2E_SHOTS=1`)

## How to re-run

```bash
python scripts/run_full_product_e2e.py
# or
QT_QPA_PLATFORM=offscreen pytest tests/e2e tests/test_lifecycle_e2e_matrix.py tests/test_lifecycle_e2e_factory.py -q
```

**STOP for human review — do not auto-merge.**
