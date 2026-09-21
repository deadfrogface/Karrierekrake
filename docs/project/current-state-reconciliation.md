# Current-State Reconciliation (NEXT-01)

**Audit date:** 2026-09-21  
**Sync note:** Updated after GitHub **#46** merged onto main (synthetic E2E + SearchIntent geo preserve).  
**Repository HEAD (main):** `8c3ea87a2660e68b3dce64f3e2eb6053014f1dab`  
**Binding product decisions:** [`docs/architecture/canonical-product-decisions.md`](../architecture/canonical-product-decisions.md)

### Naming

| Kind | Meaning |
|------|---------|
| GitHub `#N` | Actual merged/open pull request on GitHub |
| NEXT-01, NEXT-02, … | Forward work packages (this reconciliation is **NEXT-01**) |
| Historical “PR19–PR51” roadmap labels | **Not** interchangeable with future NEXT ids |

### Status legend

| Tag | Meaning |
|-----|---------|
| **DONE** | Implemented on main and consistent with target for that row |
| **PARTIAL** | Substantial code exists; gaps vs target or vs real users |
| **BROKEN_REAL_WORLD** | Tests may be green; real user / product behavior fails |
| **NOT_IMPLEMENTED** | Absent on main |
| **STALE_DOCUMENTATION** | Docs contradict code or new binding decisions |

### Evidence grades

| Grade | Meaning |
|-------|---------|
| CI | Green on main workflows (unit / Windows smoke / etc.) |
| Fixture | Synthetic corpora / mocked providers |
| Real-user | Observed by human on real Windows / real accounts / real files |
| None | No evidence |

---

## A. GitHub reality (do not invent)

### main HEAD

- Commit: `8c3ea87` — *Synthetic Offline Product E2E / Chaos Megapass (#46)*
- Prior: `d1ac05e` — *PR45: V2 UI — Matrix, Design Tokens & App Shell (#45)*
- CI on #46 merge SHA: **CI success**, **Windows Smoke success** (2026-09-21)

### Open PRs (at sync time)

| # | Title | State |
|---|-------|-------|
| **47** | NEXT-01 reconciliation + canonical product decisions | **OPEN** (this branch) |

### Merged GitHub PRs `#19`–`#46` (actual)

| # | Title (short) | Merged |
|---|----------------|--------|
| 19 | Günther local intelligence | 2026-09-18 |
| 20 | Profile data integrity | 2026-09-18 |
| 21 | Production sanitization | 2026-09-18 |
| 22 | SearchIntent domain model | 2026-09-18 |
| 23 | Deterministic search filter/rank | 2026-09-18 |
| 24 | DACH cross-border geo | 2026-09-18 |
| 25 | Recruiting contact discovery | 2026-09-18 |
| 26 | Contact verification | 2026-09-18 |
| 27 | Gmail OAuth & sync | 2026-09-18 |
| 28 | Email normalize/classify | 2026-09-18 |
| 29 | Email ↔ case association | 2026-09-18 |
| 30 | Lifecycle state machine | 2026-09-18 |
| 31 | Calendar scheduling engine | 2026-09-19 |
| 32 | Replies / follow-up / ghosting | 2026-09-19 |
| 33 | Lifecycle E2E factory | 2026-09-19 |
| 34 | Desktop design system | 2026-09-19 |
| 35 | Profile vs search UX | 2026-09-20 |
| 36 | Jobs/apps/timeline UX | 2026-09-20 |
| 37 | Mobile shared contracts | 2026-09-20 |
| 38 | Mobile companion MVP | 2026-09-20 |
| 39 | Mobile auth / secure storage | 2026-09-20 |
| 40 | Tokens / local data security | 2026-09-20 |
| 41 | Prompt injection / supply chain | 2026-09-20 |
| 42 | DSGVO privacy engineering | 2026-09-20 |
| 43 | Google production OAuth | 2026-09-20 |
| 44 | Accessibility / BFSG engineering | 2026-09-21 |
| 45 | V2 UI shell / tokens | 2026-09-21 |
| 46 | Synthetic offline product E2E / chaos + SearchIntent geo preserve | 2026-09-21 |

Earlier merges `#1`–`#18` cover branding, EXE smoke, adversarial gates, post-application lifecycle, etc.

---

## B. System matrix

Columns:

**SYSTEM | CURRENT IMPLEMENTATION | CURRENT TEST EVIDENCE | REAL USER VERIFIED | TARGET ARCHITECTURE | KEEP | CHANGE | REMOVE | OPEN BLOCKER | STATUS**

### 1. Guenther / local AI

| Field | Content |
|-------|---------|
| CURRENT IMPLEMENTATION | **ONE production LLM:** `phi4-mini` only (`microsoft_Phi-4-mini-instruct-Q4_K_M.gguf`, SHA `01999f17…c0c2`). Qwen retained in `HISTORICAL_MODEL_CATALOG` only. Settings: enable + fixed Phi label. Load failure → **GUENTHER_UNAVAILABLE** (no alternate LLM / no heuristic substitute). |
| CURRENT TEST EVIDENCE | `tests/test_next02_phi_cv.py`, Guenther unit suites; CI. |
| REAL USER VERIFIED | **None** for live Phi GGUF on Windows EXE in this agent. |
| TARGET ARCHITECTURE | **ONE Phi model only**; no Qwen; no user picker; unavailable → manual path. |
| KEEP | Deterministic validators; offline-first; fail-closed (no cloud LLM); quality/grounding gates. |
| CHANGE | Packaging/download/consent UX for commercial Phi weights. |
| REMOVE | ~~Qwen production/fallback/picker~~ (done NEXT-02). |
| OPEN BLOCKER | Packaging still does not ship weights; download/consent UX incomplete for commercial. |
| STATUS | **DONE** for ONE-Phi runtime policy; packaging **PARTIAL** |

### 2. Geo / commute distance

| Field | Content |
|-------|---------|
| CURRENT IMPLEMENTATION | **Google Maps Platform only** — Geocoding + Route Matrix Essentials via authenticated proxy. `Job.distance_km` = road km. Failure → `DISTANCE_UNKNOWN`. Haversine/pgeocode/Nominatim not authoritative. |
| TARGET | Same (NEXT-05 landed). |
| CHANGE | Done on `cursor/next-05-google-maps-geo-d85b`. |
| REMOVE | Production reliance on Nominatim, pgeocode, Haversine-as-commute. |
| OPEN BLOCKER | Live Google billing/API keys for Windows acceptance (proxy env). |
| CURRENT TEST EVIDENCE | `tests/test_next05_google_maps.py`, `tests/test_location.py`, `tests/test_dach_cross_border.py`. |
| REAL USER VERIFIED | **None** for live Google road km (needs Maps API key + proxy). Known product risk if misconfigured: missing proxy → UNKNOWN. |
| TARGET ARCHITECTURE | **Google Geocoding + Google Routes/Route Matrix only**; UNKNOWN if no route; never Luftlinie as Fahrt. |
| KEEP | UNKNOWN semantics; remote skip; DACH country intent rules (separate from routing). |
| STATUS | **PASS (code)** — live key acceptance still open. |

### 3. SearchIntent / job search / ranking

| Field | Content |
|-------|---------|
| CURRENT IMPLEMENTATION | SearchIntent model + deterministic filter/rank; pipeline dry-run default; sources BA/Indeed etc. **#46 fix:** empty-role rebuild preserves explicit geo/salary/remote/strictness from `existing_intent` (no overwrite by LocationConfig defaults). |
| CURRENT TEST EVIDENCE | Intent corpora, hard_filter, matcher, CI; #46 synthetic E2E + `tests/test_search_intent.py` regression. |
| REAL USER VERIFIED | Partial historical EXE defects fixed in early PRs; ongoing UX polish via #45. |
| TARGET | Keep deterministic authority; distance filter must consume Google route km when NEXT geo lands. |
| KEEP | SearchIntent ≠ profile; dry-run; cancel/pause; geo-preserve on role-empty rebuild. |
| CHANGE | Wire radius to route provider once Google geo ships. |
| REMOVE | — |
| OPEN BLOCKER | Live source flakiness (manual Live Sources workflow has failures). |
| STATUS | **PARTIAL** |

### 4. CV import

| Field | Content |
|-------|---------|
| CURRENT IMPLEMENTATION | Canonical pipeline: extract (pypdf **layout** + DOCX **tables**) → deterministic parse → **Phi** `suggest_cv_extract` when Guenther enabled → `validate_cv_extract` grounding → reconcile → `CvImportDialog` preview → YAML persist. |
| CURRENT TEST EVIDENCE | `cv_corpus` PDFs; `test_next02_phi_cv` (DOCX tables, Phi wiring, grounding); import replace suites. |
| REAL USER VERIFIED | Real private EXE accept **PENDING** (Windows black-box). Synthetic/layout improved; still treat real layouts as risk until EXE gate. |
| TARGET | Real EXE import path must show correct sections after apply+restart; layout-capable extract. |
| KEEP | Merge/replace semantics; no hallucinated profile; parser limits; Phi grounding DROP. |
| CHANGE | Complete Windows EXE black-box with private local CVs. |
| REMOVE | Trust in “corpus green ⇒ product ready”. |
| OPEN BLOCKER | No Windows black-box pywinauto gate on main; private CVs must stay local (`private/cvs/`). |
| STATUS | **PARTIAL** (Phi wired); real EXE **PENDING** |

### 5. Gmail / mail

| Field | Content |
|-------|---------|
| CURRENT IMPLEMENTATION | Explicit `mail_provider` (none/google_gmail/microsoft_graph/generic_imap). Google Gmail adapter reuses readonly OAuth+sync. Microsoft Graph + IMAP adapters with keyring secrets. **No auto-fallback.** |
| CURRENT TEST EVIDENCE | `tests/test_next03_providers.py` contract corpus; existing Gmail OAuth suites. |
| REAL USER VERIFIED | Google path historically partial; MS/IMAP live accounts **PENDING**. |
| TARGET | User-selected: Gmail **or** Outlook/M365 **or** IMAP — **no auto-fallback**. |
| KEEP | Readonly-first; draft-only send gates; association review; zero false confident link gates. |
| CHANGE | Live MS/IMAP acceptance; generalize DB `gmail_id` naming (alias kept). |
| REMOVE | Silent provider hopping (**forbidden**). |
| OPEN BLOCKER | Google OAuth production URLs/website; MS client ID for live. |
| STATUS | **PARTIAL** (architecture **DONE**; live MS/IMAP acceptance pending) |

### 6. Calendar / interview scheduling

| Field | Content |
|-------|---------|
| CURRENT IMPLEMENTATION | Explicit `calendar_provider` (none/google_calendar/microsoft_graph/generic_caldav). Google FreeBusy + write gate; MS Graph + CalDAV adapters; iCloud as CalDAV preset. Independent of mail provider. |
| CURRENT TEST EVIDENCE | NEXT-03 busy/create contract tests across adapters; lifecycle calendar matrix. |
| REAL USER VERIFIED | **None** for live Google/MS/CalDAV write. |
| TARGET | User-selected Google / Microsoft / CalDAV; no auto-fallback; duplicate event gate remains. |
| KEEP | Draft/approve gates; timezone engine; idempotent write keys. |
| CHANGE | Complete live write transports; production MS app registration. |
| REMOVE | — |
| OPEN BLOCKER | Live OAuth calendar write UX. |
| STATUS | **PARTIAL** (architecture **DONE**; live acceptance pending) |

### 7. Application lifecycle / inbox UX

| Field | Content |
|-------|---------|
| CURRENT IMPLEMENTATION | Event-sourced cases; Postfach V2 contextual actions; dry-run apply. |
| CURRENT TEST EVIDENCE | Lifecycle factory (#33), association corpora, V2 UI tests (#45). |
| REAL USER VERIFIED | Limited; contextual interview button rules engineered but not EXE-black-box proven on this agent. |
| TARGET | Same safety gates; visible UI == domain state. |
| KEEP | Zero false rejection/offer/association; draft-only send. |
| CHANGE | Stronger black-box EXE proof (NEXT). |
| REMOVE | Debug telemetry in normal UI (addressed in polish PRs). |
| OPEN BLOCKER | Real Windows black-box EXE acceptance still absent. |
| STATUS | **PARTIAL** |

### 8. V2 Desktop UI

| Field | Content |
|-------|---------|
| CURRENT IMPLEMENTATION | Nav Übersicht/Jobs/Bewerbungen/Postfach/Profil; design tokens; polish on #45. |
| CURRENT TEST EVIDENCE | pytest-qt structural tests; CI + Windows smoke. |
| REAL USER VERIFIED | Human visual review requested; not fully closed. |
| TARGET | Demo fidelity + contextual actions; accessibility IDs for automation. |
| KEEP | V2 IA; dry-run; German UX. |
| CHANGE | Stable `kk.*` automation ids where missing; EXE black-box suite. |
| REMOVE | Residual “Weitere Aktionen” dumping grounds if any remain. |
| OPEN BLOCKER | Demo vs production visual parity ongoing. |
| STATUS | **PARTIAL** / approaching **DONE** for shell |

### 9. Accessibility

| Field | Content |
|-------|---------|
| CURRENT IMPLEMENTATION | Focus/names/DPI/high-contrast engineering (#44). **No WCAG/BFSG conformity claim.** |
| CURRENT TEST EVIDENCE | `tests/test_a11y_*.py`; CI. |
| REAL USER VERIFIED | Screen-reader smoke checklist documented, not proven. |
| TARGET | Automatable UIA names; legal review separate. |
| KEEP | Engineering helpers. |
| CHANGE | Expand automation ids for pywinauto. |
| REMOVE | — |
| OPEN BLOCKER | Legal BFSG applicability **UNSPECIFIED**. |
| STATUS | **PARTIAL** |

### 10. Privacy / security

| Field | Content |
|-------|---------|
| CURRENT IMPLEMENTATION | Keyring tokens; export/delete lifecycle; injection boundaries; CI privacy_scan + security job. |
| CURRENT TEST EVIDENCE | Strong CI. |
| REAL USER VERIFIED | Unknown for counsel Art.6 / DPIA. |
| TARGET | Keep fail-closed; no PII in fixtures. |
| KEEP | Almost all of PR40–42 engineering. |
| CHANGE | Production OAuth needs real privacy policy URL (website). |
| REMOVE | — |
| OPEN BLOCKER | Website / legal pages absent. |
| STATUS | **PARTIAL** (engineering **DONE**-ish; commercial legal **OPEN**) |

### 11. Mobile companion

| Field | Content |
|-------|---------|
| CURRENT IMPLEMENTATION | Flutter/Drift local MVP; contracts; sync transport **UNSPECIFIED**. |
| CURRENT TEST EVIDENCE | Mobile CI analyze/test. |
| REAL USER VERIFIED | **None** (no store build evidence). |
| TARGET | Explicit sync decision before Gmail on mobile; calendar write blocked until privacy/transport. |
| KEEP | Local-first MVP; capability honesty in docs. |
| CHANGE | Sync architecture decision (NEXT). |
| REMOVE | Premature cloud push claims. |
| OPEN BLOCKER | Sync transport unspecified. |
| STATUS | **PARTIAL** / sync **NOT_IMPLEMENTED** |

### 12. Packaging / Windows smoke

| Field | Content |
|-------|---------|
| CURRENT IMPLEMENTATION | PyInstaller onefile `Karrierekrake.exe`; content allowlist; Windows Smoke + Build Windows workflows. |
| CURRENT TEST EVIDENCE | **CI Windows Smoke green** on main HEAD. |
| REAL USER VERIFIED | Unknown SmartScreen/install UX. |
| TARGET | Black-box pywinauto acceptance against packaged EXE (NEXT). |
| KEEP | Isolated LOCALAPPDATA smoke; content gate. |
| CHANGE | Add system_user black-box job when Windows runner/agent available. |
| REMOVE | — |
| OPEN BLOCKER | No self-hosted Windows worker attached to cloud agent for interactive UIA at audit time. |
| STATUS | **PARTIAL** (smoke **DONE**; human EXE acceptance **NOT_IMPLEMENTED**) |

### 13. E2E / chaos megapass

| Field | Content |
|-------|---------|
| CURRENT IMPLEMENTATION | Lifecycle E2E (#33) + **synthetic offline product E2E / chaos** suite on main via **#46** (`tests/e2e/*`, FakeGmail/calendar, offscreen UI). Report: `docs/e2e/full-product-e2e-report.md`. |
| CURRENT TEST EVIDENCE | **SYNTHETIC E2E REGRESSION: DONE / PASS** (fixture / fake providers / dry-run). CI unit + Windows smoke green on merge SHA. |
| REAL USER VERIFIED | **REAL WINDOWS BLACK-BOX USER ACCEPTANCE: NOT DONE.** **REAL EXTERNAL PROVIDER ACCEPTANCE: NOT DONE.** |
| TARGET | Keep synthetic regression green; add real Windows EXE black-box + real provider acceptance (NEXT). |
| KEEP | Lifecycle gates; synthetic megapass; evidence classification that forbids “OVERALL PRODUCT E2E PASS”. |
| CHANGE | Add EXE/UIA black-box layer; real Gmail/Calendar/Maps acceptance when providers exist. |
| REMOVE | Any claim that synthetic PASS equals real product acceptance. |
| OPEN BLOCKER | Linux cloud ≠ Windows UIA; no real Google/MS accounts in CI. |
| STATUS | Synthetic **DONE / PASS** (reclassified label); real Windows black-box harness **ADDED (NEXT-06)** but live EXE run **NOT DONE** on Linux agents → overall product acceptance still **PARTIAL** |

### 14. Commerce / payments

| Field | Content |
|-------|---------|
| CURRENT IMPLEMENTATION | **None**. |
| CURRENT TEST EVIDENCE | N/A |
| REAL USER VERIFIED | N/A |
| TARGET | **Exactly one** commercial provider after legal/tax decision. |
| KEEP | — |
| CHANGE | Implement one provider when decided. |
| REMOVE | Any multi-provider runtime waterfall. |
| OPEN BLOCKER | Pricing/tax/legal decision. |
| STATUS | **NOT_IMPLEMENTED** |

### 15. Website

| Field | Content |
|-------|---------|
| CURRENT IMPLEMENTATION | **None** (no website tree). |
| CURRENT TEST EVIDENCE | N/A |
| REAL USER VERIFIED | N/A |
| TARGET | Homepage + privacy policy URLs for Google OAuth production. |
| KEEP | — |
| CHANGE | Build/publish site (NEXT). |
| REMOVE | — |
| OPEN BLOCKER | Blocks production OAuth verification. |
| STATUS | **NOT_IMPLEMENTED** |

### 16. Licensing

| Field | Content |
|-------|---------|
| CURRENT IMPLEMENTATION | GPL-3.0 + NOTICE; model/dep reuse audits. |
| CURRENT TEST EVIDENCE | Docs/audits. |
| REAL USER VERIFIED | N/A |
| TARGET | Keep SPDX honesty; model licenses reviewed before bundling Phi weights. |
| KEEP | LICENSE/NOTICE discipline. |
| CHANGE | Re-audit when Google Maps / Phi redistribution lands. |
| REMOVE | — |
| OPEN BLOCKER | GGUF redistribution + Maps ToS. |
| STATUS | **PARTIAL** |

### 17. Release infrastructure

| Field | Content |
|-------|---------|
| CURRENT IMPLEMENTATION | GitHub Actions CI, Windows Smoke, Build Windows, Mobile CI, Live Sources (manual). |
| CURRENT TEST EVIDENCE | Main HEAD CI+Smoke green; Live Sources recently **failed** (manual). |
| REAL USER VERIFIED | N/A |
| TARGET | Keep; add black-box acceptance artifacts. |
| KEEP | Privacy/security gates. |
| CHANGE | Wire NEXT acceptance reports. |
| REMOVE | — |
| OPEN BLOCKER | Live sources instability. |
| STATUS | **PARTIAL** |

---

## C. Stale documentation (explicit)

These documents (and similar shootout leftovers) must **not** be read as current architecture without cross-check against code + `canonical-product-decisions.md`:

| Doc | Issue | Tag |
|------|-------|-----|
| `docs/guenther-model-tournament.md` | Claims production still Qwen; two-tier “not implemented” outdated | **STALE_DOCUMENTATION** |
| `docs/guenther-final-model-shootout.md` | “Production default Qwen unchanged” | **STALE_DOCUMENTATION** |
| `docs/guenther-grounding-repair-report.md` | Same | **STALE_DOCUMENTATION** |
| `docs/guenther-writing-quality-final-report.md` | Same | **STALE_DOCUMENTATION** |
| `docs/guenther-final-hardening-report.md` | Same | **STALE_DOCUMENTATION** |
| `docs/guenther-hardware-tiers.md` | Table rows still list Qwen Autopick for STANDARD/POWER | **STALE_DOCUMENTATION** |
| `docs/guenther-model-candidates.md` | Autopick targets Qwen | **STALE_DOCUMENTATION** |
| `docs/dach-cross-border.md` | Accurate for **current Haversine** code; **conflicts with NEW geo target** (Google-only) | Current-code OK / target **STALE** relative to NEXT decisions |
| Design SUPER_PROMPT distance notes | Partially historical | Review before citing |

**Small NEXT-01 fix applied:** banner comments added to the worst Guenther stale reports (see commit). Full Guenther/Qwen removal is **not** in NEXT-01 scope.

---

## D. Open PRs / WIP note

| Item | Note |
|------|------|
| GitHub **#46** | **MERGED** onto main (`8c3ea87`). Synthetic E2E **PASS**; SearchIntent geo preserve included. Does **not** prove real Windows / external acceptance. |
| GitHub **#47** | NEXT-01 reconciliation (this branch) — sync against post-#46 main |
| Local WIP stash `wip-blackbox-route-cv` | Incomplete OSRM/CV/UIA work on another branch — **not** main; superseded by new geo decision (**Google**, not OSRM) |

---

## E. Recommended NEXT queue (documentation only here)

| ID | Intent |
|----|--------|
| **NEXT-01** | This reconciliation + canonical decisions (**this doc**) |
| **NEXT-02** | Enforce ONE Phi model + CV Phi pipeline (**this package / PR**) |
| **NEXT-03** | Google Maps Geocoding + Routes as sole commute authority |
| **NEXT-04** | CV extract/layout fix + local black-box EXE acceptance |
| **NEXT-03** | Mail/Calendar multi-provider (explicit choice, no fallback) — **this package** |
| **NEXT-04** | Real integration acceptance via packaged EXE + API probe before Verbunden |
| **NEXT-07** | Single commerce provider decision + implementation |
| **NEXT-08** | Mobile sync transport decision |

---

## F. Short verdict

Karrierekrake on **main** (`8c3ea87`) is a substantial desktop product with strong CI/Windows smoke, lifecycle/mail safety engineering, and a **merged synthetic offline E2E regression (DONE / PASS via #46)** — but:

1. **AI** still allows Qwen fallback/picker → violates new ONE-MODEL rule.  
2. **Geo** is still Haversine/Nominatim/pgeocode → violates new ONE-GEO (Google) rule.  
3. **CV import** remains a **real-world** risk despite green corpora.  
4. **Payments / website / multi-mail-calendar** largely **NOT_IMPLEMENTED**.  
5. **Real Windows black-box** and **real external provider** acceptance are **NOT DONE** — do **not** restore “OVERALL PRODUCT E2E PASS”.  
6. Documentation debt is real; prefer this file + canonical decisions over tournament PDFs.

**STOP after NEXT-01** — no large feature rewrites in this package.
