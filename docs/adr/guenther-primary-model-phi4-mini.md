# ADR: Günther primary model = Phi-4-mini

**Status:** Accepted (PR #19 quality-loop pass)  
**Date:** 2026-09-17  
**Product:** Karrierekrake — assistant personality remains **Günther**

## Decision

**Phi-4-mini-instruct (Q4_K_M, bartowski GGUF SHA `01999f17…c0c2`)** is locked as Günther’s **PRIMARY** local reasoning/writing model.

**Qwen3-1.7B** remains available only as **LIGHT hardware / failsafe fallback**.

## Context

The final local model shootout compared:

| ID | Model | Result |
|----|-------|--------|
| A | Phi-4-mini | Best measured (Phase-1 + Phase-2) |
| B | Qwen3.5-9B | Weaker quality / interview empties |
| C | Gemma 4 12B | Heavier; legal ToU; not better overall |
| D | Qwen3-14B | Heavier; not better automation/quality |
| E | Qwen3.5-27B | `NOT_RUN_HARDWARE` on 15 GiB host |

Winner priority used: safety → automation → ready-as-is → quality.

Phase-1 (existing fixtures): Phi 100% eligible-safe automation, 0 safety failures, cover raw 7.75, ready 84.21%, interview 8.22.

Phase-2 (independent blind 100 covers): Phi automation **85.11%**, unnecessary fail-closed **14.89%**, cover raw **7.665**, ready **76.6%** → **NOT release-ready**, but still best measured.

## Why not hop to a larger model?

- Larger candidates did not beat Phi on the release bar under identical validators.
- Consumer RAM (~8–16 GB) favors Phi (~2.3 GB weights, ~5.6 GB peak observed).
- Gemma Terms require legal review; not suitable as default without that.
- E is impractical as default on typical consumer hardware.

## Why workflow architecture instead of another tournament?

Phase-2 failures are dominated by **placeholder leakage**, **unsupported credential phrasing**, and **generic/weak specificity** — problems that a structured

**EVIDENCE → PLAN → DRAFT → CRITIQUE → TARGETED REVISION → SAFETY VERIFY**

pipeline can address without changing the model. Model hopping is closed for this cycle.

## Qwen3-1.7B role

- LIGHT tier (`ram < 8 GB` or ≤2 CPUs): automatic fallback.
- Explicit user preference always respected.
- Not described as the best quality model.

## Reopen conditions

Reopen model selection only if:

1. Phi cannot reach acceptable release quality after structured workflow, or
2. A materially stronger local model fits realistic consumer hardware, or
3. Phi licensing/distribution becomes unsuitable, or
4. Runtime support becomes unsuitable, or
5. Real-world tests show a persistent Phi-specific limitation.

Until then: **PHI IS LOCKED.**
