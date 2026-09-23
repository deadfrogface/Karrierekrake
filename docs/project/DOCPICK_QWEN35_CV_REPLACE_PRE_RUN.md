# Docpick + Qwen3.5-4B CV Replace — Pre-Run Lock

**Branch:** `cursor/docpick-qwen35-cv-replace-d85b`  
**Locked before any scoring on this architecture.**

## Import fields (Karrierekrake)

Scorer V2 / `import_cv`: name, email, phone, dob, address (street, house_number, postal_code, city, country), languages[+level], licenses, education entries, employment entries, skills, software, certificates.

## Licenses (code + weights)

| Source | Code | Weights | Offline | Decision |
|--------|------|---------|---------|----------|
| ArkNill/docpick | Apache-2.0 | n/a | yes (needs local LLM endpoint) | **Main orchestration** |
| Qwen/Qwen3.5-4B | Apache-2.0 | Apache-2.0 | local GGUF Q4_K_M (~2.6 GB) | **Main LLM** |
| Docling | MIT | model pkgs | yes (already working after torch fix) | **PDF text frontend** |
| sukhrobnurali/qwen3vl-resume-parser | Apache-2.0 | ~8.8B BF16 (~17 GB) VL-8B | CPU 15 GiB / no CUDA | **Skip** — not realistic on target hardware |
| Aillian/CVsAgent | MIT | n/a | OpenAI default / optional Ollama | Not primary (cloud default; schema not native KK) |
| Ollama structured outputs | docs only | n/a | — | Pattern reference; we use llama.cpp OpenAI-compat |

## Hardware assumptions (product SLA missing)

| Gate | Value | Rationale |
|------|-------|-----------|
| Host | 15 GiB RAM, 4 CPU, no CUDA | PHASE0 baseline |
| Peak RSS | ≤ **12000 MB** | Q4 4B + Docling + headroom |
| Avg s/CV | ≤ **120 s** | **Assumption** (no CV-import latency SLA in docs) |
| Quality | F1 ≥ 0.90, hallu ≤ 0.03, invented emp/edu = 0, process 10/10 | prior replace gate |

## Sample (locked)

Reuse `tests/oss_cv_replace/SAMPLE_MANIFEST_LOCKED.json` (`SMOKE_DE_EN_10_V1`) — fixed before this Docpick scoring. Scorer V2 unchanged. Known fixtures ≠ blind proof.

## Architecture under test

1. Docling PDF → markdown/text (proven local)  
2. Docpick `VLLMProvider` + Karrierekrake Pydantic schema (prompt + JSON parse from Docpick)  
3. Local `llama.cpp` OpenAI server serving `Qwen3.5-4B-Q4_K_M.gguf`  
4. Thin adapter → Scorer V2 parsed shape  

**Not repeated:** SmartResume+Docling smoke (F1 0.805) — no new technical reason beyond switching to Docpick schema/LLM stack + Qwen3.5-4B.
