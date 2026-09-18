# Günther die Krake — Phase 0: Current Karrierekrake Architecture Audit

**Date:** 2026-09-15  
**Base `origin/main` SHA:** `8c1e81c9653789251e2500b249a9abbf3d7d3175`  
**Lifecycle verification:** PR **#17** merged (`e5096cb`); CI-confirm PR **#18** merged (`8c1e81c`).  
**Branch for this megapass:** `cursor/guenther-local-ai-megapass-d85b` (created from current `origin/main` — not reused).

**Rule:** No Günther product implementation until this audit is committed.  
**Primary rule going forward:** Günther may **think**. Karrierekrake **decides**. The **user** authorizes consequential actions.

---

## 1. Lifecycle-in-main gate (BLOCKER check)

| Check | Result |
|-------|--------|
| `origin/main` contains merge of PR #17 | **YES** — `e5096cb Merge pull request #17` |
| ApplicationCase / lifecycle modules present | **YES** — `core/lifecycle.py`, `core/case_pipeline.py`, `core/known_jobs.py` |
| Email classify / associate / Gmail / calendar | **YES** — `integrations/email_*.py`, `gmail_*.py`, `calendar_availability.py`, `ics_export.py`, `reply_draft.py`, `interview_prep.py`, `followup.py` |
| Desktop lifecycle UI + settings | **YES** — `desktop/pages/lifecycle.py`, settings keys on `SettingsConfig` |
| Tests + fictional corpus | **YES** — `tests/test_post_application_lifecycle.py`, `tests/fixtures/fictional_emails/` |
| Known-job search suppression | **YES** — `core/known_jobs.py` + manager `refuse_reapply` |

**Verdict:** Proceed. Do **not** reimplement lifecycle/quality-pass features.

---

## 2. Product identity & packaging

| Item | Location / note |
|------|-----------------|
| Brand | Karrierekrake (GPL-3.0); product name is Karrierekrake |
| Desktop entry | `python -m desktop.app` → PySide6; EXE `Karrierekrake.exe` |
| Data root | `%LOCALAPPDATA%\Karrierekrake` via `desktop/paths.py` (`ensure_app_dirs`) |
| Spec | `packaging/Karrierekrake.spec` — onefile, no bundled Chromium; Chromium on-demand in AppData |
| NOTICE / licenses | GPL-3.0 app + MIT/Apache adapted third parties in `NOTICE` |
| Existing AI | **None required.** README already: „kein Pflicht-KI-Abo · Daten bleiben auf Ihrem PC“. Matcher/CV/email are deterministic local heuristics. |

---

## 3. Layer map (where Günther must plug in — not replace)

```
┌─────────────────────────────────────────────────────────────┐
│  desktop/  (PySide6 UI, workers QThread, settings, lifecycle)│
├─────────────────────────────────────────────────────────────┤
│  app/main.py  pipeline (search → filter → match → apply)     │
├──────────────┬──────────────────┬───────────────────────────┤
│ search/      │ apply/           │ integrations/ (lifecycle) │
│ JobSpy/BA/…  │ manager+ATS      │ Gmail, classify, assoc,   │
│              │ preview+submit   │ calendar, drafts, prep    │
├──────────────┴──────────────────┴───────────────────────────┤
│  core/  config, DB, models, matcher, cv_parser, lifecycle,  │
│         known_jobs, case_pipeline, cover_letter, documents  │
└─────────────────────────────────────────────────────────────┘
```

**Günther placement (planned):** new top-level package `guenther/` (or `ai/`) that:

1. Offers optional structured suggestions on top of existing deterministic outputs.
2. Never owns submit / send / calendar finalize / CAPTCHA / status writes without going through existing Karrierekrake gates.
3. Is off by default; Auto model selection; fail-closed when unavailable.

---

## 4. Safety / apply architecture (must remain authoritative)

| Mechanism | Module | Günther constraint |
|-----------|--------|-------------------|
| Fail-closed submit gate (snapshot at manager create) | `apply/manager.py` `_submit_gate_open` / `_submit_allowed` | **No bypass.** LLM cannot open gate. |
| Dry-run / `_maybe_submit` | `apply/base.py` | Suggestions only; never click submit. |
| Operating modes | `OperatingMode` in `core/models.py` | Günther does not change mode. |
| CAPTCHA / 2FA / needs_review stop | apply path + `JobStatus.CAPTCHA` | No CAPTCHA solve / bypass. |
| CV role = `cv` required | `ApplicationManager._resolve_cv_path` + `core/documents.py` | May help parse CV; cannot invent path/role. |
| Never demote APPLIED | apply/manager + lifecycle `STATUS_RANK` | Günther must not unilaterally overwrite APPLIED/REJECTED. |
| Known-case re-apply refuse | `core/known_jobs.refuse_reapply` | Suggestions cannot force re-apply. |
| Preview gate | `apply/preview.py` | Preview remains human-facing truth. |

---

## 5. ApplicationCase / lifecycle (PR #17) — integration surfaces

| Concern | Existing API | Günther role |
|---------|--------------|--------------|
| Case model + rank | `core/lifecycle.py` `ApplicationCase`, `STATUS_RANK`, `TERMINAL_STATUSES` | May propose next status; **case pipeline / DB writes decide** with rank + confidence. |
| Email → classify → associate → events | `core/case_pipeline.process_parsed_email` | Optional second-opinion classify/associate **behind** regex primary; ambiguous stays review; never silent HIGH_CONFIDENCE on weak signal. |
| Classify (DE+EN phrases) | `integrations/email_classify.py` | Deterministic **first**; LLM only assist with validated schema. |
| Associate (threshold 0.90, recruiter ambiguity) | `integrations/email_associate.py` | LLM association must fail closed below threshold; no silent link. |
| Reply drafts | `integrations/reply_draft.py` | LLM may improve draft text; `email_draft_only` + approval gate unchanged. |
| Interview prep | `integrations/interview_prep.py` from matcher evidence | Enrich talking points **only** from evidence/profile anchors; no invented facts. |
| Follow-up / ghosted | `integrations/followup.py` | Suggest-only; never auto-send. |
| Calendar / ICS | `calendar_availability.py`, `ics_export.py` | Availability hints only; user finalizes. |
| UI | `desktop/pages/lifecycle.py` | Surface Günther suggestions with clear „Vorschlag“ labeling. |

**Do not rebuild:** parallel ApplicationCase store, parallel Gmail sync, parallel matcher evidence taxonomy, or company-wide blacklist.

---

## 6. Matching, CV, documents, writing (deterministic baseline)

| Module | Behavior today | Günther enhancement (optional) |
|--------|----------------|--------------------------------|
| `core/matcher.py` | Score 0–100; evidence DIRECT / RELATED / NOT_SUPPORTED; no LLM | Soft requirement extraction / gap narrative **validated** against evidence classes; cannot flip NOT_SUPPORTED → DIRECT without profile tokens. |
| `core/cv_parser.py` | Heuristic DE/EN section parse; never invents quals | Assist messy CVs; claim guards; manual profile data wins. |
| `core/cover_letter.py` | Template + relevance-ranked experience/skills | Optional rewrite; anchors must appear in profile/job; no invented employers. |
| `core/documents.py` | CV role normalization | Untouched authority for which file is CV. |
| `core/hard_filter.py` / `salary.py` / `deduplicator.py` | Deterministic filters | Günther must not weaken hard excludes. |

---

## 7. Config & settings hooks

`SettingsConfig` (`core/config.py`) already has lifecycle fields (`preferred_contact`, Gmail, draft-only, etc.). **Missing for Günther:**

- `guenther_enabled: bool = False`
- `guenther_model: str = "auto"` (Auto / Light / Standard …)
- Paths for models under AppData (not in git)
- No cloud endpoint settings (by design — reject if proposed)

UI: extend `desktop/pages/settings.py` with On/Off + Auto model; German user strings; no ML jargon.

---

## 8. Desktop workers / non-blocking inference

| Existing | Implication for Günther |
|----------|-------------------------|
| `desktop/workers.py` `PipelineWorker` on `QThread` + cancel/pause | Inference must be similarly non-blocking; cancelable; honest progress. |
| Lazy imports (playwright/jobspy) | Heavy llama runtime must be lazy; EXE must start without model loaded. |
| Shutdown / single-instance | Unload model on idle when RAM tight; respect shutdown. |

---

## 9. Data / privacy / logging

| Area | Current | Günther rule |
|------|---------|--------------|
| AppData dirs | config, data, logs, cvs, cache, cover_letters, browsers | Add `models/` (or `guenther/models`) under AppData only |
| Logging | `core/logging.py` / `karrierekrake` logger | **No PII** (CV text, email bodies, tokens) in logs; log categories/error codes only |
| Privacy scan | `scripts/privacy_scan.py` | Fixtures fictional; allowlist updates if needed |
| Cloud AI | None | **No** OpenAI/Anthropic/paid APIs; **no** cloud fallback |

---

## 10. Tests & fixtures to extend (not replace)

| Asset | Use for Günther |
|-------|-----------------|
| `tests/fixtures/fictional_emails/corpus.json` | Extend / parallel AI corpus for classify+associate |
| `tests/fixtures/cv_corpus/` | CV intelligence golden cases |
| `tests/test_post_application_lifecycle.py` | Safety regressions must keep passing |
| Adversarial / privacy / quality suites | Add hostile prompt-injection + invented-fact tests |
| Marker `-m "not network"` | Günther unit tests must be offline |

---

## 11. Gap analysis — what Günther adds vs what already exists

| Capability | Exists (deterministic) | Günther (optional local LLM) |
|------------|------------------------|------------------------------|
| CV structured extract | Yes (`cv_parser`) | Assist low-quality / non-standard CVs |
| Job requirement extract | Partial (matcher keywords) | Structured requirements list |
| Evidence / claim support | Yes (DIRECT/RELATED/NOT_SUPPORTED) | Narrative + soft checks; never invent |
| Email classify | Yes (regex DE+EN) | Ambiguous edge assist |
| Email↔case associate | Yes (0.90 + recruiter guard) | Second opinion only; fail closed |
| Cover / reply writing | Templates | Constrained rewrite |
| Interview prep | Evidence wrap | Question list from evidence only |
| Model download / runtime | **Missing** | Model manager + LocalAIProvider |
| UX brand „Günther die Krake“ | **Missing** | Settings + light UI copy |

---

## 12. Explicit non-goals (from mission + this audit)

- Submit applications, send employer email, accept interviews, finalize calendar
- Bypass CAPTCHA / 2FA / submit gates / ApplicationCase safety
- Invent candidate facts or silent ambiguous email association
- Unilateral APPLIED/REJECTED overwrite
- Required cloud AI; shipping GGUF weights in git
- Coupling forever to a single runtime (Ollama-only) — abstract `LocalAIProvider`
- Reimplementing PR #17 lifecycle or quality-pass matcher/CV work

---

## 13. Implementation order reminder (post-audit)

Phases 1–2 docs (reuse/license + model candidates) → benchmark corpus/metrics → provider + contracts → intelligence modules integrated with lifecycle → UX/model manager/privacy/inference/fallbacks/injection → tests/packaging/docs → hostile review.

**Reuse before build** applies to llama.cpp wrappers, constrained JSON, Pydantic (already a runtime dep), and any MIT/Apache patterns — code license ≠ model license.
