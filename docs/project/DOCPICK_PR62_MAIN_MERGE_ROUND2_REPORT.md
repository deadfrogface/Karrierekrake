# Docpick PR #62 — Main-Merge + Round2 (V3.1)

**Kein Merge als fertiger Parser.** Bekannte Entwicklungs-CVs. **Kein** unabhängiger Blindtest. **Kein** 99-%-Nachweis.

## PR / CI

- Branch: `cursor/docpick-qwen35-cv-replace-d85b`
- Merge: `origin/main` integriert (Konfliktlösung: Docpick bleibt einziger Produktiv-Import)
- DET-Fallback: **nein** (`import_cv_canonical` → `import_cv_docpick` only; `parse_cv_text` nur offline/Unit)

### CI-Ursachen (Tip `72ea744`) und Fixes

| Check | Ursache | Fix |
|-------|---------|-----|
| privacy / security | `@example.de` in Holdout-Artefakten | Artefakte `final_holdout` → `@example.com`; Allowlist `example.*` Fixtures |
| unit-tests | `parse_cv_text` raiste | Offline-DET wieder nutzbar; Import ruft DET nicht auf; Phi-Tests stubben Docpick |
| cv-regression | Docling fehlt in CI | Corpus/Sollwerte **SKIP** ohne Docling (kein DET-Fallback) |

## Round2-Herkunft

- Lokal versiegelt unter `tests/docpick_qwen35/regression_known_cvs_round2/`
- Freeze-Commit Parser: `72ea744` (name-from-email + compact schema + docling cache)
- Modell-SHA: `00fe7986…` match
- Datei-Hashes `cv_docpick_import.py` / Scorer V3.1 / date_normalize: match
- Seal: `gt_not_loaded=true`, 40/40 OK, Prediction-SHA verifiziert vor GT-Load
- **Bewertung:** Integrität ausreichend → fehlende CVs nicht nötig; kompletter 40er-Lauf verwendet

## Ergebnisschichten (strikt getrennt)

### A — Ursprünglicher vollständiger Lauf (V3)
- Seal Freeze `9674973` / Score `229d005`
- F1 **0,934** · Perfect Core **8/40** · Hallu ≈0,0016 · Felder 1223
- Ø ≈107,7 s/CV · Peak RSS ≈8493 MB

### B — V3.1 auf denselben alten Vorhersagen (reiner Scorer)
- Commit `72ea744` Artifact `SCORE_V3_VS_V3_1_SIDE_BY_SIDE.json`
- F1 **0,981** · Perfect Core **20/40** · 107 Datums-Flips · **kein Parser-Lauf**

### C — Korrekturschicht auf alten Vorhersagen (kein Full-Re-Extract)
- Layered C: name-from-email Mapping auf sealed preds
- F1 **0,985** · Perfect Core **21/40** · **kein** vollständiger neuer Extrakt

### D — Round2 Neu-Extrakt 40/40 + V3.1 (dieser Lauf)
- F1 **0.9889**
- Perfect Core **23/40**
- Hallu **0.0008** (n=1)
- Felder **1231** bewertet · nicht bewertbar **68**
- DE: F1 **0.9882** · PC **15/31** · n=31
- EN: F1 **0.9926** · PC **8/9** · n=9
- Ø **87.8 s/CV** · Peak RSS **3239 MB**
- Kaltstart `DE_01`: **111.2 s**
- Folgelauf `DE_02`: **139.2 s**
- Echte Fehler: missing=19, wrong=7, hallu=1
- Schwerpunkt: employment (Positionen/end_date heute), education Abbruch-Marker, Diakritika (Célina), DE_04 city

## Verbleibende Importfehler (Beispiele)

Siehe `PHASE_B_COMPLETE_GT_ONLY_V3_1_RESULTS.json` → `real_errors_on_complete_gt`.

## DET-Fallback

Bestätigt: Produktivpfad nur Docpick; bei Fehler `CvImportError` ohne DET.
