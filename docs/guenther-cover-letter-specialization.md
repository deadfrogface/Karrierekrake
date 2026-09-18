# Günther Cover Letter Specialization

Status: **FROZEN PLATEAU** (development gate not passed — QUALITY READY = NO)

## Goal

Specialize Phi-4-mini for German cover letters only:

`Evidence → Verified Plan → Specialized Writer → Safety Verify → [optional one targeted rewrite] → Ready`

No generic Critic1 / Revision2 in the production default.

Joint targets (LOCKED — must not be lowered for PR #19 optics):

- Automation ≥99%
- Ready-as-is ≥99%
- Cover ≥8.0
- Safety = 0

## PR #19 decision (2026-09-18)

| Flag | Value |
|------|-------|
| QUALITY READY | **NO** |
| MERGE READY | **NO** |
| PR #19 auto-merge | **NO** |
| Plateau freeze | **YES** — other product development may continue |
| Final blind fixture | **NOT created** (dev gate failed) |

Artifact: `benchmark/cover_specialization/pr19_plateau_freeze.json`

## Locked

- Primary model: Phi-4-mini (`Q4_K_M`, SHA256 `01999f17…c0c2`)
- Model selection: **closed**
- Evaluator: frozen under `benchmark/cover_specialization/`
- Default quality-loop mode: `plan_draft` + one targeted rewrite when needed

## Architecture

| Kept | Removed from default |
|------|----------------------|
| EvidenceStore DIRECT/RELATED/NOT_SUPPORTED | Generic Critic1 loop |
| Hard-requirement logic | Generic Critic2 / Revision2 |
| Verified Plan | Unbounded regeneration |
| Deterministic safety + max-1 safety repair | |
| One targeted rewrite | Few-shot (K≥2 regresses) |
| Phi-4-mini primary / Qwen3-1.7B light fallback | |

## A/B/C/D (verified)

| | Auto | Ready | Cover | Safety | Calls |
|--|------|-------|-------|--------|-------|
| A OLD | 85.11 | 76.60 | 7.665 | 0 | — |
| B Plan+Draft | 93.62 | 60.64 | 7.30 | 0 | 2.05 |
| C Critic1 | 89.36 | 64.89 | 7.17 | 0 | 4.12 |
| D Full | 85.11 | 58.51 | 7.045 | 0 | 4.85 |

Conclusion: Plan helps automation; generic critic/rev2 do not help.

## Frozen development gate (plan_draft_v2)

| Metric | Value | Target |
|--------|-------|--------|
| Auto | 93.62% | ≥99% |
| Ready | 84.04% | ≥99% |
| Balanced | 84.04% | ≥99% |
| Cover raw | 7.68 | ≥8.0 |
| Safety | 0 | 0 |

GEPA: base_v2 wins probe; mutants regress. Few-shot K=2 collapses (keep K=0).
Targeted rewrite kept experimentally. LoRA required but `BLOCKED_NO_SUITABLE_GPU`.

## Next blocker

Cover-only LoRA/QLoRA on a suitable NVIDIA GPU with ≥300 fictional SFT examples,
then re-measure the full development gate **before** any new blind fixture.

## Merge

Human merges PR #19 only when `QUALITY READY = YES` and `MERGE READY = YES`.
Do **not** lower targets to force a merge.
