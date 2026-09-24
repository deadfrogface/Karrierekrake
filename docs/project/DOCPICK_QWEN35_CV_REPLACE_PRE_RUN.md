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
| sukhrobnurali/qwen3vl-resume-parser | Apache-2.0 | ~8.8B BF16 (~17 GB) VL-8B | CPU 8 GB target / no CUDA | **Skip** — not realistic on target hardware |
| Aillian/CVsAgent | MIT | n/a | OpenAI default / optional Ollama | Not primary (cloud default; schema not native KK) |
| Ollama structured outputs | docs only | n/a | — | Pattern reference; we use llama.cpp OpenAI-compat |

## Hardware assumptions (product SLA)

| Gate | Value | Rationale |
|------|-------|-----------|
| Host (target) | **Intel Core i3 (11th gen), exactly 8 GB RAM**, no CUDA | Product target machine |
| Peak RSS (CV path) | **≤ 3.3 GB (3300 MB) — HARD FAIL above** | Soft ≤12 GB / ≤12000 MB is **obsolete** and is **not** success |
| Avg s/CV | ≤ **120 s** | **Assumption** (no CV-import latency SLA in docs) |
| Quality | F1 ≥ 0.90, hallu ≤ 0.03, invented emp/edu = 0, process 10/10 | prior replace gate |

Constant: `CV_IMPORT_PEAK_RSS_MB_MAX` in `core/cv_docpick_import.py` (default `3300`).

**Merge readiness for #62 = measured Peak RSS ≤ 3.3 GB** on the Docling+Qwen CV path (import process **plus** local LLM server). Do not treat ≤12 GB as a pass.

## Sample (locked)

Reuse `tests/oss_cv_replace/SAMPLE_MANIFEST_LOCKED.json` (`SMOKE_DE_EN_10_V1`) — fixed before this Docpick scoring. Scorer V2 unchanged. Known fixtures ≠ blind proof.

## Architecture under test

1. Docling PDF → markdown/text (proven local)  
2. Docpick `VLLMProvider` + Karrierekrake Pydantic schema (prompt + JSON parse from Docpick)  
3. Local `llama.cpp` OpenAI server serving `Qwen3.5-4B-Q4_K_M.gguf`  
4. Thin adapter → Scorer V2 parsed shape  

**Not repeated:** SmartResume+Docling smoke (F1 0.805) — no new technical reason beyond switching to Docpick schema/LLM stack + Qwen3.5-4B.
