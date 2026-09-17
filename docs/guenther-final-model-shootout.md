# Günther Final Local Model Shootout

## Verdict

**BEST MEASURED MODEL:** `phi4-mini`  
**RELEASE-READY MODEL:** `NOT_READY`  
**PRODUCTION DEFAULT CHANGED:** **NO**  
**PR #19 MERGED:** **NO**

Phase-1 (existing fixtures) showed 100% eligible-safe automation for all runnable
candidates with zero accepted safety failures. Independent Phase-2 confirmation on
the previously blind 100-cover fixture dropped Phi automation to **85.11%** with
**14.89%** unnecessary fail-closed — so observed Phase-1 100% is **not** proof of
a true ≥99% production rate.

---

## Strategy (corrected)

| Phase | Fixtures | Purpose |
|-------|----------|---------|
| **1** | Existing writing-quality final (40 blind covers + 20 interviews), hardening (credentials/wrong-company/repair), grounding adversarial, Pflege | Winner selection |
| **2** | NEW `guenther_final_model_shootout_fixture` (100 covers + 30 interviews) | Independent confirmation **only after** winner selection |

- Pipeline freeze commit: `787c2816b4e4a1e4d80b6443e77fea54b5115c40`
- Repair policy: **max 1** (identical for all)
- Runtime: **llama-cpp-python 0.3.35**, `n_ctx=4096`, text-only, CPU
- Hardware: **15 GiB RAM**, 4 cores, no GPU
- Quantization: **Q4_K_M** for all candidates
- Production default (**Qwen3-1.7B**) **not** changed

### New fixture blindness

| Checkpoint | Status |
|------------|--------|
| SHA256 | `858d60b36e1b0bc3cc3791cc55aa57f8d6fc5fac6d804bc8a48d49bd0131852a` |
| Remained blind through Phase-1 (no `sc_*` execution) | **YES** |
| Used for Phase-1 winner selection | **NO** |
| Phase-2 executed against winner after selection | **YES** (`phi4-mini`) |
| Post-Phase-2 tuning | **NO** |

**Phase Y correction note:** Raw execution chronology and
`benchmark/guenther_final_model_shootout_results.json` → `new_fixture_blind_status.remained_blind_through_phase1=true`
confirm blindness through Phase-1. Phase-1 raw outputs contain only pre-existing suites
(`wq_final_blind_covers`, hardening, …); `sc_*` appears first under Phase-2 paths.
If any summary text previously read as “Remained blind … False”, that was a **presentation
inconsistency only** — benchmark numbers and blindness facts were not rewritten.

---

## Model provenance

| ID | Upstream | GGUF | SHA256 (LFS) | License | Size |
|----|----------|------|--------------|---------|------|
| A phi4-mini | microsoft/Phi-4-mini-instruct | bartowski Q4_K_M | `01999f17…c0c2` | MIT | 2.32 GB |
| B qwen35-9b | Qwen/Qwen3.5-9B | unsloth Q4_K_M | `03b74727…b7e8` | Apache-2.0 | 5.29 GB |
| C gemma4-12b | google/gemma-4-12b-it | bartowski Q4_K_M | `3962624d…1509` | Gemma Terms (**legal review**) | 7.14 GB |
| D qwen3-14b | Qwen/Qwen3-14B | official Qwen GGUF Q4_K_M | `500a8806…81f0` | Apache-2.0 | 8.38 GB |
| E qwen35-27b | Qwen/Qwen3.5-27B | unsloth Q4_K_M | `84b5f7f1…d806` | Apache-2.0 | 15.59 GB |

**E NOT_RUN_HARDWARE:** Q4_K_M ≈16.7 GB weights alone; host has 15 GiB RAM / no swap. No simulated results.

---

## Phase-1 results (existing 40-cover + 20-interview fixtures)

Identical pipeline/validators/scoring/repair for every candidate.

| MODEL | QUANT | SIZE_GB | PEAK_RAM_MB | AVG_LAT_S | P95_LAT | COVER_RAW | COVER_ACC | MEDIAN | READY% | 1ST% | REPAIR% | AUTO% | UNNEC% | MAN/1200* | IV_AVG | SAFETY | HELD-OUT | LICENSE | DEPLOY |
|-------|-------|---------|-------------|-----------|---------|-----------|-----------|--------|--------|------|---------|-------|--------|-----------|--------|--------|----------|---------|--------|
| phi4-mini | Q4_K_M | 2.32 | 5611 | 30.3 | 51.8 | **7.75** | 7.74 | 8.0 | **84.21** | 90.0 | 50.0 | **100** | **0.0** | **0*** | **8.22** | **0** | 109/109 reuse | MIT | CONSUMER_STANDARD |
| qwen35-9b | Q4_K_M | 5.29 | 10517 | 72.3 | 131.5 | 7.30 | 7.47 | 8.0 | 71.05 | 90.0 | 50.0 | 100 | 0.0 | 0* | 6.66† | 0 | — | Apache-2.0 | CONSUMER_HIGH |
| gemma4-12b | Q4_K_M | 7.14 | 14466 | 96.5 | 198.6 | 7.50 | 7.47 | 8.0 | 73.68 | 92.5 | 33.3 | 100 | 0.0 | 0* | **8.25** | 0 | — | Gemma ToU | ENTHUSIAST |
| qwen3-14b | Q4_K_M | 8.38 | 14511 | 141.6 | 184.2 | 7.50 | 7.49 | 8.0 | 71.05 | 95.0 | 50.0 | 100 | 0.0 | 0* | 7.94 | 0 | — | Apache-2.0 | ENTHUSIAST |
| qwen35-27b | Q4_K_M | 15.59 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | Apache-2.0 | IMPRACTICAL_FOR_DEFAULT |

\*MAN/1200 = benchmark extrapolation from eligible-safe **unnecessary fail-closed** rate only (not ready-as-is gaps).  
†Qwen3.5-9B: 4 empty talking-points / 4 empty questions on supported interview cases.

### Phase-1 score distribution (covers)

| Model | &lt;6 | 6.0–6.9 | 7.0–7.9 | 8.0–8.9 | 9.0–9.4 | ≥9.5 |
|-------|------|---------|---------|---------|---------|------|
| phi4-mini | 0 | 6 | 0 | 34 | 0 | 0 |
| qwen35-9b | 1 | 11 | 0 | 28 | 0 | 0 |
| gemma4-12b | 1 | 9 | 0 | 30 | 0 | 0 |
| qwen3-14b | 0 | 11 | 0 | 29 | 0 | 0 |

### Phase-1 safety / deterministic gates

All runnable models: **zero** accepted blocking factual/safety errors on generated covers.  
Wrong-company / credential / repair validator false-accepts: **0**. Pflege regression: **PASS**. Adversarial claim match: **100%** (deterministic EvidenceStore).

### Held-out (Stage 15/16)

- **phi4-mini:** 109/109 reused (pipeline freeze unchanged; all safety gates zero).
- **B/C/D:** not advanced — none beat Phi on cover (≥8.0 or +0.3) while automation was tied at 100%; Qwen3.5-9B also missed interview ≥8.0.

---

## Phase-2 independent confirmation (Phi only, previously blind fixture)

| Metric | Phase-1 (40 existing) | Phase-2 (100 new) |
|--------|----------------------|-------------------|
| Eligible-safe automation | 100% | **85.11%** (80/94) |
| Unnecessary fail-closed | 0% | **14.89%** (14/94) |
| Cover raw avg | 7.75 | 7.67 |
| Cover accepted avg | 7.74 | 7.81 |
| Ready-as-is % | 84.21 | 76.6 |
| Interview avg | 8.22 | 7.97 |
| Empty TPS / questions | 0 / 0 | 0 / 0 |
| Accepted safety failures | 0 | **0** |
| Projected manual reviews / 1200* | 0* | **~179*** |

\*Extrapolation from unnecessary fail-closed rate on this benchmark — not a guaranteed production rate.

**Interpretation:** Observed Phase-1 100% automation did **not** hold on the larger unseen fixture. A later **300–500-case** automation confirmation is recommended before any commercial claim of ≥99%.

---

## Winner logic (priority order applied)

1. **Absolute safety** — all runnable: 0 accepted blocking errors  
2. **Eligible-safe automation** — Phase-1 tie at 100%; Phase-2 Phi 85.11%  
3. **Ready-as-is** — Phi 84.21% leads Phase-1  
4. **Cover quality** — Phi 7.75 leads  
5. **Interview** — Gemma 8.25 slightly above Phi 8.22; Qwen3.5-9B fails (6.66)  
6. **Structured output** — all produced usable JSON via existing provider path  
7–10. **Resources / latency / size / license** — Phi lightest & fastest; Gemma needs legal review  

---

## Architecture recommendation

| Question | Answer |
|----------|--------|
| BEST MEASURED MODEL | **phi4-mini** |
| RELEASE-READY MODEL | **NOT_READY** |
| BEST DEFAULT MODEL (catalog option, not prod flip) | **phi4-mini** |
| BEST HIGH-QUALITY MODEL | None clearly better than Phi on this pass; Gemma/Qwen3-14B are heavier peers, not winners |
| BEST LIGHT MODEL | **qwen3-1.7b** (unchanged production light) |
| SHOULD PHI BE REPLACED | **NO** |
| SHOULD QWEN3-1.7B REMAIN PRODUCTION DEFAULT FOR NOW | **YES** |
| ONE MODEL OR MULTI-TIER | **OPTION C:** light default (Qwen3-1.7B) + hardened standard (Phi) as optional/strong tier; optional HQ only if hardware + future evidence support it |
| WHY | Phi wins Phase-1 on ready-as-is, cover quality, latency, and RAM among equal automation/safety; Phase-2 shows automation still below release bar; no candidate reached cover ≥8.0 + ready ≥95% + ≥99% automation |

### Distribution strategy (Stage 18, design only)

- Do **not** bundle multi‑GB weights in Git  
- Download-on-first-use / optional strong model with checksum, resume, disk/RAM checks  
- Fallback: production light Qwen3-1.7B  

### Hardware classes (measured + estimate)

| Model | Measured peak RSS | Suggested class |
|-------|-------------------|-----------------|
| phi4-mini | ~5.6 GB | 8–16 GB system RAM, GPU optional |
| qwen35-9b | ~10.5 GB | ≥16 GB |
| gemma4-12b / qwen3-14b | ~14.5 GB | ≥24 GB comfortable; tight on 16 GB |
| qwen35-27b | not run | ≥32 GB |

---

## Absolute winner targets vs observed (Phi)

| Target | Need | Phase-1 | Phase-2 |
|--------|------|---------|---------|
| Safety gates | 0 | 0 | 0 |
| Eligible-safe automation | ≥99% | 100% | **85.11%** |
| Unnecessary fail-closed | ≤1% | 0% | **14.89%** |
| Cover raw / accepted | ≥8.0 | 7.75 / 7.74 | 7.67 / 7.81 |
| Interview | ≥8.0 | 8.22 | 7.97 |
| Ready-as-is | ≥95% | 84.21% | 76.6% |

→ **NOT_READY** for release-as-default despite being best measured.

---

## Artifacts

- Report: `docs/guenther-final-model-shootout.md`
- Results: `benchmark/guenther_final_model_shootout_results.json`
- Raw: `benchmark/guenther_final_model_shootout_raw/`
- Blind reserve fixture: `benchmark/guenther_final_model_shootout_fixture.json` + `.sha256`
- Catalog: `benchmark/guenther_final_model_shootout_catalog.json`

Historical tournament / hardening / writing-quality artifacts were **not** overwritten.
