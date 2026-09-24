# Docpick Blind DE/EN v2 — Vorbereitung (kein Datensatz)

**Status:** Scaffold bereit. **Kein neuer unabhängiger Korpus vorhanden.**  
Bekannte CVs (Smoke, Mini-Holdout, Round2/3, Blind-v1) dürfen **nicht** als „neu“ verwendet werden.

## Protokoll (unverändert)

1. **Phase A (GT unzugänglich):** Parser-Commit + PDF-Hashes + Predictions einfrieren  
   (`PARSER_FREEZE.json`, `PHASE_A_EXTRACTION_SEAL.json`, `frozen_predictions/`)
2. **Phase B:** Seal prüfen, erst dann `phase_b_solutions/` laden und V3.1 scoreen  
3. Zwischen A und B **keine** Parser-/Prompt-/Modell-Änderung  
4. DE und EN getrennt berichten; unvollständige GT-Felder = `nicht_bewertbar`  
5. „99 %“ nur bei Blind-F1 ≥ 0,99 auf diesem Korpus — **n=4 (v1) reicht nicht**

## Anforderung an den neuen Datensatz

Bitte liefern (oder freigeben) unter z. B. `tests/docpick_blind_de_en_v2/`:

| Lieferobjekt | Anforderung |
|--------------|-------------|
| PDFs | ≥ **20** CVs, ideal **40**, gemischt **DE + EN** (mindestens je 10) |
| Unabhängigkeit | nie in Round2/3/Blind-v1/Mini-Holdout/Smoke als Entwicklungsset genutzt |
| GT | vollständige V3-Lösungsliste pro Dokument (`expected_results_full_v3.json`) |
| Layout | realistische Varianten (ein-/zweispaltig, Tabellen, UK/CH-Adressen willkommen) |
| Manifest | `EXTRACTION_MANIFEST_PDF_ONLY.json` mit `id`, `lang`, `path`, SHA-256 |

## Scripts (nach Datenlieferung)

```bash
# Phase A — GT-Verzeichnis darf nicht gelesen werden
python scripts/run_docpick_blind_de_en_v2_sealed_extract.py

# Phase B — Seal verify + Score
python scripts/run_docpick_blind_de_en_v2_sealed_score.py
```

Solange kein Manifest existiert, stoppen die Scripts mit Exit-Code 2 und dieser README-Referenz.

## Was v1 gezeigt hat (nicht Merge-Gate)

Blind-v1 n=4: F1 0,996, Warm 59,5 s — **informativ**, kein Produktiv-99%-Claim.
