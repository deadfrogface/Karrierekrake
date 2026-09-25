# Round4 – bekannte DE/EN-Regression (nicht Blind)

**Seal:** `tests/docpick_qwen35/regression_known_cvs_round4/`  
**Label:** `REGRESSION_KNOWN_CVS_NOT_BLIND` — kein 99%-Claim.

## Ergebnis V3.1 COMPLETE_GT_ONLY

| | Round3 | Round4 |
|--|--------|--------|
| F1 | **0,991** | **0,979** |
| Perfect Core | **33/40** | **10/40** |
| Halluzinationen | 1 | **0** |
| Missing | 19 | **11** |
| Wrong | 1 | **39** |
| DE F1 / EN F1 | 0,995 / 0,972 | 0,978 / 0,985 |
| Ø s/CV | 88,2 | **78,8** |
| Cold / Peak RSS | 111,7 s / 3,3 GB | **94,5 s / 3,34 GB** |

## Was Round4 verbessert hat

Adresse/UK/CH, Street+Hausnr-Split, Software-Suffixe, Employment `|` und Tabellen-Merge → frühere Fehler auf EN_02, DE_04, MH_019/024/025/026/004 weitgehend weg; Halluzinationen 0.

## Was Round4 verschlechtert hat

Prompt „Dates MM/YYYY“ + aggressives „heute“ → viele **DOB**-Formatfehler und erfundene **heute**-Enddaten. Prompt/DOB-Norm danach korrigiert; **kein** erneuter 40er-Lauf (Vermeidung Wiederholung). Round3 bleibt Qualitäts-Referenz bis zum nächsten Seal.

## Nicht bewertbar

Felder nur mit `software_count` o. ä. in der Inventory → `nicht_bewertbar` (unverändert im Scorer).
