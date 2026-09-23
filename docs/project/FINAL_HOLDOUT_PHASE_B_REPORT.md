# FINAL HOLDOUT — PHASE B REPORT

**Status:** Independent sealed evaluation complete  
**Overall:** Target **not** met  

`RESULT: INDEPENDENT FINAL HOLDOUT BELOW 99 %`

## Integrität

| Check | Result |
| ----- | ------ |
| Phase-A seal hash | `97c64fb31cf8dfff78e530364a546f759bcaa24f1df899af3844d4a4f8c9075c` — **match** |
| PDF hashes | OK (0 mismatches) |
| Prediction hashes | OK (0 mismatches) — predictions **unchanged** |
| Re-extraction (`import_cv` / `parse_cv_text`) | **0** |
| Phi / C1 / Writer calls | **0** |
| Parser changes in Phase B | **0** |
| Ground-truth changes | **0** |
| Scorer | `scripts/holdout_scorer_v2.py` (unchanged V2) |
| Evidence text | `extract_text` used **only** for Scorer-V2 evaluability (same method as Holdout-100); not used to regenerate predictions |

Integrity artifact: `artifacts/final_holdout/PHASE_B_INTEGRITY.json`

## Datensatz

| Item | Value |
| ---- | ----- |
| Documents | 50 (`FH_001` … `FH_050`) |
| Ground truth | `tests/final_holdout/phase_b_solutions/expected_results.json` |
| Metadata | excluded from Accuracy/F1 (`document_language`, `layout_class`, …) |
| Schema extension | `career_notes` — separate report only |
| Languages (docs) | de: 45 · en: 5 |
| Source type | born_digital: 50 |

## Gesamtmetriken (Scorer V2)

| Metric | Value |
| ------ | ----: |
| Strict scalar accuracy (exact casefold) | 0.737 |
| Normalized field accuracy | **0.674** |
| Precision | 0.877 |
| Recall | 0.744 |
| F1 | **0.805** |
| Hallucination rate | **0.071** |
| Missing field rate | 0.232 |
| Wrong category rate | 0.000 |
| Perfect documents | **0 / 50** |
| Perfect core profiles | **0 / 50** |
| Documents with ≥1 error | 50 |
| Documents with critical-classified events | see critical section |
| Field facts scored | 1648 |

### Counts

| Status | n |
| ------ | -: |
| correct | 1110 |
| missing | 382 |
| hallucinated | 117 |
| wrong | 39 |
| wrong_category | 0 |

### Target checks

| Criterion | Pass? |
| --------- | ----: |
| Accuracy ≥ 0.99 | no |
| F1 ≥ 0.99 | no |
| Hallucination ≤ 0.01 | no |
| No critical invented employment/education/qualifications/personal | **no** (1 invented education: `Elternzeit` as education on FH_011) |

## Feldgruppen (F1)

| Group | Accuracy | F1 | Hallu | n |
| ----- | -------: | -: | ----: | -: |
| licenses | 1.000 | 1.000 | 0.000 | 52 |
| contact | 0.969 | 0.984 | 0.000 | 96 |
| certificates | 0.960 | 0.980 | 0.000 | 50 |
| software | 0.960 | 0.979 | 0.000 | 173 |
| personal | 0.959 | 0.979 | 0.000 | 145 |
| address | 0.676 | 0.807 | 0.000 | 241 |
| education | 0.642 | 0.782 | 0.003 | 296 |
| skills | 0.658 | 0.794 | 0.342 | 339 |
| employment | 0.232 | 0.377 | 0.000 | 155 |
| languages | 0.000 | 0.000 | 0.000 | 100 |
| career_intent | 0.000 | 0.000 | 0.000 | 1 |

**Weakest productive group:** languages (0/100 language pairs extracted in sealed predictions).

## Slices (selected)

See `artifacts/final_holdout/slice_metrics.json` for full table.

Notable:

* `lang:de` / `lang:en` evaluated separately
* `employment:1` vs `employment:multi`
* `contact:complete` vs `contact:missing_or_partial`
* `c1_context`, `target_role:present|absent`, `career_notes:present`
* `layout_class:0` … `14` (numeric layout IDs from metadata)

**Weakest slice (by F1, ≥20 facts):** `layout_class:10`

## Perfect-Match-Verteilung

| Bucket | Documents |
| ------ | --------: |
| 0 Fehler | 0 |
| 1 Fehler | 0 |
| 2 Fehler | 0 |
| 3–5 Fehler | 3 |
| >5 Fehler | 47 |

## Kritische Fehler

* **1** hallucinated education record: `FH_011` — predicted qualification `Elternzeit` (career note / life event) as education.
* Additional **wrong** education/employment field assignments (institution/position mismatches) are listed in `critical_errors.json` / `error_inventory.json` (wrong ≠ invented, but severity high).

No invented employment company/position records were scored as hallucinated extras in this run (employment errors were primarily **missing**).

## Vergleich zum Entwicklungsdatensatz

| Corpus | Role | Acc | F1 | Perfect | Hallu |
| ------ | ---- | --: | -: | ------: | ----: |
| Holdout-100 Post-Analysis DET | development / regression after analysis | 0.997 | 0.998 | 89/100 | 0.001 |
| Final Holdout 50 (this Phase B) | **independent sealed frozen** | 0.674 | 0.805 | 0/50 | 0.071 |

These are **not** methodologically equivalent. The 100-CV figure is not an independent proof.

## Ehrliche Schlussfolgerung

Auf dem unabhängigen synthetischen Final-Holdout wurden **nicht** ≥99 % erreicht.

Hauptlasten in den versiegelten Predictions:

1. Languages: systematically empty → 100 missing language facts  
2. Employment: mostly missing structured records  
3. Skills: many hallucinated extras (fragment / wrap style)  
4. Education: frequent institution/qualification mismatch; one critical career-note-as-education  

**Keine Parseränderung in Phase B.** Keine Prediction neu erzeugt. Keine globale Qualitätsgarantie.

Nächster Schritt (separater Auftrag): Post-Analysis Hypothesen aus `FINAL_HOLDOUT_REMAINING_FAILURES.md` — neuer unabhängiger Holdout wäre für erneuten ≥99 %-Nachweis nötig.
