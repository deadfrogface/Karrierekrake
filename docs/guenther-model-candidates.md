# Günther die Krake — Phase 2: Model Candidates

**Date:** 2026-09-15  
**Branch:** `cursor/guenther-local-ai-megapass-d85b`  
**Rule:** No weights in git. User downloads into `%LOCALAPPDATA%\Karrierekrake\models\`. Code license ≠ model license.

---

## Selection goals

1. German-capable instruction following for CV / job / email / interview tasks  
2. Structured JSON outputs (schema-validated)  
3. Smallest model that meets **safety** thresholds (false rejection, false HIGH_CONFIDENCE association, invented facts heavily penalized)  
4. Low-end Windows CPU viable (LIGHT tier)  
5. Commercial-license-safe for default Auto catalog  

---

## Candidate table

| ID | Model | Params | License | Typical GGUF size (approx.) | RAM ballpark (Q4_K_M / Q5) | German | Notes | Catalog role |
|----|-------|-------:|---------|----------------------------:|---------------------------:|--------|-------|--------------|
| `qwen3-1.7b` | Qwen3-1.7B-Instruct (official GGUF) | 1.7B | **Apache-2.0** | ~1.1–1.8 GB (Q4–Q8) | ~2–3 GB | Good multilingual | Smallest serious candidate | **LIGHT / default fallback** |
| `qwen3-4b` | Qwen3-4B-Instruct (official GGUF) | 4B | **Apache-2.0** | ~2.5–4.3 GB | ~4–6 GB | Stronger | Better JSON + DE nuance | **STANDARD Autopick target** |
| `phi4-mini` | Phi-4-mini-instruct | ~3.8B | **MIT** | ~2.3–2.5 GB Q4_K_M | ~4–5 GB | Solid multilingual | Strong reasoning; MIT-friendly | **STANDARD alternate** |
| `gemma3-4b` | Gemma 3 4B Instruct | 4B | **Gemma ToU** (not Apache for Gemma 3) | ~2.5–4 GB | ~4–6 GB | Good | Flow-down ToU risk | **REJECT default**; optional only after review |
| `qwen2.5-1.5b` | Qwen2.5-1.5B-Instruct | 1.5B | Apache-2.0 | ~1 GB | ~2 GB | Decent | Older gen; keep as emergency LIGHT if Qwen3 GGUF unavailable | Optional LIGHT legacy |

**Not candidates for default:** 7B+ (POWER-only if ever justified), cloud APIs, browser Xenova classifiers as required deps.

---

## Hardware tiers (justified)

| Tier | Detect when | Default model | Behavior if model missing / OOM |
|------|-------------|---------------|----------------------------------|
| **LIGHT** | ≤8 GB RAM or weak CPU / 32-bit constraints | `qwen3-1.7b` Q4_K_M | Deterministic Karrierekrake only; Günther shows „nicht verfügbar“ |
| **STANDARD** | 8–16 GB RAM typical Windows laptop | `qwen3-4b` Q4_K_M (or `phi4-mini`) | Fall back to LIGHT model if OOM |
| **POWER** | ≥24 GB RAM or discrete GPU with local accel | Same STANDARD weights; longer context / higher quant optional | Still no cloud; optional Q5/Q6 |

Only three tiers — no marketing sprawl. Auto = detect tier → pick installed model → else prompt install.

---

## Quantization policy

| Quant | Use |
|-------|-----|
| **Q4_K_M** | Default download for LIGHT/STANDARD |
| Q5_K_M | Optional POWER quality bump |
| Q8_0 | Dev/benchmark reference only (large) |
| IQ2 / extreme | **REJECT** for product — too lossy for safety-critical association |

---

## Download sources (manager allowlist) — pinned 2026-09-15

| Catalog ID | Resolve URL | SHA256 (HF LFS) | Size |
|------------|-------------|-----------------|-----:|
| `qwen3-1.7b` | `https://huggingface.co/bartowski/Qwen_Qwen3-1.7B-GGUF/resolve/main/Qwen_Qwen3-1.7B-Q4_K_M.gguf` | `72c5c3cb38fa32d5256e2fe30d03e7a64c6c79e668ad84057e3bd66e250b24fb` | ~1.28 GB |
| `qwen3-4b` | `https://huggingface.co/Qwen/Qwen3-4B-GGUF/resolve/main/Qwen3-4B-Q4_K_M.gguf` | `7485fe6f11af29433bc51cab58009521f205840f5b4ae3a32fa7f92e8534fdf5` | ~2.50 GB |
| `phi4-mini` | *(empty)* | — | **REVIEW REQUIRED** deferral |

Prefer official repos when they publish the needed quant. Official Qwen 1.7B GGUF currently offers Q8_0 only; LIGHT uses bartowski Q4_K_M (base model still Apache-2.0).

**No silent multi-GB download.** UI must show size, license, destination path, progress, cancel. Manager requires `allow_download=True`.

---

## Benchmark expectations (Phase 3–4)

Corpus: fictional German CV, jobs, emails, association traps, cover-letter anchors, interview prep.  
Severe penalties:

- False **rejection** classification  
- False **HIGH_CONFIDENCE** email↔case association  
- Invented candidate facts / employers / degrees  

Winner rule: smallest model meeting safety threshold; prefer Apache/MIT.

**Provisional Autopick (pre-benchmark):** `qwen3-4b` STANDARD, `qwen3-1.7b` LIGHT. Confirmed in `benchmark/results.json` + `docs/guenther-benchmark-report.md` after corpus run.

---

## Packaging note

EXE ships **runtime adapter code** only (optional `llama-cpp-python` wheel strategy documented in Phase 23). Weights never inside `Karrierekrake.exe`.
