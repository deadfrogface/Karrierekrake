# Günther 10-Model Local AI Tournament (Evidence Pass)

> **STALE_DOCUMENTATION (NEXT-01):** Historical evidence only.  
> Binding rules: [`docs/architecture/canonical-product-decisions.md`](architecture/canonical-product-decisions.md) — **ONE Phi model**, no Qwen production/fallback.  
> Current-state matrix: [`docs/project/current-state-reconciliation.md`](project/current-state-reconciliation.md).

**Branch:** `cursor/guenther-local-ai-megapass-d85b` (PR #19)  
**Scope:** Evidence-gathering only. **No** production default change. **No** winner implementation. **No** self-correction. **No** Qwen3-1.7B repair. **No** GGUF weights in git.  
**Runtime:** REAL GGUF via `llama-cpp-python==0.3.35`, CPU, ~15 GB RAM, 4 threads, `n_ctx=4096`, identical `GuentherService` prompts / validators / schemas / fixtures (`/no_think` retained). **REPAIR: NONE.**  
**Artifacts:** `benchmark/model_tournament_results.json`, `benchmark/model_tournament_raw/<model>/` (text/JSON only), `benchmark/model_tournament_catalog.json`, `benchmark/scripts/run_model_tournament.py`.

---

## Executive fields

| Field | Value |
|-------|-------|
| TOURNAMENT COMPLETE | **YES** |
| REAL GGUF EXECUTED | **YES** (A–I downloaded+run; J not downloaded) |
| PRODUCTION DEFAULT CHANGED | **NO** (still pinned Qwen3-1.7B Q4_K_M) |
| WINNER IMPLEMENTED | **NO** |
| SELF-CORRECTION IMPLEMENTED | **NO** |
| GATED | **J** — `GATED_LICENSE` (Llama 3.1 Community; Q4_0 ≠ Q4_K_M) |
| DISQUALIFIED_SAFETY | **none** |
| DISQUALIFIED_QUALITY | **B, C, G, H, I** (interview &lt; 4.0 and/or empty productive gen) |
| PHASE-2 SURVIVORS | **A, D, E, F** |
| WEIGHTED #1 (safety-pass) | **D Phi-4-mini** (82.86) — recommend for human review only |
| ARCHITECTURE REC | **TWO-TIER** (recommend only; not implemented) |
| NEXT PHASE | **C** — human review + claim-grounding scorer work; then decide |

---

## Phase 0 — Pre-flight verification

| MODEL | BASE | PARAMS | REPO | EXACT FILE | QUANT | SIZE | LICENSE | COMMERCIAL | REDIST | SHA256 (prefix) | LLAMA.CPP | CHAT TPL | TEXT-ONLY | DL ALLOWED | STATUS |
|-------|------|--------|------|------------|-------|------|---------|------------|--------|-----------------|-----------|----------|-----------|------------|--------|
| A | Qwen3-1.7B | 1.7B | bartowski/Qwen_Qwen3-1.7B-GGUF | Qwen_Qwen3-1.7B-Q4_K_M.gguf | Q4_K_M | 1.28GB LIGHT | Apache-2.0 | YES | OK | `72c5c3cb…` | YES | qwen3-im | YES | YES | READY |
| B | Qwen3-4B | 4B | Qwen/Qwen3-4B-GGUF | Qwen3-4B-Q4_K_M.gguf | Q4_K_M | 2.50GB MEDIUM | Apache-2.0 | YES | OK | `7485fe6f…` | YES | qwen3-im | YES | YES | READY |
| C | Qwen3.5-4B | 4B | unsloth/Qwen3.5-4B-GGUF | Qwen3.5-4B-Q4_K_M.gguf | Q4_K_M | 2.74GB MEDIUM | Apache-2.0 | YES | OK (community GGUF) | `00fe7986…` | YES | qwen-im | YES (mmproj unused) | YES | READY |
| D | Phi-4-mini-instruct | ~3.8B | bartowski/microsoft_Phi-4-mini-instruct-GGUF | microsoft_Phi-4-mini-instruct-Q4_K_M.gguf | Q4_K_M | 2.49GB MEDIUM | MIT | YES | OK | `01999f17…` | YES | phi/chatml | YES | YES | READY |
| E | Granite 3.3 2B Instruct | 2B | ibm-granite/granite-3.3-2b-instruct-GGUF | granite-3.3-2b-instruct-Q4_K_M.gguf | Q4_K_M | 1.55GB LIGHT | Apache-2.0 | YES | OK | `ac71e9e3…` | YES | granite | YES | YES | READY |
| F | Qwen3-8B | 8B | Qwen/Qwen3-8B-GGUF | Qwen3-8B-Q4_K_M.gguf | Q4_K_M | 5.03GB LARGE | Apache-2.0 | YES | OK | `d98cdcbd…` | YES | qwen3-im | YES | YES | READY |
| G | Qwen2.5-7B-Instruct | 7B | Qwen/Qwen2.5-7B-Instruct-GGUF | `…q4_k_m-00001-of-00002.gguf` (+00002) | Q4_K_M | 4.68GB LARGE SPLIT | Apache-2.0 | YES | OK | both shards recorded | YES | qwen2-im | YES | YES | READY |
| H | Granite 3.3 8B Instruct | 8B | ibm-granite/granite-3.3-8b-instruct-GGUF | granite-3.3-8b-instruct-Q4_K_M.gguf | Q4_K_M | 4.94GB LARGE | Apache-2.0 | YES | OK | `77bcee06…` | YES | granite | YES | YES | READY |
| I | Mistral 7B Instruct v0.3 | 7B | bartowski/Mistral-7B-Instruct-v0.3-GGUF | Mistral-7B-Instruct-v0.3-Q4_K_M.gguf | Q4_K_M | 4.37GB LARGE | Apache-2.0 | YES | OK (NOT Ministral) | `1270d22c…` | YES | mistral-instruct | YES | YES | READY |
| J | Llama 3.1 8B Instruct | 8B | ggml-org/Meta-Llama-3.1-8B-Instruct-Q4_0-GGUF | meta-llama-3.1-8b-instruct-q4_0.gguf | **Q4_0** | ~6.0GB | Llama 3.1 Community | RESTRICTED | NOT OK silently | recorded; **not fetched** | YES | llama3 | YES | **NO** | **GATED_LICENSE** |

Weights cached under `/tmp/karrierekrake-models/` only (not committed). Checksums verified where catalog SHA present.

---

## Phase 1 — Qualification (~35 identical cases)

Safety gates: **all runnable models passed** (injection / false consequential / false confident assoc / unsupported consequential / direct action / malformed / schema bypass = **0**). B’s prior injection failure did **not** recur under hardened pipeline.

Quality gate (`cover < 4.5` OR `interview < 4.0` OR empty productive gen), except baseline A kept for comparison:

| Letter | Status | Cover | Interview | Notes |
|--------|--------|------:|----------:|-------|
| A | QUALIFIED (baseline kept) | 5.1 | 2.0 | Interview empty TPS pattern |
| B | DISQUALIFIED_QUALITY | 7.2 | 1.0 | Cover OK; interview collapsed |
| C | DISQUALIFIED_QUALITY | 6.0 | 1.5 | Interview collapsed |
| D | QUALIFIED | 8.0 | 9.4 | Strong generative |
| E | QUALIFIED | 5.2 | 4.467 | Barely clears interview floor; `cv_ok=false` |
| F | QUALIFIED | 8.0 | 9.067 | Strong generative; LARGE/slow |
| G | DISQUALIFIED_QUALITY | 7.1 | 1.0 | Split GGUF complete; interview collapsed |
| H | DISQUALIFIED_QUALITY | 6.9 | 1.0 | Interview collapsed; `cv_ok=false` |
| I | DISQUALIFIED_QUALITY | 0.2 | 1.0 | 5/5 empty covers; schema/gen failure |
| J | GATED_LICENSE | — | — | Not run |

---

## Phase 2 — Full held-out (survivors A, D, E, F)

Identical surface: **73** emails (held-out + injection/hostile), **18** associations, **10** cover pairs, **≥6** interviews, evidence + CV/job structured. Raw letters saved under `benchmark/model_tournament_raw/<model>/`.

| Letter | Status | Email acc | Cover /10 | Interview /10 | Elapsed s | Size class | Empty covers | Safety zeros |
|--------|--------|----------:|----------:|--------------:|----------:|------------|-------------:|:------------:|
| A | COMPLETED_FULL | 0.986 | 6.2 | 2.0 | 707 | LIGHT | 0 | YES |
| D | COMPLETED_FULL | 1.000 | **7.6** | **8.917** | 1321 | MEDIUM | 0 | YES |
| E | COMPLETED_FULL | 1.000 | 5.75 | 6.667 | 1201 | LIGHT | 1 (`cl_admin` invalid_json) | YES |
| F | COMPLETED_FULL | 1.000 | 7.05 | 6.833 | 2473 | LARGE | 0 | YES |

### Weighted ranking (safety-pass only)

Weights: Cover 30% · Interview 20% · General accuracy 20% · Usefulness/abstention 15% · Perf/RAM/size 15%. Baseline elapsed = A.

| Rank | Letter | Model | Weighted | Cover | Interview | Perf score | Useful |
|-----:|--------|-------|---------:|------:|----------:|-----------:|-------:|
| 1 | **D** | Phi-4-mini | **82.86** | 7.6 | 8.917 | 48.2 | 100 |
| 2 | E | Granite 3.3 2B | 73.67 | 5.75 | 6.667 | 58.91 | 95 |
| 3 | F | Qwen3-8B | 73.03 | 7.05 | 6.833 | 21.45 | 100 |
| 4 | A | Qwen3-1.7B | 72.33 | 6.2 | 2.0 | 100 | 100 |

Tie-breakers not required (clear #1). Soft targets (≥7 cover/interview): **D meets both**; F meets cover only; E/A do not.

### Efficiency vs 1.7B

| Letter | Size / A | Wall / A | Cover Δ | Interview Δ |
|--------|---------:|---------:|--------:|------------:|
| D | ~1.94× | ~1.87× | +1.4 | +6.9 |
| E | ~1.20× | ~1.70× | −0.45 | +4.7 |
| F | ~3.92× | ~3.50× | +0.85 | +4.8 |

---

## Human-review flags (auto-scorer gaps)

Automatic cover rubric penalizes empty/role-reversal/wrong-role **tokens** / missing company / awkward DE — it does **not** yet catch **unsupported credential invention** in free text:

1. **D `cl_missing_hard`:** invents *Pflegeausbildung* / applies as *Pflegefachkraft* for Nora Admin (admin profile) — auto score **8.0**.
2. **F `cl_missing_hard`:** same invention pattern — auto score **8.0**.
3. **F interviews `iv_dental_medical`, `iv_junior`:** empty `talking_points`/`questions` with only `gap_notes` → **2.5** (unnecessary productive abstention).
4. **E `cl_admin`:** `invalid_json` → fail-closed empty letter.

These do **not** flip DISQUALIFIED_SAFETY (advisory writing path; consequential email/assoc gates stayed 0) but **must** inform architecture decision before any default change.

Infrastructure retries: **0** (no silent quality retries; outputs unchanged by retry).

---

## RAW → VALIDATED → FINAL

Pipeline unchanged: provider raw → schema validate → fail-closed / det-agreement where applicable. **REPAIR: NONE.** Samples in each model’s `emails.json`, `covers.json`, `interviews.json`, `cover_*.txt`.

---

## FINAL VERDICT

### Does ~7–8B solve the usefulness failure modes?

| Failure mode | Solved by 7–8B (F) / MEDIUM (D)? |
|--------------|----------------------------------|
| Wrong-role / invented credentials | **NO** (D & F invent Pflegeausbildung on hard mismatch) |
| Role reversal (recruiter voice) | **MOSTLY** (A still fails `missing_desirable`; D/F largely applicant voice) |
| Wrong company | **PARTIAL** |
| Empty generation | **PARTIAL** (covers filled on D/F; F still empty interview TPS on 2/6) |
| Generic / thin | **PARTIAL** (D best) |
| German naturalness | **YES, improved** |
| Evidence grounding | **PARTIAL** (more DIRECT; free-text claims still invent) |
| Interview usefulness | **PARTIAL** (D strong 8.9; F mixed 6.8) |
| Unnecessary abstention | **PARTIAL** (much better than A; not eliminated) |

**Conclusion:** Scaling alone does **not** fully solve productive quality. D is the best **weighted** safety-pass candidate; F is strong on cover but loses on latency/size and still abstains/hallucinates on hard cases.

### Root cause (baseline 1.7B productive quality)

| Code | Meaning |
|------|---------|
| **A** | Model capacity / generative instruction-following under JSON+evidence constraints — **PRIMARY** |
| B | Prompt/validator over-abstention (interview empties) — secondary |
| C | Runtime/decoding — minor (shared stack) |
| D | Fixture/scorer gap (misses credential invention) — secondary for next phase |

**Chosen: A** (larger models improve German + interview fill **without** prompt changes).

### Architecture recommendation (recommend only)

**TWO-TIER** — keep LIGHT model (A retained; E optional lightweight challenger) for advisory email/association footprint + existing safety; route writing/interview to **D** only after human accepts MIT provenance + adds claim-grounding / hard-mismatch validators.  
Do **not** implement routing or change defaults in this pass.

### Next phase (do not implement here)

| Code | Option |
|------|--------|
| A | Adopt D as production default now — **too early** |
| B | Implement two-tier immediately — **premature** |
| **C** | **Human review of D vs F raw letters + strengthen claim-grounding / hard-mismatch scoring; then decide ONE vs TWO-TIER** — **RECOMMENDED** |
| D | Expand tournament / repair 1.7B — out of this pass’s stop condition |

**Chosen: C.**

### Explicit non-actions (this pass)

- Production default remains **Qwen3-1.7B Q4_K_M**.
- Qwen3-1.7B **not removed**.
- Tournament winner **not wired** into product.
- Self-correction **not** added.
- PR **not** merged by agent.

---

## Reproduction

```bash
# Phase 1 (all READY except J gated)
.venv/bin/python -u benchmark/scripts/run_model_tournament.py --phase qualification

# Phase 2 survivors
.venv/bin/python -u benchmark/scripts/run_model_tournament.py --phase full --only A,D,E,F
```

Models must already be present under `GUENTHER_MODELS_DIR` / `/tmp/karrierekrake-models/` (or catalog `local_dir`). No weights are fetched into the repo tree.
