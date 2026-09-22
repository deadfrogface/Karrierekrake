# HOLDOUT_100 – Remaining Failures V2

Bewertung: Scorer V2 auf Frozen DET A5 sowie Post-Analysis A5_v2. Keine Frozen-Prediction geändert.

## Frozen DET A5 – größte Fehlerklassen

| Klasse | Status | n (ca.) | Einordnung |
|--------|--------|--------:|------------|
| `skill_extra` | hallucinated | 814 | echte Parser-Halluzination / Over-Extraction |
| `software` | missing | 400 | sichtbare Tools oft ohne `Software:`-Label |
| `employment_entry` | missing | 150 | Layouts / Matching-Restfehler nach bipartitem Match |
| `skill` | missing | 133 | Recall-Lücke |
| `address.country` | missing | 96 | oft nur implizit DE |
| `education_entry` | missing | 59 | offene Enden / ungewöhnliche Formulierungen |
| `certificate` | missing | 49 | Routing/Kategorie |
| `language` | missing | 46 | Nonstandard-Sprachsektionen |
| `target_role` | missing | 14 | nur evidence-gated Docs; Frozen DET liefert selten |

Details: `artifacts/holdout_100/remaining_failures_v2_summary.json`, Fehlerliste in `scorer_v2_frozen_errors.json`.

## Post-Analysis A5_v2 (Kenntnisse-Routing)

* Acc **0.698** / F1 **0.822** / Perfect **17/100** (V2)
* Software und Zertifikate stark verbessert; Skills-Hallu sinkt, bleibt aber führend
* **POST-ANALYSIS REGRESSION RESULT** – nicht als Frozen Holdout ausweisen

## Schema-Gaps / GT

* `target_role` produktiv eher SearchIntent/`desired_titles` – Klasse B
* Keine Auto-GT-Review-Kandidaten in diesem Zyklus

## Nächster generalisierbarer Schritt

1. Soft-Skill-/Prosa-Filter gegen `skill_extra` (ohne Dateinamen-Hacks)
2. Label-Synonyme für Software (`Tools:`, `Systeme:`, EN)
3. Employment-Date-first Parser für Rest-Layouts
4. Danach erneut Post-Analysis-Regression mit Scorer V2
