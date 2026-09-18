# ADR: PR #19 Cover Writer Plateau Freeze

## Status

Accepted — freeze for continued product development; gate not passed.

## Context

Prompt/GEPA/few-shot/targeted-rewrite optimization plateaued below the joint targets
on the frozen development fixture. Safety remains at zero accepted failures.

## Decision

1. **Freeze** the current cover-writer configuration (`plan_draft_v2` + targeted rewrite,
   Critic1/Rev2 removed from default, Phi-4-mini locked).
2. **Do not lower** Automation ≥99%, Ready ≥99%, Cover ≥8.0, Safety = 0.
3. Set **QUALITY READY = NO** and **MERGE READY = NO**.
4. **Do not auto-merge** PR #19.
5. **Allow** other product work to continue on top of / alongside this frozen baseline.
6. **Do not** create a new final blind cover fixture until the development gate passes.
7. Resume cover quality only via the documented next blocker (cover-only LoRA on GPU,
   or a new measured optimization pass that does not weaken targets or the frozen evaluator).

## Frozen measured gate

| Metric | Frozen value | Target |
|--------|--------------|--------|
| Automation | 93.62% | ≥99% |
| Ready-as-is | 84.04% | ≥99% |
| Cover raw | 7.68 | ≥8.0 |
| Safety | 0 | 0 |

## Consequences

- PR #19 remains open until a human merges after QUALITY READY = YES.
- Rest of Karrierekrake development may proceed without waiting for 99/99 cover.
- Future cover work must treat the frozen evaluator and these targets as binding.
