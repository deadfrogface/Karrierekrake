# POST_ANALYSIS_REMAINING_FAILURES

Pipeline: `A5_det_product_v6_address` · Scorer V2 · Perfect **89/100** · F1 **0.998**

## Fehlerverteilung

| Fehler/Doc | Docs |
|-----------:|-----:|
| 0 | 89 |
| 1 | 9 |
| 2 | 2 |

## Verbleibende Klassen

| Klasse | n | Root Cause | Nächster Schritt | LoRA? |
|--------|--:|------------|------------------|------:|
| skills missing | 9 | Wrap/Label-Lücken bei Mehrwort-Skills | Zusätzliche Wrap-Heuristik nur mit Regression | eher nein |
| software hallucinated | 3 | Produktfragmente / Duplikat-Teile | Fragment-Dedup erweitern | nein |
| certificates hallucinated | 1 | Sicherheitsunterweisung-Fragment | Dedup gegen längeren Cert-Namen | nein |

Keine Employment-/Education-/Address-/Language-Fehler mehr auf diesem Corpus.

## Nicht als Frozen Holdout ausweisen

Dies ist ein **Post-Analysis Development/Regression**-Ergebnis. Für eine unabhängige ≥99 %-Behauptung braucht es ~30–50 unangetastete CVs.
