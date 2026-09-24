# Acceptance + Kill-or-Ship status (PR #62)

**Kill-or-Ship:** #62 only ships if the full application flow on the **real Intel Core i3 / 8 GB Windows laptop** stays within the RAM limit, is stable, and has acceptable quality and wait time. **Every unmeasured gate stays open.**  
**#64 = UI-only** — not mixed into this PR.

## A) Target device Peak — **OPEN / FAIL (unmeasured on laptop)**

| | |
|--|--|
| Required host | Real i3 (11th gen) / **exactly 8 GB** Windows laptop |
| Agent-VM Peak | **NOT ship evidence** (prior ~2.6 GB import-only / ~8.5 GB combined) |
| Laptop Peak | **Not measured in this environment** |
| Protocol | `docs/project/DOCPICK_TARGET_DEVICE_MEASUREMENT_CHECKLIST.md` + `scripts/run_docpick_target_device_peak_windows.ps1` |

## B) Process-group Peak — **informational on Agent-VM only**

| Host | Process-group Peak | Ship evidence? |
|------|--------------------|----------------|
| Agent-VM (llama `n_ctx=2048` loaded) | **~5.4 GB** LLM alone | **No** |
| Agent-VM (prior import+LLM gate) | **8.50 GB** | **No** |
| Real i3/8GB Win laptop | **unmeasured** | Required for ship |

Also required on laptop: free RAM, crashes, import/parse duration.

## C) Hard fail (crash / OOM / UI freeze / unusable) — **OPEN**

Cannot certify on Agent-VM. Code raises `peak_rss_exceeded` / `timeout` / `empty_cv` / `unreadable_cv` (no silent hang), but **laptop stability is unmeasured**.

## D) Prior gates

| Gate | Status |
|------|--------|
| Peak ≤3.3 GB hard (constant 3300) | Code **PASS**; ship Peak **OPEN** until laptop |
| Fail-cases empty/corrupt/timeout/OOM | **PASS** (demo + unit) |
| Matching-Contract + Diff | **PASS** (v1, no drift) |
| Extract + cover letter under limit | **BLOCKED** (needs Peak ≤3.3 on target) |

## E) E2E Profile → Matching → Cover letter — **OPEN**

Must be demonstrated **under** process-group ≤3.3 GB on the laptop; evaluate extract / matching / cover letter **separately**. Not run as ship evidence here.

## F) #64 UI-only — **honored** (no UI QA mixed into #62 Peak work)

---

## What we can measure now vs laptop

| Now (Agent-VM / CI) | Requires physical laptop |
|---------------------|---------------------------|
| Code hard-fail Peak/timeout/empty/corrupt | Process-group Peak on 8 GB Win |
| Contract freeze + unit tests | Free RAM / crash / UI freeze |
| Informational Agent-VM RSS (not ship) | Import duration on i3 |
| Quality post-analysis (not Peak ship) | E2E Profile→Matching→Cover under limit |

## Go / No-Go (Kill-or-Ship)

**NO SHIP / NO-GO.**  

Reasons: (A) target-device Peak **unmeasured** → gate stays **OPEN**; Agent-VM process-group already **~5.4–8.5 GB ≫ 3.3 GB** (abort signal, still not a substitute for laptop proof). Recommend abort of on-device Qwen3.5-4B for i3/8 GB unless the laptop run proves ≤3.3 GB process-group with stable E2E.
