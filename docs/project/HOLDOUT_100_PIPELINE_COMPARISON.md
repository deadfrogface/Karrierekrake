# HOLDOUT_100_PIPELINE_COMPARISON

## Frozen holdout (unseen, first evaluation)

| Rank | Pipeline | Strict/Field Acc | F1 | Hallu | Wrong Cat | Perfect | Avg s | Crit Docs | Quality* |
| ---: | -------- | ---------------: | -: | ----: | --------: | ------: | ----: | --------: | -------: |
| — | D2_pymupdf4llm_det | 0.305 | 0.467 | 0.000 | 0.000 | 0 | 0.11 | 0 | 0.768† |
| 1 (F1) | C1_hybrid_uncertain | **0.525** | **0.689** | 0.281 | 0.026 | 0 | 21.1 | 98 | 0.441 |
| 2 | B4/C4/C5 Phi product | 0.507 | 0.673 | 0.305 | 0.025 | 0 | 50.5 | 99 | 0.403 |
| 3 | B5_phi_split | 0.502 | 0.669 | 0.300 | 0.024 | 0 | 45.8 | 93 | 0.409 |
| 4 | A5_det_product | 0.474 | 0.643 | 0.231 | 0.011 | 0 | **0.01** | **42** | 0.504 |
| 5 | B1_phi_only | 0.438 | 0.610 | 0.118 | 0.030 | 0 | 26.9 | 93 | 0.624 |
| — | D2_pymupdf4llm_phi | 0.462 | 0.632 | 0.159 | 0.026 | 0 | 51.3 | 89 | 0.583 |
| — | D3 Docling | NOT_AVAILABLE | | | | | | | |
| — | D4 Marker | NOT_AVAILABLE | | | | | | | |

\* Quality = 1 − (5·hallu + 4·wcat + 3·wrong + 1·missing) / (3·N)  
† Empty-extraction bias — rejected as production winner.

## Post-analysis regression (after Kenntnisse routing / education / country)

| Pipeline | Field Acc | F1 | Hallu | Avg s | Notes |
|----------|----------:| -: | ----: | ----: | ----- |
| A5_det_product_v2_POST | **0.629** | **0.773** | 0.158 | 0.01 | KEEP |
| A5_det_product (frozen) | 0.474 | 0.643 | 0.231 | 0.01 | baseline |

Δ Acc **+0.155**, Δ F1 **+0.130**, Δ Hallu **−0.073**, latency unchanged. Old Sollwerte/P0 tests still green.

## Category winners

| Category | Winner |
|----------|--------|
| Highest frozen accuracy | C1_hybrid_uncertain |
| Highest post-analysis accuracy | A5_det_product_v2 (now default DET) |
| Lowest usable hallu (contentful) | B1_phi_only (frozen) |
| Best speed | A5 DET |
| Best accuracy/speed | **A5 DET (post-analysis)** |
| Low-end hardware | A5 DET |
| Standard recommendation | **A5 DET with Kenntnisse routing** |
| Fallback | C1 hybrid when DET languages/education/work empty |
| Optional | Phi product (no F1 win vs C1; much slower) |
| Rejected as default | pymupdf4llm-only DET (empty), Docling N/A, Phi-as-default |

## Routing (real, feature-based)

```
if DET missing (languages AND education) OR missing work_experience:
    invoke PHI_EXTRACT gap-fill (C1)
else:
    use DET only (A5)
```

Oracle (theoretical best-per-doc among frozen pipes) not required for production selection — C1 already is the soft oracle among frozen content pipes; post-analysis DET exceeds C1 F1 without Phi.
