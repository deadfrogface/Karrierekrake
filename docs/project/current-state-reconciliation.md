# Current-State Reconciliation (NEXT-01)

**Audit date:** 2026-09-21  
**Repository HEAD (main):** `d1ac05e0defb82aeb632705193fc20e862d8fbce`  
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

- Commit: `d1ac05e` — *PR45: V2 UI — Matrix, Design Tokens & App Shell (#45)*
- CI on that SHA: **CI success**, **Windows Smoke success** (2026-09-21)

### Open PRs (at audit time)

| # | Title | State |
|---|-------|-------|
| **46** | Full Product E2E / Chaos Megapass + SearchIntent geo fix | **OPEN** (not on main) |

### Merged GitHub PRs `#19`–`#45` (actual)

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

Earlier merges `#1`–`#18` cover branding, EXE smoke, adversarial gates, post-application lifecycle, etc.

---

## B. System matrix

Columns:

**SYSTEM | CURRENT IMPLEMENTATION | CURRENT TEST EVIDENCE | REAL USER VERIFIED | TARGET ARCHITECTURE | KEEP | CHANGE | REMOVE | OPEN BLOCKER | STATUS**

### 1. Guenther / local AI

| Field | Content |
|-------|---------|
| CURRENT IMPLEMENTATION | Catalog: `phi4-mini` (primary), `qwen3-1.7b` (light_fallback), `qwen3-4b` (legacy). One GGUF loaded at a time. Settings: enable + Auto/Phi/Qwen picker. LIGHT hardware can force Qwen. Heuristic provider when no LLM. Deterministic validators already authority over LLM output. |
| CURRENT TEST EVIDENCE | CI unit/Guenther suites; tournament/shootout reports (partially stale). No GGUF in EXE. |
| REAL USER VERIFIED | **None** for Phi-only production behavior. |
| TARGET ARCHITECTURE | **ONE Phi model only**; no Qwen; no user picker; unavailable → manual path. |
| KEEP | Deterministic validators; offline-first; fail-closed (no cloud LLM); quality/grounding gates. |
| CHANGE | Freeze production to Phi only; Settings remove model choice; hardware path must not switch LLM. |
| REMOVE | Qwen catalog roles as production/fallback; silent heuristic-as-LLM substitute if it masks “AI unavailable”. |
| OPEN BLOCKER | Packaging still does not ship weights; download/consent UX incomplete for commercial. |
| STATUS | **PARTIAL** + **STALE_DOCUMENTATION** (many Guenther reports still say “production default Qwen”). |

### 2. Geo / commute distance

| Field | Content |
|-------|---------|
| CURRENT IMPLEMENTATION | **Haversine** authoritative for `Job.distance_km`. Coords: **pgeocode** + **Nominatim**. No Google Routes / Matrix. No OSRM on main. |
| CURRENT TEST EVIDENCE | `tests/test_dach_cross_border.py`, `tests/test_location.py` (fixture). CI green. |
| REAL USER VERIFIED | **None** for Google road km. Known product risk: air-line ≠ road. |
| TARGET ARCHITECTURE | **Google Geocoding + Google Routes/Route Matrix only**; UNKNOWN if no route; never Luftlinie as Fahrt. |
| KEEP | UNKNOWN semantics; remote skip; DACH country intent rules (separate from routing). |
| CHANGE | Replace Nominatim/pgeocode/Haversine authority with Google Maps Platform. |
| REMOVE | Production reliance on Nominatim, pgeocode, Haversine-as-commute. |
| OPEN BLOCKER | Google billing/API keys, quotas, privacy notice, offline behavior policy. |
| STATUS | **PARTIAL** (geo exists) vs target → **CHANGE**; docs `dach-cross-border.md` accurate for *current* code, stale vs *target*. |

### 3. SearchIntent / job search / ranking

| Field | Content |
|-------|---------|
| CURRENT IMPLEMENTATION | SearchIntent model + deterministic filter/rank; pipeline dry-run default; sources BA/Indeed etc. |
| CURRENT TEST EVIDENCE | Intent corpora, hard_filter, matcher, CI. |
| REAL USER VERIFIED | Partial historical EXE defects fixed in early PRs; ongoing UX polish via #45. |
| TARGET | Keep deterministic authority; distance filter must consume Google route km when NEXT geo lands. |
| KEEP | SearchIntent ≠ profile; dry-run; cancel/pause. |
| CHANGE | Wire radius to route provider once Google geo ships. |
| REMOVE | — |
| OPEN BLOCKER | Live source flakiness (manual Live Sources workflow has failures). |
| STATUS | **PARTIAL** |

### 4. CV import

| Field | Content |
|-------|---------|
| CURRENT IMPLEMENTATION | `extract_text` (pypdf paragraphs; python-docx **paragraphs only** on main) → section split → parse → `CvImportDialog` → YAML persist. |
| CURRENT TEST EVIDENCE | `cv_corpus` 10 PDFs green; **no DOCX table fixtures on main**. |
| REAL USER VERIFIED | **BROKEN_REAL_WORLD** reports: Berufserfahrung/Ausbildung empty on real layouts (two-column/tables). Unit green ≠ accepted. |
| TARGET | Real EXE import path must show correct sections after apply+restart; layout-capable extract. |
| KEEP | Merge/replace semantics; no hallucinated profile; parser limits. |
| CHANGE | Extraction for tables/columns; black-box EXE acceptance; private local CV dir (gitignored). |
| REMOVE | Trust in “corpus green ⇒ product ready”. |
| OPEN BLOCKER | No Windows black-box pywinauto gate on main; private CVs must stay local. |
| STATUS | **BROKEN_REAL_WORLD** / **PARTIAL** |

### 5. Gmail / mail

| Field | Content |
|-------|---------|
| CURRENT IMPLEMENTATION | Google Gmail **readonly** OAuth + robust sync; classify/associate/lifecycle local. |
| CURRENT TEST EVIDENCE | FakeGmail unit/E2E lifecycle corpora; CI. |
| REAL USER VERIFIED | **None** in CI (no real Google accounts). |
| TARGET | User-selected: Gmail **or** Outlook/M365 **or** IMAP — **no auto-fallback**. |
| KEEP | Readonly-first; draft-only send gates; association review; zero false confident link gates. |
| CHANGE | Add Microsoft + IMAP as explicit choices. |
| REMOVE | Any future silent provider hopping. |
| OPEN BLOCKER | Google OAuth production URLs/website still required for commercial consent. |
| STATUS | **PARTIAL** (Gmail); Outlook/IMAP **NOT_IMPLEMENTED** |

### 6. Calendar / interview scheduling

| Field | Content |
|-------|---------|
| CURRENT IMPLEMENTATION | Scheduling engine + Google FreeBusy client + write **gate**; ICS; in-memory transport in tests. Google `events.insert` transport incomplete vs scopes. |
| CURRENT TEST EVIDENCE | Calendar engine + lifecycle E2E matrix; CI. |
| REAL USER VERIFIED | **None** for live Google write. |
| TARGET | User-selected Google / Microsoft / CalDAV; no auto-fallback; duplicate event gate remains. |
| KEEP | Draft/approve gates; timezone engine; idempotent write keys. |
| CHANGE | Complete write transports; add MS + CalDAV. |
| REMOVE | — |
| OPEN BLOCKER | Live OAuth calendar write UX. |
| STATUS | **PARTIAL**; MS/CalDAV **NOT_IMPLEMENTED** |

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
| OPEN BLOCKER | #46 E2E megapass not merged. |
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
| CURRENT IMPLEMENTATION | Lifecycle E2E on main (#33). Broader product E2E in **open #46** (not merged). |
| CURRENT TEST EVIDENCE | #33 CI; #46 reported green on its branch. |
| REAL USER VERIFIED | No. |
| TARGET | Offline E2E + Windows black-box. |
| KEEP | Lifecycle gates. |
| CHANGE | Merge/review #46; add EXE layer. |
| REMOVE | — |
| OPEN BLOCKER | #46 unmerged; Linux cloud ≠ Windows UIA. |
| STATUS | **PARTIAL** |

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
| GitHub **#46** | Full product E2E megapass — open; CI green on branch; **not** main |
| Local WIP stash `wip-blackbox-route-cv` | Incomplete OSRM/CV/UIA work on another branch — **not** main; superseded by new geo decision (**Google**, not OSRM) |

---

## E. Recommended NEXT queue (documentation only here)

| ID | Intent |
|----|--------|
| **NEXT-01** | This reconciliation + canonical decisions (**this doc**) |
| **NEXT-02** | Enforce ONE Phi model (remove Qwen production paths + Settings picker) |
| **NEXT-03** | Google Maps Geocoding + Routes as sole commute authority |
| **NEXT-04** | CV extract/layout fix + local black-box EXE acceptance |
| **NEXT-05** | Mail/Calendar multi-provider (explicit choice, no fallback) |
| **NEXT-06** | Website + OAuth production URLs |
| **NEXT-07** | Single commerce provider decision + implementation |
| **NEXT-08** | Mobile sync transport decision |

---

## F. Short verdict

Karrierekrake on **main** is a substantial desktop product with strong CI/Windows smoke and deep lifecycle/mail safety engineering — but:

1. **AI** still allows Qwen fallback/picker → violates new ONE-MODEL rule.  
2. **Geo** is still Haversine/Nominatim/pgeocode → violates new ONE-GEO (Google) rule.  
3. **CV import** remains a **real-world** risk despite green corpora.  
4. **Payments / website / multi-mail-calendar** largely **NOT_IMPLEMENTED**.  
5. Documentation debt is real; prefer this file + canonical decisions over tournament PDFs.

**STOP after NEXT-01** — no large feature rewrites in this package.
