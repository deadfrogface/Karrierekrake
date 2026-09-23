# FINAL HOLDOUT — REAL PARSER FAILURES

After scorer audit: **538/538** Phase-B error events remain `REAL_PARSER_ERROR`.  
Scorer/schema issues do **not** explain the independent holdout gap to 99%.

Predictions: sealed `artifacts/final_holdout/frozen_predictions/` (unchanged).

## Critical

| Document | Field | Expected | Actual | Class | Evidence | Suspected root cause | Severity |
| -------- | ----- | -------- | ------ | ----- | -------- | -------------------- | -------- |
| FH_011 | education_extra | (none) | qualification=`Elternzeit` | invented education | prediction.education | life-event / career note classified as education | **critical** |

## Systemic

### Languages (F1 0.000)

* All 50 predictions: `languages: []`
* GT: 100 pairs; names present in `raw_text_preview`
* Often language lines absorbed into education blobs (32 name hits)
* **Fix direction (later):** general language-section / CEFR line extraction; keep C1 licence ≠ C1 language

### Employment (F1 ~0.38)

* Only 4/50 predictions have non-empty `work_experience`
* GT employment visible; mostly FN
* **Fix direction:** recover employment records from experience sections without inventing employers

### Skills (hallu ~0.34)

* 116 hallucinated skill extras
* Wrap/section-bleed / responsibility tokens
* **Fix direction:** general skill token filters; no document-specific rules

### Education

* Fused `qualification \| institution` strings
* Wrong institution from section headers / language blocks
* **Fix direction:** split qual vs institution; stop header bleed

### Address

* Street often includes house number; country often missing
* Partially mitigated by Scorer V2 house-number recovery; remaining gaps are parser

## Weakest layout slice

`layout_class:10` (3 docs: FH_011, FH_026, FH_041) — same systemic gaps, not a unique scorer pathology. Includes the critical Elternzeit case.

## Explicitly not fixed here

No parser code changes in the scorer-audit turn.
