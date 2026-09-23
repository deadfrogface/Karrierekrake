# Docpick Regression — bekannte DE/EN-CVs (PR #62)

**Testtyp:** `REGRESSION_KNOWN_CVS_NOT_BLIND`  
**Kein** unabhängiger Blindtest · **kein** 99-%-Nachweis · **kein** DET.

Extraktion: nur PDF-Pfade (`EXTRACTION_MANIFEST_PDF_ONLY.json`), GT/alte Predictions
nicht geladen. Seal + SHA-256 vor Auswertung. Metrik: **`COMPLETE_GT_ONLY_V3`**
(Scorer V2 unverändert; Lösungsblätter unverändert; Parser/Prompt unverändert).

## Inventar

| Korpus | Docs | DE | EN | Emp/Edu-GT |
|--------|------|----|----|------------|
| SMOKE_DE_EN_10_V1 | 10 | 5 | 5 | nur Counts → Emp/Edu **nicht bewertbar** |
| MINI_HOLDOUT_30 | 30 | 26 | 4 | volle Listen → bewertbar |

Ausgeschlossen: Leonie-Brandt-PDF (kein strukturiertes Lösungsblatt).

## Freeze / Lauf

- Commit / Freeze: siehe `PARSER_FREEZE.json` + `PHASE_A_EXTRACTION_SEAL.json`
- DET blockiert: ja (`parse_cv_text` → RuntimeError)
- Extraktion OK: **40/40**
- Wall ≈ **4310 s** · Mittel ≈ **107,7 s/CV** · Peak RSS ≈ **8493 MB**

## COMPLETE_GT_ONLY_V3 (kein Gesamt-F1 über alle Emp/Edu)

| Slice | Felder | P | R | F1 | Hallu | Missing | Perfect Core* |
|-------|--------|---|---|----|-------|---------|---------------|
| Gesamt (bewertbare Felder) | 1223 | 0,903 | 0,967 | **0,934** | 0,0016 (2) | 37 | 8/40 |
| DE | 1020 | 0,904 | 0,971 | 0,936 | 0,001 | 27 | — |
| EN | 203 | 0,896 | 0,945 | 0,920 | 0,005 | 10 | — |
| SMOKE_DE_EN_10 | 140 | 0,986 | 0,986 | 0,986 | 0,007 | 2 | — |
| MINI_HOLDOUT_30 | 1083 | 0,892 | 0,964 | 0,927 | 0,001 | 35 | — |

\*Perfect Core = alle **bewerteten** Felder eines Dokuments korrekt (Emp/Edu auf SMOKE nicht in der Bewertung).

**Nicht bewertbar:** 68 Feld-Slots (u. a. 10 Emp + 10 Edu auf SMOKE; weitere Count-only Skills/Software/Zertifikate).

**Gesamt-F1 inkl. aller Emp/Edu über beide Korpora:** **nicht möglich** — SMOKE hat keine vollen Emp/Edu-Listen.

## Echte Fehler (Beispiele mit CV-Beleg)

1. **DE_04** `address.city` missing — CV zeigt „Leipzig“ neben dem Namen; Extrakt leer.  
2. **EN_03** Adresse: Straße halluziniert als „Berlin“, Stadt falsch „Germany“, Land missing — CV: „Berlin, Germany“.  
3. **MH_003** `name.first_name` wrong — CV „Célina“, Extrakt „Celina“ (Diakritika).  
4. **MH_001** Employment-Eintrag missing / Datumsfelder — CV enthält „Seestern Produktion GmbH“ / „Aquakulturwirtin“.  
5. Viele **Datums-Wrong** (z. B. GT `02/2019` vs Pred `2019-02`) — Inhalt im CV belegt; Formatdifferenz unter unverändertem Scorer.

Fehlerliste: `PHASE_B_COMPLETE_GT_ONLY_V3_RESULTS.json` → `real_errors_on_complete_gt`.

## Produktiver Import

`import_cv` → `import_cv_docpick`; **kein DET-Fallback**.
