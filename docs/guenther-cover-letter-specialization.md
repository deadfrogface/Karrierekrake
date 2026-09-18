# Günther Cover Letter Specialization

Status: **IN PROGRESS** (development gate not yet passed)

## Goal

Specialize Phi-4-mini for German cover letters only:

`Evidence → Verified Plan → Specialized Writer → Safety Verify → Ready`

Optional: one targeted rewrite. No generic Critic1 / Revision2 in the production default.

Joint targets: Automation ≥99%, Ready-as-is ≥99%, Cover ≥8.0, Safety = 0.

## Locked

- Primary model: Phi-4-mini (`Q4_K_M`, SHA256 `01999f17…c0c2`)
- Model selection: **closed**
- Evaluator: frozen under `benchmark/cover_specialization/`
- Default quality-loop mode: `plan_draft`

## Architecture

| Kept | Removed from default |
|------|----------------------|
| EvidenceStore DIRECT/RELATED/NOT_SUPPORTED | Generic Critic1 loop |
| Hard-requirement logic | Generic Critic2 / Revision2 |
| Verified Plan | Unbounded regeneration |
| Deterministic safety + max-1 safety repair | |
| Phi-4-mini primary / Qwen3-1.7B light fallback | |

## A/B/C/D (verified)

| | Auto | Ready | Cover | Safety | Calls |
|--|------|-------|-------|--------|-------|
| A OLD | 85.11 | 76.60 | 7.665 | 0 | — |
| B Plan+Draft | 93.62 | 60.64 | 7.30 | 0 | 2.05 |
| C Critic1 | 89.36 | 64.89 | 7.17 | 0 | 4.12 |
| D Full | 85.11 | 58.51 | 7.045 | 0 | 4.85 |

Conclusion: Plan helps automation; generic critic/rev2 do not help.

## Plan+Draft failure audit (6 eligible)

| Category | Count |
|----------|-------|
| PLAN_FALSE_BLOCK (SCHEMA_INVALID) | 2 |
| VALIDATOR_FALSE_POSITIVE | 3 |
| WRITER_UNSUPPORTED_CLAIM | 1 |

Targeted fixes applied (schema retry, claim/grounding FPs, IHK span, employer mis-tag, do_not_claim cleanup). Safety for true inventions (e.g. CISSP) remains blocking.

## Tooling

- `tools/cover_opt/` — DSPy Phi adapter, metric, cache/resume, runners
- DSPy `3.3.1` in `requirements-dev.txt` only (not runtime)
- Cache key: case+plan+prompt+demos+model+gen+evaluator hashes

## LoRA

Only if prompt/few-shot/targeted-rewrite plateau below 99/99. GPU required; otherwise `BLOCKED_NO_SUITABLE_GPU` with prepared scripts.

## Merge

Human merges PR #19 only when `QUALITY READY = YES` and `MERGE READY = YES`.


## Development gate result (plan_draft_v2)

| Metric | Value | Target |
|--------|-------|--------|
| Auto | 93.62% | ≥99% |
| Ready | 84.04% | ≥99% |
| Balanced | 84.04% | ≥99% |
| Cover raw | 7.68 | ≥8.0 |
| Safety | 0 | 0 |

GEPA: base_v2 wins probe (100/93.75); mutants regress.
Few-shot: K=2 collapses (keep K=0).
Targeted rewrite: see `targeted_rewrite_results.json`.
LoRA: REQUIRED but BLOCKED_NO_SUITABLE_GPU (+ insufficient gold <300).
QUALITY READY: NO. MERGE READY: NO.
