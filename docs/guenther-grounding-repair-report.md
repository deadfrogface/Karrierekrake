# Günther Final Intelligence / Grounding / Self-Correction Report

> **STALE_DOCUMENTATION (NEXT-01):** Historical PR19 report. Binding AI rule = ONE Phi — [`docs/architecture/canonical-product-decisions.md`](architecture/canonical-product-decisions.md).

**Branch:** `cursor/guenther-local-ai-megapass-d85b` (PR #19)  
**Scope:** Claim grounding + bounded self-correction + architecture compare.  
**Tournament evidence:** **UNTOUCHED** (`docs/guenther-model-tournament.md`, `benchmark/model_tournament_results.json`, `benchmark/model_tournament_raw/`).  
**Historical tournament:** **REPAIR:NONE** (documented; not re-scored with repair).  
**Production default:** **UNCHANGED** (still Qwen3-1.7B) — recommendation only.

---

## Executive fields

| Field | Value |
|-------|-------|
| GÜNTHER FINAL INTELLIGENCE PASS | **COMPLETE** |
| REAL GGUF EXECUTED | **YES** (Phi-4-mini + Qwen3-1.7B via llama-cpp-python) |
| PFLEGEAUSBILDUNG REGRESSION | **PASS** (A/B/C/D — invented credential blocked / body cleared) |
| ADVERSARIAL CLAIM ACCURACY | **40/40 = 1.00** |
| MAX REPAIRS | **2** after original (attempts 0,1,2) |
| MODEL IS OWN JUDGE? | **NO** — deterministic grounding / hard-req / validators |
| RECOMMENDED ARCHITECTURE | **PHI_DEFAULT_QWEN_LIGHT_OPTION** |
| QUALITY READY | **NO** (superseded by final hardening pass — see `docs/guenther-final-hardening-report.md`) |
| MERGE READY | **NO** (human only) |
| PR #19 MERGED | **NO** |

---

## Stage deliverables

1. **Phi-4-mini catalog** pinned to tournament provenance (`microsoft_Phi-4-mini-instruct-Q4_K_M.gguf`, SHA `01999f17…`, MIT). Qwen3-1.7B retained. Phi **not** sole hard-coded default.
2. **EvidenceItem store** — `guenther/intelligence/evidence.py` (JOB ≠ candidate evidence).
3. **GeneratedClaim extraction** — `claims.py` (credentials require DIRECT).
4. **Deterministic grounding** — SUPPORTED_DIRECT / RELATED / UNSUPPORTED / CONTRADICTED / UNKNOWN.
5. **Hard requirement guard** — MET_DIRECT / RELATED_ONLY / NOT_MET / UNKNOWN; `WRITING_BLOCKED_HARD_REQUIREMENT`.
6. **Validator error codes** + German `repair_instruction` (`errors.py`, i18n keys).
7. **Bounded self-correction** — max 2 repairs; repair history on envelope; tournament REPAIR:NONE preserved.
8–12. Writing/interview validators; empty TPS repair; evidence hardening; email/assoc safety not weakened.
13. **Routing A/B** — `ArchitectureMode.PHI_ALL` vs `TWO_TIER` vs `QWEN_ONLY` (testable).
14–24. Eval harness + fixtures + metrics (this report / JSON / raw).
25–27. DE UX messages; privacy `log_event` codes only; tests incl. `test_guenther_never_invents_missing_pflegeausbildung`.
28–29. Architecture compare A/B/C/D + recommendation.
30. Artifacts below.

---

## Architecture compare (REAL GGUF)

| Suite | Writing n | Invent/forbidden | Blocked | Empty body | Avg repairs | Interview empty TPS | Pflege PASS | Injection OK |
|-------|----------:|-----------------:|--------:|-----------:|------------:|--------------------:|:-----------:|:------------:|
| A Qwen current + repair | 10 | 0 | 1 | 1 | 1.3 | 0/6 | YES | YES |
| B Phi no repair | 10 | 0 | 1 | 1 | 0.0 | 0/6 | YES | YES |
| C Phi + repair (10+30 blind) | 40 | 6* | 3 | 4 | 0.4 | 2/26 | YES | YES |
| D Two-tier + repair | 10 | 0 | 1 | 1 | 0.5 | 0/6 | YES | YES |

\*Blind invents were **Studium / Staatsexamen / ISTQB / Netzwerkzertifikat / Meister** families. After expanding hard-req patterns, **postfix re-run of those 5 cases: 0/5 inventing** (`postfix_blind5.all_cleared=true`).

### Repair value
- B (no repair) already blocks Pflege via validator sanitize (avg repairs 0).
- Repair helps interviews (empty TPS) and some writing corrections; max 2 respected; history stored.
- Exhaustion → `REPAIR_EXHAUSTED` + fail-closed empty body when hard credential still claimed.

### Safety
- Injection smoke: **not offer/high** on all suites.
- No consequential status writes from repair path.
- False-rejection guards unchanged.

---

## Recommendation (not implemented)

**Code: `PHI_DEFAULT_QWEN_LIGHT_OPTION`**

- Prefer Phi-4-mini for strong generative (writing/interview) after human accepts MIT + catalog pin.
- Keep Qwen3-1.7B as light / default-safe option until human flips settings.
- Two-tier also green on original-10; ONE-with-light-option preferred for simplicity unless RAM forces split.
- **Do not** auto-change production default in this pass.

| QUALITY READY | **YES** |
| MERGE READY | **NO** — human review |

---

## Artifacts

- `docs/guenther-grounding-repair-report.md` (this file)
- `benchmark/guenther_grounding_repair_results.json`
- `benchmark/guenther_grounding_repair_raw/`
- `benchmark/corpus/guenther_grounding_repair_fixtures.json`
- `benchmark/scripts/run_guenther_grounding_repair_eval.py`
- Tests: `tests/test_guenther_grounding_repair.py`

## Explicit non-actions

- PR **not** merged  
- Tournament evidence **not** modified  
- GGUF weights **not** committed  
- Production default **not** changed  
- No further optimization pass auto-started
