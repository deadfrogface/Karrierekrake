<!-- Suggested PR #19 body (forge SoT may block automated update). Copy into GitHub PR if needed. -->

## PR19 STATUS: FROZEN

| Flag | Value |
|------|-------|
| FUNCTIONAL | YES |
| QUALITY READY | **NO** |
| MERGE READY | **NO** |
| Auto-merge | **NO** |

Do **not** merge automatically. Do **not** lower joint targets (99% auto / 99% ready / cover ≥8.0 / safety 0) for optics.

Full freeze write-up: `docs/pr19-guenther-phi-freeze.md`  
Artifact: `benchmark/cover_specialization/pr19_plateau_freeze.json`

### A) Implemented in this PR (current code)

- Günther local advisory AI (CV / Job / Evidence / Email / Association / Writing / Interview)
- Evidence DIRECT/RELATED/NOT_SUPPORTED + deterministic safety validation
- **Primary:** Phi-4-mini (`phi4-mini` Q4_K_M)
- **LIGHT fallback still in runtime:** Qwen3-1.7B on LIGHT hardware (not yet removed)
- Writer default: `plan_draft` + optional one targeted rewrite; Critic1/Rev2 **not** production default

### B) Product architecture decided (not fully migrated)

- Long-term **Phi-only**: Phi STANDARD + Phi LIGHT from one specialized Phi base
- No long-term separate Qwen LIGHT — migration is **follow-up**, not this freeze

### C) Deferred

- Cover LoRA/QLoRA (`BLOCKED_NO_SUITABLE_GPU`, gold &lt;300)
- Phi LIGHT quant + real 8 GB Windows test
- Remove Qwen from runtime catalog
- New final blind set (only after dev gate passes)

### D) Quality gap (frozen measured gate)

| Metric | Frozen | Target |
|--------|--------|--------|
| Automation | 93.62% | ≥99% |
| Ready-as-is | 84.04% | ≥99% |
| Cover | 7.68 | ≥8.0 |
| Safety | 0 | 0 |

### E) Why continue with PR20

PR19 is functionally usable for continued product work, but cover quality gate failed. Further AI optimization without GPU would only bloat PR19. Next product PR: **PR20 — Profile Data Integrity**. Return to cover/Phi gate before commercial release.

### Safety

Accepted fabricated credentials / wrong company / wrong role / role reversal / RELATED→DIRECT / placeholders must remain **0**.
