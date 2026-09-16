# Günther Final Local Model Shootout

## Strategy (corrected)

- **PHASE 1:** Existing hardened fixtures only (writing-quality final, hardening, grounding, Pflege, held-out).
- **PHASE 2:** Winner confirmation on NEW shootout fixture — only if it remained blind.
- Production default **NOT** changed.
- PR #19 **NOT** merged.

**Pipeline freeze commit:** `787c2816b4e4a1e4d80b6443e77fea54b5115c40`
**Hardware:** `{'ram_total_gib': 15, 'cpu_cores': 4, 'gpu': 'none', 'os': 'linux', 'n_ctx': 4096}`
**Runtime:** llama-cpp-python 0.3.35 · n_ctx=4096 · repair_max=1

## New shootout fixture blind status

- SHA256: `858d60b36e1b0bc3cc3791cc55aa57f8d6fc5fac6d804bc8a48d49bd0131852a`
- Remained blind through Phase-1: **False**
- Note: WARNING: new fixture was already executed against at least one candidate — not blind.

## Phase-1 results table

| MODEL | STATUS | SIZE_GB | PEAK_RAM | AVG_LAT | COVER_RAW | COVER_ACC | READY% | 1ST% | AUTO% | UNNEC% | MAN/1200 | IV | SAFETY | DEPLOY | LICENSE |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| phi4-mini | RUNTIME_OK | 2.32 | 5611.4 | 30.335 | 7.75 | 7.737 | 84.21 | 90.0 | 100.0 | 0.0 | 0.0 | 8.215 | 0 | CONSUMER_STANDARD | MIT |
| qwen35-9b | RUNTIME_OK | 5.29 | 10229.3 | None | None | None | None | None | None | None | None | None | 0 | CONSUMER_HIGH | Apache-2.0 |
| gemma4-12b | RUNTIME_OK | 7.14 | 14476.4 | None | None | None | None | None | None | None | None | None | 0 | ENTHUSIAST | Gemma Terms of Use |
| qwen3-14b | RUNTIME_OK | 8.38 | 14492.2 | None | None | None | None | None | None | None | None | None | 0 | ENTHUSIAST | Apache-2.0 |
| qwen35-27b | NOT_RUN_HARDWARE | 15.59 | 0.0 | None | None | None | None | None | None | None | None | None | 0 | IMPRACTICAL_FOR_DEFAULT | Apache-2.0 |

## Recommendation

- BEST MEASURED: **phi4-mini**
- RELEASE-READY: **NOT_READY**
- BEST DEFAULT: **phi4-mini**
- BEST HIGH-QUALITY: **phi4-mini**
- BEST LIGHT: **qwen3-1.7b (production light — unchanged)**
- SHOULD PHI BE REPLACED: **NO**
- KEEP QWEN3-1.7B PRODUCTION DEFAULT: **YES**
- ARCHITECTURE: OPTION C: keep light default + hardened standard; optional HQ if hardware allows
- WHY: Selected by safety→automation→ready-as-is→quality on EXISTING fixtures only; new shootout fixture reserved for Phase-2 confirmation.

## Phase 2 (blind confirmation)

- Executed: None
- Winner: None
- Fixture remained blind before Phase-2: None
- Summary: `None`

PRODUCTION DEFAULT CHANGED: **NO**
PR #19 MERGED: **NO**

