# FINAL HOLDOUT SCORER AUDIT REPORT

## Integrität

| Check | Result |
| ----- | ------ |
| Seal hash | `97c64fb31cf8dfff78e530364a546f759bcaa24f1df899af3844d4a4f8c9075c` OK |
| Prediction hashes | 0 mismatches |
| Predictions unchanged | **ja** |
| Re-extraction | **0** |
| Phi/C1 | **0** |
| Parser code changed | **nein** |

## Reproduktion

Original Phase B reproduced (`artifacts/final_holdout/audit/scorer_original_reproduction.json`):

| Metric | Expected | Reproduced |
| ------ | -------: | ---------: |
| Strict Acc (label) | 0.737 | 0.737 |
| Normalized Acc | 0.674 | 0.674 |
| Precision | 0.877 | 0.877 |
| Recall | 0.744 | 0.744 |
| F1 | 0.805 | 0.805 |
| Hallu | 0.071 | 0.071 |
| Languages F1 | 0.000 | 0.000 |
| Perfect | 0/50 | 0/50 |

## Normalized vs Strict

**Cause:** different fact universes.

* Phase-B “Strict” = scalar subset (~482 facts) exact/casefold → Acc 0.737  
* Phase-B “Normalized” = full Scorer V2 (~1648 facts) → Acc 0.674  

Same-universe `strict_match=true ∧ normalized=false`: **0** cases  
(`artifacts/final_holdout/audit/strict_true_normalized_false.json`).

**Fix:** stop comparing them as two Accuracies; primary metric = Scorer V2 field accuracy; optional `scalar_exact_accuracy_subset` labeled separately.

## Languages F1 0

| | |
|--|--|
| Predictions contain languages? | **nein** (0/50) |
| Ground Truth contains languages? | **ja** (50/50, 100 pairs) |
| Schema mapping | `languages` ↔ `languages` via `match_language_pairs` / `canonicalize_language_item` |
| Cause | **REAL_PARSER_ERROR** — empty `languages[]`; text only in `raw_text_preview` / education bleed |
| Corrected Languages F1 | **0.000** (unchanged — cannot invent languages in scorer) |

Traces: `artifacts/final_holdout/audit/language_comparison_traces.json`

## Feldmapping

See `artifacts/final_holdout/audit/field_mapping_audit.json` and `docs/project/FINAL_HOLDOUT_SCORER_AUDIT.md`.

## Ground Truth

* Original file **unchanged**
* Language names sampled: predominantly `GROUND_TRUTH_CONFIRMED` (visible in PDF text)
* `career_notes`: `SCHEMA_EXTENSION_FIELD`
* Review: `artifacts/final_holdout/audit/ground_truth_review.json`

## FH_011

* Classification: **REAL_PARSER_ERROR**
* Prediction contains education `{qualification: "Elternzeit"}`
* Scorer did not invent it or map from GT career_notes
* Trace: `artifacts/final_holdout/audit/fh011_elternzeit_trace.json`

## Layout class 10

* 3 documents; weak for same real parser reasons (languages empty, employment sparse, skill extras); includes FH_011 critical case
* Not primarily scorer-driven
* `artifacts/final_holdout/audit/layout_class_10_audit.json`

## Korrigierte Metriken (audited rescore)

| Metrik | Phase B | Audited | Diff | Ursache |
| ------ | ------: | ------: | ---: | ------- |
| Strict Accuracy (label) | 0.737 | — | — | Relabeled; not a full-universe Acc |
| scalar_exact_accuracy_subset | 0.737 | 0.737 | 0 | Same scalar subset |
| Scorer V2 / Normalized Acc | 0.674 | 0.674 | 0 | Empty-level fix irrelevant without language preds |
| Precision | 0.877 | 0.877 | 0 | |
| Recall | 0.744 | 0.744 | 0 | |
| F1 | 0.805 | 0.805 | 0 | |
| Hallucination | 0.071 | 0.071 | 0 | |
| Perfect Docs | 0/50 | 0/50 | 0 | |
| Perfect Core | 0/50 | 0/50 | 0 | |
| Languages F1 | 0.000 | 0.000 | 0 | Real empty predictions |
| kritische Fehler | 1 | 1 | 0 | FH_011 Elternzeit |

Artifacts: `artifacts/final_holdout/audit/scorer_audited_results.json` (+ per_document / field_group / slice).

## Echte Parserfehler

* Reclassified events: **538 REAL_PARSER_ERROR**, 0 scorer/GT false failures for core score gap  
* Top groups: employment, skills, education, languages, address  
* Details: `docs/project/FINAL_HOLDOUT_REAL_PARSER_FAILURES.md`

## Scorerfehler behoben (allgemein)

1. Empty language level false match (`"" in "c2"`)  
2. Language object aliases (`name`/`proficiency`)  
3. `date_of_birth` ↔ `dob` evidence alias  
4. Metric naming clarification  

Unit tests: `tests/test_final_holdout_scorer_audit.py` (30) + existing V2 tests.

## Schlussfolgerung

`RESULT: AUDITED INDEPENDENT FINAL HOLDOUT BELOW 99 %`

Independent sealed quality remains ~Acc 0.674 / F1 0.805 / hallu 0.071 / Perfect 0/50.  
The Phase-B scare (Normalized < Strict, Languages F1 0) is **explained**: metric universe mismatch + real empty language extraction — **not** a scorer sabotage of good predictions.

**No parser change in this audit.**  
**Next step:** separate Post-Analysis on real parser failures (languages, employment, skill extras, Elternzeit-as-education), then a **new** independent holdout for any ≥99% claim.
