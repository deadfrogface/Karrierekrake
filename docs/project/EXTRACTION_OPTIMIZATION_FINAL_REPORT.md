# EXTRACTION_OPTIMIZATION_FINAL_REPORT

```
RESULT: POST-ANALYSIS TARGET ACHIEVED
```

Corpus: **Post-Analysis Development and Regression Corpus** (kein unangetasteter Holdout)  
Branch: `cursor/holdout-100-d85b` · Scorer: V2

## Ausgangspunkt

| Metrik | Wert |
|--------|-----:|
| Accuracy | 0.698 |
| F1 | 0.822 |
| Perfect | 17/100 |
| Hallu | 0.137 |
| Pipeline | DET A5 + Kenntnisse-Routing |
| C1-Fallback | 64/100 Docs, ≈+0.025 F1 |
| Zeit | ~0.01 s/Doc DET |

## Pareto (Ausgang)

Größte Klassen: Skills-Kontamination durch verschluckte Praxis/Bildungsweg, Software missing in Werkzeuge/education, Employment missing, Address. Details: `EXTRACTION_ERROR_PARETO.md`.

## Iterationen

1. **Abschnittsgrenzen** (Praxis/Stationen/Werdegang/Bildungsweg/Schule&Ausbildung) → KEEP · F1 0.940 · Perfect 39  
2. **Skills/Software/Language Cleanup** (+ Romanes) → KEEP · F1 0.949 · Perfect 57  
3. **Werkzeuge-Heading** → KEEP · F1 0.986 · Perfect 67  
4. **Adresse** (Frankfurt (Oder), AT-PLZ, FR) + Wrap-Fragmente → KEEP · F1 **0.998** · Perfect **89**  
   - Aggressive always-continue → REVERT (Hallu)

## Finale Pipeline

| Komponente | Wahl |
|------------|------|
| Extractor | bestehender Text-Extractor (PyMuPDF-Pfad) |
| DET | `parse_cv_text` Heuristik |
| Section Routing | `cv_sections.HEADINGS` inkl. Praxis/Werkzeuge/… |
| Kenntnisse Labels | Software/Fachkenntnisse/Zertifikate/… |
| Record Grouping | bestehende Employment/Education-Parser |
| Validatoren/Evidence | unverändert produktiv |
| Phi/C1 | **kein Default**; C1-Fallback **deaktiviert** (0 geroutete Docs) |

## Finale Metriken (Post-Analysis)

| Metrik | Vorher | Nachher |
|--------|-------:|--------:|
| Accuracy | 0.698 | **0.997** |
| Precision | — | **0.999** |
| Recall | — | **0.998** |
| F1 | 0.822 | **0.998** |
| Perfect Docs | 17 | **89** |
| Hallu | 0.137 | **0.001** |
| Wrong Category | 0 | 0 |
| Missing Rate | 0.163 | ≈0.002 |
| Mean Zeit/Doc | ~0.01 s | ~0.01 s |

## Feldgruppen

Personal/Contact: stabil korrekt · Address: 0 Fehler · Employment/Education: nach Abschnittsfix vollständig · Languages: nach Werkzeuge/Romanes ok · Skills/Software: Restfragmente · Certificates: 1 Extra.

## C1/Phi

| | Ergebnis |
|--|----------|
| Thin-Routing nach DET-Fix | **0/100** |
| Entscheidung | **DISABLE_C1_FALLBACK** |
| Phi | kein globaler Mehrwert → kein Default |

## Remaining Failures

Siehe `POST_ANALYSIS_REMAINING_FAILURES.md` (11 Docs, meist Einzel-Skill-Fragmente).

## Ehrliche Aussage

Kein globaler Accuracy-Claim. Die 100 CVs sind Entwicklungs-/Regressionstests. Für einen unabhängigen Nachweis braucht es einen neuen, unangetasteten Satz (~30–50 CVs).

## Artefakte

- `artifacts/holdout_100/extraction_error_pareto.json`
- `artifacts/holdout_100/extraction_optimization_history.json`
- `artifacts/holdout_100/iter1_…` … `iter4_…`
- `artifacts/holdout_100/final_c1_fallback_analysis.json`
- `artifacts/holdout_100/final_per_document_results.json`
- `artifacts/holdout_100/final_pipeline_comparison.json`
