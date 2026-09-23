# EXTRACTION_ERROR_PARETO

Corpus: **Post-Analysis Development and Regression Corpus** (100 CVs)  
Baseline: DET A5 + Kenntnisse-Routing · Acc **0.698** · F1 **0.822** · Perfect **17/100**  
Scorer: V2 · Quelle: `artifacts/holdout_100/extraction_error_pareto.json`

## Perfect-Match-Verteilung

| Fehler/Dokument | Dokumente |
|----------------:|----------:|
| 0 | 17 |
| 1 | 4 |
| 2 | 4 |
| 3–5 | 22 |
| >5 | 53 |

Near-perfect (genau 1 Fehler): oft `software_extra` oder `address.country` — keine Einzelfall-Hacks.

## Top-Fehlerklassen (nach Gesamtauswirkung)

| Rang | Fehlerklasse | FP | FN | WC | Docs | verlorene Perfect | Schwere | Root Cause | Stufe |
| ---: | ------------ | -: | -: | -: | ---: | ----------------: | ------- | ---------- | ----- |
| 1 | skills_noise_or_prose_extra | 297 | 0 | 0 | 28 | 28 | high | Prosa/Split-Tokens in Skills | parse_skills |
| 2 | skills_contam_employment_leak | 171 | 0 | 0 | 20 | 20 | critical | Kenntnisse verschluckt Praxis/Stationen/Werdegang/Bildungsweg | section_split |
| 3 | software_missing_label_or_section | 0 | 165 | 0 | 45 | 45 | critical | Label/Wrap/Slash-Split; Fortsetzungszeilen | kenntnisse_routing |
| 4 | employment_entry_missing | 0 | 150 | 0 | 60 | 60 | critical | Experience-Überschriften nicht erkannt | section_split |
| 5 | skills_missing | 0 | 133 | 0 | 19 | 19 | high | Recall nach Over-Filter / falsche Sektion | skills |
| 6 | education_entry_missing | 0 | 50 | 0 | 40 | 40 | high | Bildungsweg / Schule & Ausbildung nicht erkannt | section_split |
| 7 | skills_software_misroute | 46 | 0 | 0 | 25 | 25 | high | Software landet in Skills | category routing |
| 8 | language_missing | 0 | 46 | 0 | 26 | 26 | medium | Sprachzeilen unter Kenntnisse | languages |
| 9+ | address.* missing | — | — | — | — | — | medium | Header/Country | personal |

Gemeinsame Ursache für Ränge 2–4 und 6–7: **Abschnittsgrenzen nach „Kenntnisse“** (u. a. `Praxis`, `Stationen`, `Werdegang`, `Bildungsweg`, `Schule & Ausbildung` — je ~20 CVs) plus **Software-Label-Tokenisierung** (`/`-Split, Zeilenumbruch).

## Feldgruppen (Baseline-Fehlercounts)

Siehe JSON `by_field_group`. Dominant: Skills (Hallu), Software (Missing), Employment (Missing), Education (Missing), Address (Missing).

## Iterationsreihenfolge (aus Pareto)

1. Abschnittsgrenzen + Kenntnisse-Kontamination / Software-Routing *(eine Root Cause)*  
2. Verbleibende Skills/Software-Trennung  
3. Employment-Record-Qualität  
4. Education-Record-Qualität  
5. Address/Country  
6. Languages  
7. C1/Phi-Fallback neu kalibrieren  
