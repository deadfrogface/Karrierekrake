# NEXT-02 Release Gate — Single Phi Production + CV Intelligence

**Date:** 2026-09-21  
**Branch:** `cursor/next-02-single-phi-cv-d85b`  
**Base:** `main` (post NEXT-01 / #47)

## Production Phi pin (do not substitute)

| Field | Value |
|-------|--------|
| Catalog id | `phi4-mini` |
| Filename | `microsoft_Phi-4-mini-instruct-Q4_K_M.gguf` |
| Quant | `Q4_K_M` |
| SHA256 | `01999f17c39cc3074afae5e9c539bc82d45f2dd7faa3917c66cbef76fce8c0c2` |
| Source repo | `bartowski/microsoft_Phi-4-mini-instruct-GGUF` |
| Base model | `microsoft/Phi-4-mini-instruct` |
| License | MIT |

Provenance: tournament / final shootout (PR #19 megapass D). No other Phi artifact selected.

---

## Gate results

| Gate | Result | Evidence |
|------|--------|----------|
| **EXACTLY ONE PRODUCTION LLM** | **PASS** | `MODEL_CATALOG` contains only `phi4-mini` |
| **QWEN PRODUCTION PATH** | **MUST BE ABSENT — PASS** | Qwen moved to `HISTORICAL_MODEL_CATALOG`; install/runtime reject |
| **MODEL FALLBACK** | **MUST BE ABSENT — PASS** | Hardware/routing always Phi; OOM/load → `GUENTHER_UNAVAILABLE`, no alternate LLM |
| **REAL CV PHI INVOCATION** | **PASS** (unit/wiring) | `import_cv_canonical` → `suggest_cv_extract`; dialog wires Guenther when enabled |
| **BERUFSERFAHRUNG** | **PASS** (synthetic) / **PENDING** (real private EXE) | Gap-fill + DOCX tables + corpus; real private CV = local only |
| **AUSBILDUNG** | **PASS** (synthetic) / **PENDING** (real private EXE) | Same |
| **RESTART** | **PENDING** (real Windows EXE) | Persistence path unchanged; black-box EXE not run in this Linux agent |

---

## Behavioural contract

- If Phi cannot load: **GUENTHER_UNAVAILABLE** with cause (missing / download failed / corrupted / insufficient RAM / runtime error).
- Non-AI functions remain usable.
- Heuristic provider is **not** a production LLM substitute (`allow_heuristic_when_no_llm=False` by default).
- CV pipeline: FILE → extract (PDF layout + DOCX tables) → deterministic parse → Phi semantic (when enabled) → grounding → reconciliation → preview → approval → persist.
- Manual profile data remains authoritative.
- Private CVs: `private/cvs/` (gitignored). Never commit, upload, or log PII.

---

## Real Windows EXE acceptance (human / Windows worker)

1. Place private CV under local `private/cvs/` (gitignored).
2. Enable Günther; ensure Phi GGUF installed.
3. Profile → CV importieren → select file → preview shows Berufserfahrung + Ausbildung.
4. Übernehmen → Speichern → close app → restart → data still present.

Until that run completes on real Windows EXE: **BERUFSERFAHRUNG / AUSBILDUNG / RESTART** real-user gates remain **PENDING**.

---

## STOP

No further architecture rewrite in this package. NEXT-03+ remain separate.
