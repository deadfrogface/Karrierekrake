# HOLDOUT_100 – Frozen Reevaluation V2

Unveränderte Frozen Predictions, neu bewertet mit Scorer V2. Integrität: `FROZEN_PREDICTIONS_INTEGRITY.json` / Verify `ok: true`, 1527 Dateien.

## Tabelle (V1 → V2)

| Pipeline | Alte Accuracy | Neue Accuracy | Alte F1 | Neue F1 | Alte Perfect | Neue Perfect | Ursache der Differenz |
| -------- | ------------: | ------------: | ------: | ------: | -----------: | -----------: | --------------------- |
| A5_det_product | 0.474 | **0.557** | 0.643 | **0.715** | 0/100 | 0/100 | Trap entfernt; Entry-Matching; keine Evidence-lose Target-Role-Strafen |
| A1/A3/A4 (DET-Familie) | 0.474 | 0.557 | 0.643 | 0.715 | 0/100 | 0/100 | Alias derselben Frozen Outputs |
| C1_hybrid_uncertain | **0.525** | 0.548 | **0.689** | 0.708 | 0/100 | 0/100 | Weniger Trap-Wrong-Category; Recall-Vorteil schrumpft unter Evidence-Regeln |
| B4_phi_product_verify | 0.507 | 0.530 | 0.673 | 0.692 | 0/100 | 0/100 | Hallu bleiben dominant |
| B5_phi_split | 0.502 | 0.529 | 0.668 | 0.692 | 0/100 | 0/100 | wie B4 |
| C4/C5 hybrids | 0.507 | 0.530 | 0.673 | 0.692 | 0/100 | 0/100 | wie Phi product |
| B1_phi_only | 0.438 | 0.378 | 0.610 | 0.549 | 0/100 | 0/100 | V2 strenger bei Hallu/Missing; Precision hoch, Recall niedrig |
| D2_pymupdf4llm_det | 0.305 | 0.291 | 0.467 | 0.451 | 0/100 | 0/100 | empty-biased |
| D2_pymupdf4llm_phi | 0.462 | 0.395 | 0.632 | 0.566 | 0/100 | 0/100 | Extractor-Limit |
| Docling / Marker | N/A | N/A | — | — | — | — | nicht installiert |

Quelle: `artifacts/holdout_100/scorer_v1_vs_v2_comparison.json`, `scorer_v2_frozen_results.json`.

## Ranking-Flip

* **V1 Frozen-Sieger:** C1 (F1 0.689)  
* **V2 Frozen-Sieger:** DET A5 (F1 0.715, Acc 0.557)  
* C1 global unter V2: F1 0.708, Acc 0.548 – **unter** DET

## Metriken (DET A5, V2)

| Metric | Wert |
|--------|-----:|
| Field Accuracy | 0.557 |
| Precision | 0.734 |
| Recall | 0.697 |
| F1 | 0.715 |
| Hallucination Rate | 0.200 |
| Missing Field Rate | 0.242 |
| Wrong Category Rate | 0.000 |
| Perfect Document Match | 0/100 |
| Perfect Core Profile Match | 0/100 |

## Feldgruppen (DET A5 V2, korrekte Counts)

Personal 300 · Contact 200 · Address 331 (+169 Fehler) · Languages 154 · Licenses 103 · Education 330 · Employment 500 · Skills 367 (+viele Extras) · Software 0 korrekt bei 400 missing · Certificates 47 · Career intent (target_role) 0/14 evaluable hits on frozen DET.

## Perfect Matches

Weiterhin **0/100** unter Frozen – Testmetadaten waren nicht die Ursache (V1 zählte sie nicht). Verbleibend: echte Extraktionslücken (Software, Skills-Extras, Employment).
