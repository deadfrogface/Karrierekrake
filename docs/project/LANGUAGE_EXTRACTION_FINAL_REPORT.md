# Language Extraction Final Report (POST-ANALYSIS)

## Ausgangspunkt

| Metric | Frozen Final-Holdout (immutable) |
| --- | ---: |
| Accuracy | 0.674 |
| F1 | **0.805** |
| Languages F1 | **0.000** |
| Perfect Core Profiles | 0/50 |
| Hallucination Rate | 0.071 |
| Critical FH_011 | Elternzeit as education |

Frozen predictions, seal, and Phase-A/B artifacts were **not** overwritten.

## Root Cause

Composite headings `Sprachen & Fahrerlaubnis` (45/50) and `Languages & licences` (5/50) were not classified by `is_heading`. Language lines routed into `education`; `_parse_languages` received an empty body. Licences still appeared via full-text regex. See `LANGUAGE_EXTRACTION_ROOT_CAUSE.md`.

## DET Fix

Architecture: Section Detection → mixed Language/Licence body → line classify → language+level pairing → licence harvest → evidence/cross-field → canonical output.

Results (POST-ANALYSIS, 50 CV):

| Metric | Value |
| --- | ---: |
| Language Precision | 1.000 |
| Language Recall | 0.950 |
| Language F1 | **0.974** |
| Pair Accuracy | 0.950 |
| Licence F1 | 0.765 |
| Language Hallucinations | 0 |
| C1 Language/Licence Confusions | 0 |
| Overall F1 | **0.941** |
| Hallucination Rate | **0.006** |
| Zeit/CV | ~15 ms |
| Peak RAM | ~43 MB |

100-CV regression: F1 **0.998** / Perfect **89** — unchanged vs prior best.

## Phi Language-only (offline)

Prompt/schema: languages+licences only; temperature 0; evidence must be verbatim; no production wiring.

| Metric | Value |
| --- | ---: |
| Language F1 | 0.984 (headline) |
| Pair Accuracy | **0.60** |
| Licence F1 | 0.929 |
| Invalid Output Rate | 0.04 |
| Language Hallucinations | 1 |
| Repeatability (5×3) | identical_rate **0.8** |
| Zeit/CV | ~16.1 s |
| Peak RAM | ~5.2 GB |

Headline Language F1 is misleading: Muttersprache often emitted as `level: null` (pair failures). Slightly higher entry-F1 partly mirrors GT duplicate `Englisch` rows.

## Hybrid / Fallback / Arbitration

**Not used.** DET repaired empties the failure class that would trigger Phi. See `fallback_results.json`.

## Vergleich

See table in `LANGUAGE_PIPELINE_COMPARISON.md` and `pipeline_comparison.json`.

## Entscheidung

**`DET ONLY`**

Messbare Begründung: Pair Accuracy 0.95 vs 0.58, Language Precision 1.0, 0 language hallu, ~1000× schneller, 100-CV unverändert, keine Modellabhängigkeit.

## FH_011

Root cause: `Weitere Angaben` / missing `Berufspraxis` + career-break parsed as education.  
Fix: profile/experience aliases + career-break filter + `career_notes`.  
Regression: KEEP (100-CV intact). Details: `FH_011_ROOT_CAUSE_AND_FIX.md`.

## Finale Post-Analysis-Metriken (50 CV, DET)

| Metric | POST-ANALYSIS |
| --- | ---: |
| Accuracy (field) | 0.889 |
| Precision | 0.994 |
| Recall | 0.894 |
| F1 | **0.941** |
| Languages F1 | **0.974** |
| Pair Accuracy | 0.950 |
| Licence F1 | 0.765 |
| Hallucination Rate | **0.006** |
| Perfect Core Profiles | 0/50 |
| Laufzeit | ~15 ms/CV |
| RAM | ~43 MB |

## Ehrliche Einordnung

- Frozen Ergebnis bleibt **F1 0.805 / Languages F1 0.000**.
- Neue Werte sind **POST-ANALYSIS** auf dem Entwicklungs-/Regressionskorpus.
- Für einen erneuten unabhängigen Nachweis ist später ein neuer kleiner Holdout nötig.

## RESULT

`RESULT: DET LANGUAGE PIPELINE WINS`
