# Günther Writing Quality Final Report (Phi-4-mini)

> **STALE_DOCUMENTATION (NEXT-01):** “Production default Qwen” is outdated. See [`docs/architecture/canonical-product-decisions.md`](architecture/canonical-product-decisions.md).

**Branch:** `cursor/guenther-local-ai-megapass-d85b`  
**PR #19:** not merged  
**Production default:** unchanged (Qwen3-1.7B)  
**Model under test:** Phi-4-mini-instruct Q4_K_M  

## Executive

| Field | Value |
|-------|-------|
| PASS STATUS | **COMPLETE** (measured) |
| QUALITY READY | **NO** |
| MERGE READY | **NO** |
| SAFETY ZEROS (blind v2 accepted) | **YES** |
| ELIGIBLE ACCEPTANCE (blind v2) | **84.21%** (target ≥90%) |
| RAW / ACCEPTED AVG | **7.30 / 7.38** (target ≥8.0) |
| INTERVIEW AVG | **8.08 / 10** |
| HELD-OUT | **109 / 109**, all safety gates 0 |
| RECOMMENDED ARCHITECTURE | **NOT_READY** |
| PRODUCTION DEFAULT CHANGED | **NO** |

## Stage 1–2 — Forensic audit (prior 30 blind, Phi replay)

Bodies were not stored in the prior hardening raw JSON; a full Phi+repair replay was executed and saved under `benchmark/guenther_writing_quality_final_raw/forensic_prev_blind30/`.

| Metric | Value |
|--------|------:|
| Final accepted (replay) | 5 / 30 |
| Fail-closed audited | 25 / 25 |
| A True safety invent | 8 |
| B Targeting / placeholder / company | 12 |
| C Overstrict validator | 0 |
| D Claim-extraction false positive | 4 |
| E Evidence-match false negative | 0 |
| F Repair failure | 0 |
| G Model quality only | 0 |
| H Hard requirement | 0 |
| I Structural / empty | 1 |
| J Other | 0 |
| JUSTIFIED fail-closed | **20 / 30** |
| UNNECESSARY fail-closed | **5 / 30** |

**Root cause summary:** Soft possession phrasing (`Ich bin überzeugt…`, `Mit meiner Erfahrung…`) was classified as `CREDENTIAL`+`requires_direct`; model also invented `Ausbildung` / `Pflegeausbildung` and inserted `[Ihr Name]` placeholders; known company often omitted → `WRONG_COMPANY`.

## Fixes applied (safety thresholds not weakened)

1. **Claim extraction:** soft experience/attitude → `EXPERIENCE`/`SKILL` without hard-direct; formal markers still credentials; **negation window** skips `kein/keine … Zertifikat`.
2. **Evidence matching:** soft skill aliases; Abschluss↔Ausbildung only with domain token.
3. **Writing + repair prompts:** structure, company, no placeholders, transferable wording, minimal repair.
4. **Envelope `ok`:** already required validator+repair final state (prior pass).

## Development set (20)

| Metric | Value |
|--------|------:|
| Final accepted | 17 / 20 |
| Eligible acceptance | 84.21% |
| Unnecessary fail-closed | 0% |
| RAW avg | 7.73 |

## Final blind v1 (frozen, pre–negation fix) — archived

| Metric | Value |
|--------|------:|
| Fixture SHA (content) | see freeze file |
| Final accepted | 32 / 40 |
| Eligible acceptance | 84.21% |
| RAW / ACCEPTED avg | 7.70 / 7.63 |
| Unnecessary fail-closed rate | 0% |
| Safety accepted zeros | all 0 |

## Final blind v2 (post-fix unseen gate)

**Fixture SHA256:** `0d74ce241407c6cfb12e634319d258d4f47d2838ec5c00effa1bc4930f5d70a1`  
**Frozen before run:** YES (`blind_v2_fixture_freeze.json`)

| Metric | Value |
|--------|------:|
| Cases | 40 |
| RAW avg | **7.30 / 10** |
| ACCEPTED avg | **7.38 / 10** |
| Median / P10 / P90 | 8.0 / 6.0 / 8.0 |
| First-pass accepted | 30 / 40 |
| Repair required | 10 / 40 |
| Repair recovered | 2 / 40 |
| Justified hard block | 2 |
| Justified safety/targeting | 5 |
| Unnecessary fail-closed | 1 (2.5%) |
| Final accepted | 32 / 40 |
| Eligible safe acceptance | **84.21%** |
| False credentials accepted | 0 |
| Unsupported / contradicted accepted | 0 |
| Wrong company / role / reversal | 0 |
| Related-as-direct / placeholder / nan | 0 |
| Repair-introduced accepted blocking | 0 |

Remaining eligible fails are mostly **true model invents of `Ausbildung`** on otherwise strong profiles (justified safety), plus 1 empty-output case.

## Interview (20 fresh)

| Metric | Value |
|--------|------:|
| Avg | **8.075 / 10** |
| Empty talking_points | **0** |
| Empty questions | **0** |
| Unsupported material accepted | **0** |

## Held-out consequential (Phi live, post-prompt)

| Metric | Value |
|--------|------:|
| Result | **109 / 109** |
| All safety gates | **0** |

## Architecture

**NOT_READY** for default flip: writing RAW/ACCEPTED avg and eligible acceptance still below release targets despite large acceptance lift (prior blind 6/30 → 32/40).

Recommend only after another writing-quality iteration: still **PHI_DEFAULT_QWEN_LIGHT_OPTION** as directional preference when quality gates clear — **not applied**.

## Tests

- New claim-semantics tests: PASS  
- Full `pytest`: **401 passed**  
- CI / Windows Smoke: see latest PR checks after push
- **CI:** PASS (commit `aaecb02`)
- **Windows Smoke:** PASS (commit `aaecb02`)
