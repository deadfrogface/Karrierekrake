# HOLDOUT_100_INITIAL_RESULTS

**Status:** FROZEN HOLDOUT — nicht überschreiben.  
**Commit (predictions):** `d0b477f` / branch work `cursor/holdout-100-d85b` @ prediction harness `42cdbbb`  
**Generated:** 2026-09-22 (UTC)  
**Documents:** 100 synthetic CVs (`tests/holdout_100/cvs/`)  
**GT read only after** predictions sealed under `artifacts/holdout_100/frozen_baseline_predictions/`.

## Metadata

See `artifacts/holdout_100/FROZEN_BASELINE_METADATA.json` and timestamped sibling after Phi phase.

## Pipelines executed

| Pipeline | Status | Notes |
|----------|--------|-------|
| A1_det_raw | OK | parse only |
| A3_det_evidence | OK | + language evidence |
| A4_det_verify_repair | OK | + verify/repair |
| A5_det_product | OK | `import_cv(guenther=False)` |
| B1_phi_only | OK | Phi map without DET structure |
| B4_phi_product_verify | OK | `import_cv(guenther=True)` + split |
| B5_phi_split | OK | explicit split path |
| C1_hybrid_uncertain | OK | Phi only if DET thin |
| C4/C5 | ALIAS | identical to B4 |
| D2_pymupdf4llm_det | OK | |
| D2_pymupdf4llm_phi | OK | |
| D3_docling_* | NOT_AVAILABLE | docling not installed |
| D4_marker | NOT_AVAILABLE | not installed |

## Frozen metrics (first GT evaluation)

Weighting for `quality_score`: hallucination×5 + wrong_category×4 + wrong×3 + missing×1 (documented a priori in evaluator).

| Rank | Pipeline | Field Acc | F1 | Hallu Rate | Wrong Cat | Perfect Docs | Crit Docs | Avg s/doc | Quality |
| ---: | -------- | --------: | -: | ---------: | --------: | -----------: | --------: | --------: | ------: |
| 1* | D2_pymupdf4llm_det | 0.305 | 0.467 | **0.000** | 0.000 | 0/100 | 0 | 0.11 | 0.768 |
| 2 | B1_phi_only | 0.438 | 0.610 | 0.118 | 0.030 | 0/100 | 93 | 26.9 | 0.624 |
| 3 | D2_pymupdf4llm_phi | 0.462 | 0.632 | 0.159 | 0.026 | 0/100 | 89 | 51.3 | 0.583 |
| 4–7 | A1/A3/A4/A5 DET | **0.474** | 0.643 | 0.231 | 0.011 | 0/100 | 42 | ~0.01 | 0.504 |
| **8** | **C1_hybrid_uncertain** | **0.525** | **0.689** | 0.281 | 0.026 | 0/100 | 98 | 21.1 | 0.441 |
| 9 | B5_phi_split | 0.502 | 0.669 | 0.300 | 0.024 | 0/100 | 93 | 45.8 | 0.409 |
| 10–12 | B4/C4/C5 | 0.507 | 0.673 | 0.305 | 0.025 | 0/100 | 99 | 50.5 | 0.403 |

\* D2_DET quality lead is **empty-extraction bias** (almost only `missing`, zero hallu). Not a usable production winner.

## Honest winners (Frozen)

| Category | Winner | Rationale |
|----------|--------|-----------|
| Highest accuracy / F1 | **C1_hybrid_uncertain** | Acc 0.525 / F1 0.689 |
| Lowest usable hallucination among content-producing pipes | **B1_phi_only** | Hallu 0.118 (vs DET 0.231) |
| Best speed | **A5_det_product** (≈A1–A4) | ~0.01 s/doc |
| Best accuracy/speed compromise | **A5_det_product** | Fast; F1 0.643; fewer crit docs than Phi hybrids |
| Best low-end hardware | **A5_det_product** | No model load |
| Recommended standard (frozen) | **A5_det_product** | Pending post-analysis skill/software fixes |
| Recommended fallback (frozen) | **C1_hybrid_uncertain** | When DET education/languages/work empty |

## Dominant frozen error classes (A5)

1. **skills extras / software missing** — section labels (`Software:`, `Fachkenntnisse:`) and tools landed in `skills`; `software[]` empty → mass missing+hallucinated.
2. **address.country** often missing.
3. **education** incomplete (multi-entry).
4. **target_role** sometimes appears as employment (trap).
5. **certificates** polluted by education fragments.

## Perfect document rate

**0/100** for all pipelines on this strict field-wise evaluation.

## Claim discipline

```
100-CV synthetic frozen holdout result
no global accuracy claim without an additional untouched private-CV holdout
RESULT: FROZEN HOLDOUT BELOW 99 %
```

Field accuracy best content pipeline ≈ **52.5 %** (C1), DET ≈ **47.4 %**. Far below 99 %.

## Next

Post-analysis generalizable fixes (skill/software separation, education multi-parse, license normalize) → `POST-ANALYSIS REGRESSION RESULT` (not a second independent holdout).
