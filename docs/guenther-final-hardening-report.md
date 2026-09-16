# Günther Final Hardening / Generalization / Release-Gate Report

**Branch:** `cursor/guenther-local-ai-megapass-d85b`  
**PR #19:** not merged (human only)  
**Production default:** unchanged — Qwen3-1.7B Q4_K_M  

## Executive

| Field | Value |
|-------|-------|
| GÜNTHER FINAL HARDENING | **COMPLETE** (measured; gates below) |
| GENERALIZED CLAIM GROUNDING | **PASS** (deterministic 60+33 + wrong-co 30) |
| FULL HELD-OUT RERUN | **YES** (Phi-4-mini, 109 cases) |
| ALL SAFETY GATES ZERO | **YES** |
| BLIND COVER AVG | **7.18 / 10** (target ≥8.0 — **not met**) |
| BLIND INTERVIEW AVG | **8.07 / 10** |
| FALSE CREDENTIALS ACCEPTED (blind) | **0** (after envelope `ok` fix) |
| WRONG COMPANY ACCEPTED (blind) | **0** |
| REPAIR POLICY | **1 REPAIR** |
| RECOMMENDED ARCHITECTURE | **NOT_READY** (quality gate) |
| QUALITY READY | **NO** |
| MERGE READY | **NO** |

## Root causes addressed (prior pass failures)

1. **False credentials accepted** — `GuentherEnvelope.ok` was always `true`; now `history.final_ok ∧ report.ok`. Negated profile lines no longer emit positive credential aliases in `EvidenceStore`.
2. **WRONG_COMPANY with final_ok** — central `has_blocking_errors()` + severity `error` on `WRONG_COMPANY`.
3. **Repair #2** — 0/22 successful nonempty recoveries in historical raw → **max 1 repair**.
4. **Pflegeausbildung** — negated profile lines → `CONTRADICTED` / block (not DIRECT).

## Deterministic generalization (fixture SHA256 `05a822acdbc9ce0f5e23440b3857afd928f4b0d484f4e3f2c1fdff6f0e341962`)

| Suite | Result |
|-------|--------|
| Credential set 1 | 60 / 60 |
| Credential set 2 (post-fix unseen) | 33 / 33 |
| Wrong company | 30 / 30 |
| Eligible writing (validator templates) | 20 / 20 |
| Cross-case contamination (validator) | 2 / 2 |
| Repair validator deterministic | 30 / 30 |
| Material claim audit | ACCEPTED_UNSUPPORTED=0, ACCEPTED_CONTRADICTED=0 |

## Live Phi benchmarks

- **Held-out:** 108 / 109 pass; safety counters all 0; ~1575 s; ~10.7 GB RAM peak (see `benchmark/guenther_final_hardening_held_out.json`).
- **Blind cover (30):** avg **7.183/10**; hard-fail accepted **0**; first-pass ok **4/30**, repair-1 ok **2/30**.
- **Blind interview (20):** avg **8.065/10**; empty talking_points **1/20**; empty questions **1/20**.

## Tests & CI

- New: `tests/test_guenther_final_hardening.py`
- Repo pytest: **398 passed** (pre-push local)
- **CI:** PASS (commit `448177b`)
- **Windows Smoke:** PASS (commit `448177b`)

## Artifacts

- `benchmark/guenther_final_hardening_results.json`
- `benchmark/guenther_final_hardening_raw/` (incl. `blind_quality_live.json`)
- `benchmark/guenther_final_hardening_held_out.json`
- Historical tournament + grounding repair raw: **untouched**
