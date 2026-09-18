# Günther die Krake — Final Report

**Feature branch:** `cursor/guenther-local-ai-megapass-d85b`  
**PR:** https://github.com/deadfrogface/Karrierekrake/pull/19  
**Base `origin/main`:** `8c1e81c9653789251e2500b249a9abbf3d7d3175`  
**Verified green head:** `12f6aa2f21ef216061e7e43c351d110c75d518c4`  
**Lifecycle gate:** PR #17 + #18 on main — proceeded.  
**Agent must not merge** — human merge only.

## CI / Windows Smoke / EXE @ `12f6aa2`

| Check | Workflow | Result | Run |
|-------|----------|--------|-----|
| unit-tests | CI | **PASS** | `34984746297` |
| privacy | CI | **PASS** | `34984746297` |
| cv-regression | CI | **PASS** | `34984746297` |
| database-migration-tests | CI | **PASS** | `34984746297` |
| static-smoke | CI | **PASS** | `34984746297` |
| qt-smoke | Windows Smoke | **PASS** | `34984746339` |
| build-and-exe-smoke | Windows Smoke | **PASS** | `34984746339` |

**7/7 PASS** on tip `12f6aa2` (includes Windows Smoke qt-smoke + build-and-exe-smoke).

## Acceptance gates (held-out REAL GGUF, qwen3-1.7b)

| Gate | Result |
|------|--------|
| Prompt injection successes | **0** |
| False confident associations | **0** |
| False rejection consequential | **0** |
| False offer consequential | **0** |
| Unsupported claims surviving validation | **0** |
| Direct consequential Günther actions | **0** |
| Malformed output → unsafe | **0** |
| Schema unsafe | **0** |
| Held-out cases / pass / fail | **109 / 108 / 1** |
| Non-safety error rate | **~0.9%** (`ho_em_ats_generic` wrong_category) |
| Model / runtime | qwen3-1.7b / ~829 s / ~5.3 GB RSS |
| CI / Windows Smoke / EXE Smoke | **7/7 PASS** @ `12f6aa2` |

## Real GGUF inference (RAN — not simulated)

| Item | Result |
|------|--------|
| Status | **RAN** held-out via `benchmark/run_held_out_eval.py --live` |
| Corpus | `benchmark/held_out/` (≥100 tasks; 32+ injection cases) |
| Winner | **`qwen3-1.7b`** (smallest meeting safety) |
| qwen3-4b | Prior live: injection→offer failure — **not** Autopick default |
| Artifacts | `benchmark/results_live_gguf.json`, `results_live_summary.json` |
| GATED | **No** for 1.7b after agreement harden |

Pins: LIGHT + STANDARD URL+SHA256 in `guenther/model_manager.py`. Phi-4-mini deferred (REVIEW REQUIRED) — not required because 1.7b met safety gates.

Deterministic Karrierekrake gates remain authoritative for consequential actions.

## Hostile / integration

| Suite | Result |
|-------|--------|
| `tests/test_guenther_local_ai.py` + lifecycle | **PASS** (41) |
| Privacy scan | **OK** (CI @ `12f6aa2`) |
| Email/assoc harden | Deterministic + validation asymmetric fail-closed |

## Mission checklist (abbrev.)

| Item | Status |
|------|--------|
| Runtime | `LocalAIProvider` (llama_cpp / ollama-dev / heuristic / null) |
| Models | LIGHT+STANDARD pinned; no weights in git |
| Winner | Live **`qwen3-1.7b`** |
| Safety | No submit/send/finalize; high-impact needs det agreement; claim guards |
| Held-out score | Final from held_out only |
| Windows Smoke / EXE | **PASS** (qt-smoke + build-and-exe-smoke) |
| Docs | This report + `docs/guenther-*.md` |

## MERGE READY: **YES**

For human merge of green tip `12f6aa2` (or successor tip that remains green).  
**Do not auto-merge.** Honest: ~0.9% non-safety category miss — not 100% AI accuracy. All safety counters = 0.

## GÜNTHER STATUS

```
Günther may think; Karrierekrake decides; user authorizes.
Held-out REAL GGUF: injection/false-assoc/false-reject/false-offer = 0.
CI + Windows Smoke + EXE @ 12f6aa2: 7/7 PASS.
MERGE READY YES — agent will not merge.
```
