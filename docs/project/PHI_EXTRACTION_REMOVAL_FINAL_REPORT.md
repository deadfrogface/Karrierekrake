# PHI_EXTRACTION_REMOVAL_FINAL_REPORT

**Branch:** `cursor/holdout-100-d85b`  
**Base commit before removal:** `5f4127d`  
**Status:** PHI_EXTRACT removed from production CV import; DET pipeline verified.

## Ausgangslage

Frühere Architektur mischte DET (`parse_cv_text`) mit optionalem PHI_EXTRACT / C1-Fallback über `guenther_enabled` in `import_cv_canonical` und dem CV-Import-Dialog.

Messungen (Scorer V2, Holdout-100 Post-Analysis):

| Metrik | Vorher (Kenntnisse-Start) | DET final (v6) |
| ------ | ------------------------: | -------------: |
| Accuracy | 0.698 | 0.997 |
| F1 | 0.822 | 0.998 |
| Perfect | 17/100 | 89/100 |
| Hallucination | 0.137 | 0.001 |

C1-Fallback: 0/100 nach DET-Fixes. Phi ohne globalen Genauigkeitsgewinn, deutlich langsamer.

Produktentscheidung: **DET only** für Extraktion; **PHI_WRITE** bleibt.

## Entfernte Komponenten (produktiv)

* Phi-Zweig in `import_cv_canonical` (kein `suggest_cv_extract`, kein `reconcile` im Import)
* CV-Import-Dialog: kein `guenther_enabled` aus Settings; Preview ohne Phi-Status
* Produktives Routing DET/Phi, Thin Routing, Verify/Repair via Phi, Field Arbitration
* UI-Texte, die einen Extraktions-KI-Pfad suggerierten (`cv_import.pipeline_det`)

Altes `guenther_enabled=True` am Import: **DeprecationWarning**, Aufruf wird ignoriert.

## Erhaltene Komponenten

* PHI_WRITE (`SYSTEM_PHI_WRITE`, `suggest_writing`, Quality Loop)
* Günther Settings / Modellwahl für Schreibhilfe
* `suggest_cv_extract` / `validate_cv_extract` / `reconcile_phi_into_parsed` für **historische** Evaluation
* Holdout-100 Frozen Predictions, Scorer-V2-Berichte, Pipelinevergleiche

## Produktionspipeline

Siehe `CV_EXTRACTION_PRODUCTION_PIPELINE.md`:

```text
Datei → extract_text → parse_cv_text → verify/repair → Profil
```

Keine Modellladung, kein Netzwerk, kein Phi-Prozess.

## Testnachweis

| Suite | Ergebnis |
| ----- | -------- |
| `tests/test_phi_extraction_removed.py` (18 Gates) | PASS — `phi_extract_call_count == 0` |
| `tests/test_next02_phi_cv.py` | PASS — Import ruft Phi nie |
| `tests/test_final_holdout_protocol.py` | PASS — Sealing / Leakage |
| `tests/test_phi_write_no_hallucination.py` | PASS |
| `tests/test_guenther_local_ai.py` / `test_phi_extract_pipeline.py` | PASS |
| 100-CV DET Regression (`A5_det_product_v7_phi_removed`) | PASS |

Vorab bestehende Corpus-Fehler (`EN_02`, `EN_05` Skills-Counts) auch auf `5f4127d` — nicht durch Removal verursacht.

## Metriken vor/nachher (DET 100-CV, Scorer V2)

| Metrik | Vorher (v6) | Nachher (v7 phi-removed) |
| ------ | ----------: | -----------------------: |
| Accuracy | 0.9969018112488084 | **0.9969018112488084** |
| F1 | 0.9984485022079007 | **0.9984485022079007** |
| Perfect | 89/100 | **89/100** |
| Hallucination | 0.0009532888465204957 | **0.0009532888465204957** |
| Phi extract calls | — | **0** |
| Wall (100 CVs) | ~1.1 s Klasse | **1.13 s** |
| Peak RSS | — | **~45 MB** (ohne Modell) |

Artefakt: `artifacts/holdout_100/phi_removal_det_regression.json`

## Final-Holdout-Infrastruktur

* Phase A: `scripts/run_final_holdout_predictions.py` (blind, hasht, siegelt)
* Phase B: `scripts/evaluate_final_holdout.py` (Seal prüfen, Scorer V2)
* Protokoll: `docs/project/FINAL_HOLDOUT_PROTOCOL.md`
* Platzhalter: `tests/final_holdout/cvs/` (Datensatz noch nicht geliefert)

**Kein unabhängiges 99-%-Ergebnis behauptet** — Dataset ausstehend.

## Dependencies

| Dependency | bisheriger Zweck | weiterhin für WRITE? | Aktion |
| ---------- | ---------------- | -------------------: | ------ |
| llama.cpp / GGUF runtime (via Guenther) | Extract + Write | ja | KEEP_FOR_WRITE |
| `SYSTEM_PHI_EXTRACT` / extract schemas | Extract | nein (historisch) | KEEP_FOR_HISTORICAL_EVALUATION |
| Outlines/Instructor (falls vorhanden) | Extract | prüfen WRITE | unverändert belassen |
| pypdf / python-docx | DET Dokument | n/a | KEEP |

Keine Writer-Regression durch Dependency-Löschung in diesem Schritt.

## Verbleibende Risiken

* Unbekannte Layouts ohne KI-Fallback → `UNCERTAIN`
* Scan/OCR separat
* ~9 Skill-Wrap-Restfragmente (nicht überoptimiert)
* Unabhängiger Final-Holdout noch nicht ausgeführt

## Dokumentation

* `PHI_EXTRACTION_REMOVAL_AUDIT.md`
* `ADR_REMOVE_PHI_FROM_CV_EXTRACTION.md`
* `CV_EXTRACTION_PRODUCTION_PIPELINE.md`
* `FINAL_HOLDOUT_PROTOCOL.md`
* dieses Report

## Nächster Schritt

Unabhängigen Final-Holdout-Datensatz (30–50 CVs) bereitstellen → Phase A siegeln → Phase B auswerten.
