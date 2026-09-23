# HOLDOUT_100_FINAL_REPORT

## Test environment

| Item | Value |
|------|-------|
| Branch | `cursor/holdout-100-d85b` |
| Frozen prediction commit (approx) | harness `42cdbbb` + prior phi-extract tip |
| Corpus | `tests/KarriereKrake_HOLDOUT_100.zip` → `tests/holdout_100/` (100 PDFs) |
| Model | phi4-mini, temp=0 for extract |
| Docling / Marker | NOT_AVAILABLE |
| Hardware | Linux cloud agent CPU (see FROZEN_BASELINE_METADATA*.json) |

## Frozen Baseline

See `docs/project/HOLDOUT_100_INITIAL_RESULTS.md` (immutable narrative).

- Best frozen F1: **C1_hybrid_uncertain 0.689** (Acc 0.525)
- DET Acc 0.474 / F1 0.643 @ ~0.01 s/doc
- Phi product slower, higher hallu, not better than C1 on F1
- pymupdf4llm DET: empty-biased, rejected
- Perfect docs: **0/100**

```
RESULT: FROZEN HOLDOUT BELOW 99 %, POST-ANALYSIS IMPROVEMENT COMPLETED
100-CV synthetic frozen holdout result
100-CV post-analysis regression result
no global accuracy claim without an additional untouched private-CV holdout
```

## Post-Analysis Improvements (KEEP)

Generalizable DET fixes (no filename/name hardcoding):

1. Labeled `Kenntnisse` routing (`Software:`, `Fachkenntnisse:`, `Zertifikate:`, `Führerschein:`, `Berufswunsch:`)
2. Education open end `ohne Abschluss`
3. ISO country codes on DE address lines
4. Certificate vs education-year-range guard

**A5 post-analysis:** Acc **0.629** / F1 **0.773** / Hallu **0.158** / ~0.01 s  
Old regression suite: PASS.

## Recommended architecture

| Role | Pipeline |
|------|----------|
| **STANDARD** | DET product (A5) with new Kenntnisse routing |
| **FALLBACK** | C1 hybrid (Phi only if DET lacks languages/education/work) |
| **OPTIONAL** | Full Phi product / split (no default — cost without frozen F1 win over C1) |
| **REJECTED default** | pymupdf4llm-as-sole-text, Docling (N/A), Phi-always-on |

## Scores to report

| Metric | Frozen best content | Post-analysis DET |
|--------|--------------------:|------------------:|
| Field Accuracy | 0.525 (C1) | **0.629** |
| F1 | 0.689 (C1) | **0.773** |
| Perfect Docs | 0/100 | 0/100 |
| vs 99% target | **miss** | **miss** |

Frozen Holdout Score (best F1): **0.689**  
Post-Analysis Score (DET F1): **0.773**  
Winner pipeline (production): **DET A5 + labeled Kenntnisse routing**  
Critical residual: skills/software/employment gaps, 0 perfect docs  

## Artifacts

- `artifacts/holdout_100/frozen_baseline_predictions/` (sealed)
- `artifacts/holdout_100/pipeline_results.json`
- `artifacts/holdout_100/error_inventory.json`
- `artifacts/holdout_100/iteration_history.json`
- `docs/project/HOLDOUT_100_*.md`
