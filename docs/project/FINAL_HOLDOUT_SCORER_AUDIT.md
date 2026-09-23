# FINAL HOLDOUT SCORER AUDIT

## Scope

Audit of Phase-B scoring for sealed Final Holdout (50 CVs).  
**No parser changes. No re-extraction. Predictions unchanged.**

## Entrypoints

| Role | Path |
| ---- | ---- |
| Phase B eval | `scripts/run_final_holdout_phase_b_eval.py` |
| Scorer | `scripts/holdout_scorer_v2.py` |
| GT | `tests/final_holdout/phase_b_solutions/expected_results.json` |
| Predictions | `artifacts/final_holdout/frozen_predictions/FH_*.json` |

## Findings summary

1. **Normalized Acc (0.674) < Strict Acc (0.737)** is a **metric labeling bug**, not normalization destroying matches.
2. **Languages F1 = 0** is a **real parser failure**: all 50 sealed predictions have `languages: []`.
3. **FH_011 Elternzeit** is a **real parser** education hallucination, not a scorer projection of `career_notes`.
4. Scorer V2 matching itself is largely sound; one real bug fixed: empty language level matched via Python `"" in "c2"`.

## Normalized vs Strict

Phase B defined:

* **Strict Accuracy** = `strict_scalar_stats()` — only personal/contact/address/dob (~482 facts)
* **Normalized Accuracy** = Scorer V2 `field_accuracy` — all evaluable fields (~1648 facts)

Same-universe check: `strict_true ∧ ¬normalized` count = **0**.

Therefore the inequality came only from **different denominators** (harder full field set includes 100 language FNs, employment FNs, skill FPs).

**Correct reporting:**

* Primary: `scorer_v2_field_accuracy` / F1 / hallu  
* Secondary (optional): `scalar_exact_accuracy_subset` — must not be compared as Strict vs Normalized Accuracy

## Languages F1 = 0

| Inventory | Count |
| --------- | ----: |
| GT docs with languages | 50 |
| GT language pairs | 100 |
| Prediction docs with `languages[]` | **0** |
| Prediction language pairs | **0** |
| Exact raw pairs matched | 0 |
| Names visible in `raw_text_preview` | 100 |
| Names bleeding into `education` strings | 32 |

Conclusion: **REAL_PARSER_ERROR**. Scorer correctly emits 100 missing. Adapter for tuple↔object is present but irrelevant when predictions are empty.

## Field mapping

See `artifacts/final_holdout/audit/field_mapping_audit.json`.

Notable adapters (eval / scorer):

* `employment` ← `work_experience` via `pred_view`
* `licenses` ← `driving_license`
* `date_of_birth` → `dob` (now in Scorer V2 evidence builder)
* `career_notes` → SCHEMA_EXTENSION (excluded from core)

## Schema extensions

`career_notes` excluded from core metrics. Documented separately.

## Scorer fixes applied (evaluation only)

1. `canonicalize_language_item` — name/proficiency aliases  
2. Empty actual language level no longer false-matches via `"" in level`  
3. `date_of_birth` alias for `dob` in evidence builder  
4. Metric renaming documentation (no silent Acc inflation)

## Unit tests

`tests/test_final_holdout_scorer_audit.py` (+ existing `tests/test_holdout_scorer_v2.py`)
