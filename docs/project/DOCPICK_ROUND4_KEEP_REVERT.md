# Round4-Regression: Ursachen und KEEP/REVERT

## Ursachen (Round3 vs Round4, gleicher Scorer V3.1)

| Familie | Δ | Zuordnung |
|---------|---|-----------|
| DOB wrong (+21) | R3 `DD.MM.YYYY` → R4 `MM/YYYY` / unvollständig | **Prompt** „Dates MM/YYYY“ (Modellantwort) |
| end_date heute (+16) | R3 konkrete Daten → R4 erfundenes `heute` | **Prompt** aggressives „current job → heute“ |
| name diacritics (+2) | Célina/Mikołaj | **Prompt** (Diakritika-Hinweis gekürzt) |
| Missing address/skills/software (−19) | Round4 besser | **Postprocess** KEEP |
| Missing license/cert (+11) | Schema-Strip + kompaktes Prompt | **Prompt/Schema** |

Normalisierung `_norm_period_end` / Scorer: **nicht** die Ursache der neuen DOB-Fehler (R3 hatte dieselben Norm-Helfer für Present→heute).

## KEEP / REVERT

| Änderung | Entscheidung | Begründung |
|----------|--------------|------------|
| Round3 System-Prompt wiederherstellen | **KEEP (Revert Round4-Prompt)** | Qualität R3 |
| Schema-Description-Strip Default aus | **REVERT** (opt-in Env) | R3 nutzte volles Schema |
| max_tokens 2048 | **KEEP** | gegen JSON-Abbruch |
| n_ctx 4096 (Server) | **KEEP** | Kontext |
| Street/Hausnr-Split | **KEEP** | Missing↓ |
| Software-Level-Strip | **KEEP** | Missing↓ |
| Employment `\|` + Tabellen-Merge | **KEEP** | Missing↓ / Hallu↓ |
| Address-Enrich aus Header | **KEEP** | UK/CH/City |
| MM/YYYY-Norm Employment | **KEEP** | Datumsform |
| DOB-Enrich aus Text | **KEEP (neu)** | repariert Prompt-Schaden allgemein |
| heute-Repair aus Datumsrange im Text | **KEEP (neu)** | nur wenn datiertes Ende sichtbar |
| `normalize_driving_license` (DET-Helfer, kein Import) | **KEEP (neu)** | Lizenz-Codes |
| UI Fail-fast / Progress | **KEEP** | UX, keine Qualitätsregression |
| Compact „Dates MM/YYYY“ Prompt | **REVERT** | DOB-Regression |
| FlashText | Messung separat | nur bei Gewinn |
