# One-Model Qwen — Phi-Purge & Status

**Branch:** `cursor/one-model-cv-write-d85b` / PR #99  
**Basis main:** `ffa648e` (bis #95)  
**Stand:** 2026-09-27

## Ausgangslage Drafts

| PR | Inhalt | CI | Rolle |
|----|--------|-----|-------|
| **#96** | EXE-Packaging, `cv_extract`, Auto-LLM, stufenspezifische Fehler | smoke grün; **security** fail (diskcache) | Packaging-Quelle; auf #99 übernommen |
| **#99** | One-Model Dual-Use Qwen | **CI grün** inkl. security + Windows EXE-Smoke | **Arbeitsbasis** |
| main | Phi noch `PRODUCTION_MODEL_ID=phi4-mini` | — | nicht produktiv für diesen Auftrag |

## Verbindliche Entscheidung

**Ein Gewicht:** `Qwen3.5-4B-Q4_K_M` (`qwen3.5-4b`) für CV-Extrakt **und** Anschreiben.  
**Phi:** nur noch in `HISTORICAL_MODEL_CATALOG` — nicht installierbar, nicht in UI, nicht in Fallbacks.  
**Kein** DET-Fallback, **kein** zweites Gewicht, **kein** Cloud.

## Getrennte Vorgänge

| Vorgang | Eingabe | Modell | Prozess |
|---------|---------|--------|---------|
| CV-Import | Datei → `cv_extract` → Docpick-Schema | Qwen in-process (Child) | `desktop.cv_import_child` |
| Anschreiben | bestätigtes Profil + Stelle | Qwen via Günther | UI-Prozess; **kein** `import_cv`/`docpick` |

Cross-Process-Lock: `core/local_model_lock.py` — Import und Schreiben halten nicht gleichzeitig dasselbe GGUF. Nach Schreiben: `unload_model()`. Vor Import: Günther unload.

## Migration

Alte `guenther_model`-Werte (`phi4-mini`, `auto`, Legacy-Qwen) → `qwen3.5-4b` beim Laden (`core/config.py`). Profile/Dokumente unangetastet.

## Nachweis „Phi-Aufrufe 0 / ein Qwen-Gewicht“

- `MODEL_CATALOG` = nur `qwen3.5-4b`
- Unit: `tests/test_one_model_qwen_only.py`
- UI/Fallbacks nennen Qwen, nicht Phi
- Historische Offline-Artefakte bleiben lesbar (Archiv)

## Gates (ehrlich)

| Gate | Status |
|------|--------|
| Linux Child DE/EN/DOCX Import | zuvor auf Agent-VM `ok=True` |
| Windows-EXE E2E öffnen→import→übernehmen→restart | **OFFEN** (CI build-and-exe-smoke ≠ voller E2E) |
| Anschreiben ohne erneute CV-Extraktion | Code-Pfad belegt; manuelle EXE-Prüfung **OFFEN** |
| i3/8 GB Job-Object ≤ 3,3 GB | **OFFEN / UNGEPRÜFT** |
| 16 GB Limit | nicht neu gesetzt; 3,3 GB-Gate unverändert |
| 99 % unabhängig | **nicht nachgewiesen** (NV3 F1 0,980 Frozen unverändert) |

## Nicht behaupten

- keine fertige Windows-App allein durch Unit-Tests
- kein neuer Blind-99-%-Claim
