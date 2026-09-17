# ADR: Günther Cover Writer Optimization

## Status

Accepted for development; production promotion pending development + blind gates.

## Context

Ablation A–D showed Plan+Draft maximizes eligible-safe automation but Writer prose quality lags OLD. Generic critic loops regress metrics.

## Decision

1. Keep Plan + Draft as production default.
2. Freeze the deterministic cover evaluator before Writer optimization.
3. Optimize Writer instructions (GEPA/bounded candidates) and optional few-shot on fictional gold only.
4. Allow at most one targeted quality rewrite; never reintroduce unbounded critic loops.
5. Escalate to cover-only LoRA/QLoRA only after prompt plateau; route adapter only to CoverLetterWriter.
6. Do not reopen model selection; Phi-4-mini stays primary.

## Consequences

- Simpler default path (≈2 model calls).
- Optimization tooling stays in `tools/cover_opt` / `requirements-dev`.
- Blind ≥200 eligible cases only after development 99/99/8/safety0.
