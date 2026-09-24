# Acceptance + Kill-or-Ship status (PR #62)

**Kill-or-Ship:** #62 only ships if the full application flow on the **real Intel Core i3 / 8 GB Windows laptop** stays within the RAM limit, is stable, and has acceptable quality and wait time. **Every unmeasured gate stays open.**  
**#64 = UI-only.** **NO automatic Phi fallback.**

## MEASUREMENT (mandatory)

| Rule | Status |
|------|--------|
| Windows **Job Object** runner (App + Docling + Qwen + ALL import children; no escape) | **Plan ready** — `scripts/run_docpick_job_object_peak_windows.ps1` |
| Hard gate **≤ 3_300_000_000 bytes** (`PeakJobMemoryUsed`) | Code constant set; **ship run NOT executed** |
| Real i3 / 8 GB Win laptop only | **OPEN** (Agent-VM ≠ ship evidence) |

## Current Peak bytes

| Source | Peak bytes | Ship? |
|--------|------------|-------|
| Job Object on target laptop | **unmeasured** | Required |
| Agent-VM combined (import+LLM, /proc sum) | **9_130_123_674** (8707.7 MiB) | **No** |
| Agent-VM LLM-only snapshot | **~5_675_000_000+** (~5.4 GiB) | **No** |
| Gate | **3_300_000_000** | — |

## Kill-path step

**Step 1 pending** — try a smaller local model under the same quality/RAM/runtime gates (no Phi), once laptop Job Object confirms over-limit after optimization (Agent-VM already ≫ gate → prepare Step 1).  
**Not Step 2 yet.** Step-2 wording reserved: *„wird lokales LLM-CV-Parsing auf dieser Hardware gestrichen; der manuelle Profilimport bleibt möglich.“*

See `DOCPICK_KILL_PATH.md`.

## Other gates (D)

| Gate | Status |
|------|--------|
| Fail-cases empty/corrupt/timeout/OOM | **PASS** (code) |
| Matching-Contract + Diff | **PASS** (v1) |
| Extract + cover letter under limit | **BLOCKED** |
| E2E Profile → Matching → Cover | **OPEN** (laptop) |

## Go / No-Go

**NO SHIP / NO-GO.** Job Object Peak on target device unmeasured (OPEN). Informational Agent-VM Peak **9_130_123_674 ≫ 3_300_000_000**.
