# Günther Final Intelligence Architecture

**GÜNTHER FINAL INTELLIGENCE ARCHITECTURE:** in progress (implementation + ablation)  
**PRIMARY MODEL LOCKED:** Phi-4-mini  
**MODEL TOURNAMENT CLOSED:** YES  
**PR #19 MERGED:** NO

## Goal

Turn the best measured local model (Phi-4-mini) into a reliable autonomous application-writing system via a bounded multi-stage pipeline — **not** via another model search.

## Locked model decision

See [ADR: Phi-4-mini primary](adr/guenther-primary-model-phi4-mini.md).

| Role | Model |
|------|-------|
| PRIMARY / RECOMMENDED | `phi4-mini` (Phi-4-mini-instruct Q4_K_M) |
| LIGHT FALLBACK | `qwen3-1.7b` |
| Legacy option | `qwen3-4b` (not recommended) |

Hardware: LIGHT → Qwen fallback; STANDARD/POWER → Phi recommended. Explicit user `guenther_model` preference is preserved.

## Pipeline

```
EVIDENCE → PLAN → [PLAN_REPAIR≤1] → DRAFT → [SAFETY_REPAIR≤1]
         → CRITIQUE → [QUALITY_REVISION≤2] → FINAL SAFETY → FINAL QUALITY → DONE
```

| Bound | Value |
|-------|-------|
| Plan repairs | 1 |
| Safety repairs | 1 |
| Quality revisions | 2 (keep only if ablation shows value) |
| Max model calls | **8** |
| Early exit | YES — stop when safety pass + `ready_as_is` |

Authority order:

1. Deterministic safety validation  
2. Hard requirement validation  
3. Structural validation  
4. Quality readiness  

Critic **never** overrides a deterministic safety block. Safety and quality are separate.

Final states: `READY_AUTOMATIC` | `REVIEW_REQUIRED_QUALITY` | `REVIEW_REQUIRED_SAFETY` | `HARD_REQUIREMENT_NOT_MET` | `GENERATION_FAILED` | `MODEL_UNAVAILABLE`.

No chain-of-thought storage (`cot_stored: false`). User-facing progress uses Günther strings only (e.g. „Günther erstellt einen Bewerbungsplan.“).

## Phase-A forensic (Phase-2 Phi, 100 covers)

Source: `benchmark/guenther_quality_loop_raw/phase2_failure_forensics.json`

| Metric | Value |
|--------|-------|
| Cases audited | 100 / 100 |
| Eligible-safe fail-closed | 14 |
| Not READY_AS_IS | 23 |
| Score &lt; 8 | 14 |
| Repair required / failed | 19 / 14 |

Unnecessary fail-closed root causes (eligible):

- Unsupported credential / claim grounding: **6**
- Unresolved placeholder: **7**
- Empty output / structural: **1**
- All 14 exhausted max-1 safety repair

Not-ready root causes:

- Fail-closed safety/structure: **14**
- Accepted but material edit / score&lt;8: **9**
- Generic writing or weak specificity (overlapping): **15**

**Do not weaken safety gates.** Plan+draft constraints must prevent placeholders and false credentials upstream.

## Ablation (development fixture = Phase-2)

Baseline (OLD / Phase-2 reuse):

| | |
|--|--|
| Automation | 85.11% |
| Unnecessary fail-closed | 14.89% |
| Cover raw | 7.665 |
| Ready-as-is | 76.6% |
| Safety accepted failures | 0 |

Live ablation modes: `old` | `plan_draft` | `critic1` | `full` — see `benchmark/guenther_quality_loop_ablation.json`.

Development targets before new blind: automation ≥95%, ready ≥90%, cover ≥8.0, safety 0.

## Shootout report blindness correction (Phase Y)

Raw chronology confirms:

| Checkpoint | Evidence |
|------------|----------|
| Remained blind through Phase-1 (`sc_*` not executed in Phase-1) | **YES** — Phase-1 raw dirs are `wq_final_blind_covers` / hardening suites only |
| Used for Phase-1 winner selection | **NO** |
| Phase-2 after winner selection | **YES** (`phi4-mini`) |

Any earlier presentation that appeared to mark “Remained blind through Phase-1: False” was a **report wording inconsistency** relative to `new_fixture_blind_status.remained_blind_through_phase1=true` and raw paths. Results numbers were **not** altered. Correction documented here and in `docs/guenther-final-model-shootout.md`.

## Artifacts

- `docs/adr/guenther-primary-model-phi4-mini.md`
- `docs/guenther-final-intelligence-architecture.md` (this file)
- `benchmark/guenther_quality_loop_results.json`
- `benchmark/guenther_quality_loop_ablation.json`
- `benchmark/guenther_quality_loop_raw/`

Historical tournament / grounding / hardening / shootout artifacts preserved.

## Quality / merge ready

QUALITY READY and MERGE READY remain **NO** until new blind confirmation meets release targets (≥99% automation, ≤1% unnecessary fail-closed, ready ≥95%, cover/interview ≥8.0, all safety zeros) **and** human review. Do not merge PR #19 automatically.
