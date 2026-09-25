# Round9 Post-Analysis — remaining NV3/MH errors (kein Blind)

**Round8 F1 0,999** bleibt Post-Analysis auf bekannten CVs.  
**NV3 Frozen Blind F1 0,980** unverändert. Scorer unverändert.

## Parser-Fixes (allgemein, Regression auf bekannten Fällen)

| Fehler | Allgemeine Regel | Klasse |
|--------|------------------|--------|
| MH_019 `heute` vs Tabellen-Ende | Table `\| start \| title \|` / `\| end \| company \|` im Jobblock | Parser |
| MH_025 Minitab/Qlik Sense fehlen | Enrich aus Applications/Software/EDV | Parser |
| NV3_008 TIA Portal in Certs | Software-Tokens aus certificates → software | Parser |
| NV3_034 Communication aids in Certs | Soft-Skill-Phrasen → skills; BLS bleibt Cert | Parser |
| NV3_033 DE-Rewrite von EN-Dropout | Source-Phrasing erhalten | Parser (kein Scorer) |
| NV3_041 Apostroph | Format: `’`→`'` in Namen | Format |
| NV3_050 Self-employed in Title | Pipe-Split Title→Company | Parser |
| NV3_001 Duty als Title | Profession nahe Company, Duty→responsibilities | Parser |

Kein Scorer-Tuning für F1.

## Offline-Unit-Belege

`tests/test_cv_docpick_helpers.py::test_table_end_date_self_employed_software_duty_apostrophe`

## Blind v3

Vorbereitung unter `tests/docpick_blind_de_en_v3/` — **Dataset fehlt** (≥50 ungesehen).
