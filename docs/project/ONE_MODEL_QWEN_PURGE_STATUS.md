# One-Model Qwen — Phi-Purge & Status

**Branch:** `cursor/one-model-cv-write-d85b` / PR #99  
**Basis main:** `ffa648e` (bis #95)  
**Stand:** 2026-09-27

## Ausgangslage Drafts

| PR | Inhalt | CI | Rolle |
|----|--------|-----|-------|
| **#96** | EXE-Packaging, `cv_extract`, Auto-LLM, stufenspezifische Fehler | smoke grün; **security** fail (diskcache) | Packaging-Quelle; auf #99 übernommen |
| **#99** | One-Model Dual-Use Qwen | CI grün inkl. security; Windows EXE-Smoke läuft/folgt | **Arbeitsbasis** |
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
- Unit: `tests/test_one_model_qwen_only.py` (inkl. Sprachwahl DE/EN für Schreiben)
- UI/Fallbacks nennen Qwen, nicht Phi
- Historische Offline-Artefakte bleiben lesbar (Archiv)

## Schreiben — Parameter (nach Sample, nicht ungeprüft 0,7/400)

| Parameter | Wert | Begründung |
|-----------|------|------------|
| temperature | **0,2** | Samples DE/EN mit Evidence-Guards `ok=True` |
| max_tokens (writing) | **900** | DE-Body ~964 Zeichen; JSON-Kopf braucht Luft |
| Ziellänge Body | 250–1000 Zeichen | Prompt; kein festes 400 |
| Sprache | Job-dominant DE/EN | Fix: Tasks nicht mehr hardcodiert „nur Deutsch“ |

Samples: `artifacts/one_model_dual_use/writing_purge_samples/SAMPLES.json`  
Korpusbericht: `docs/project/ONE_MODEL_CORPUS_REGRESSION.md`

## Gates (ehrlich)

| Gate | Status |
|------|--------|
| Linux Child DE/EN/DOCX Import | zuvor auf Agent-VM `ok=True` |
| Unit „kein Phi / ein Qwen“ | **PASS** |
| Known Parser-Rescore + Frontend KEEP | dokumentiert |
| Anschreiben ohne CV-Reparse (Code + Samples) | belegt; EXE manuell **OFFEN** |
| Windows-EXE E2E öffnen→import→übernehmen→restart | **OFFEN** (CI build-and-exe-smoke ≠ voller E2E) |
| i3/8 GB Job-Object ≤ 3,3 GB | **OFFEN / UNGEPRÜFT** |
| 16 GB Limit | nicht neu gesetzt; 3,3 GB-Gate unverändert |
| 99 % unabhängig | **nicht nachgewiesen** (NV3 F1 0,980 Frozen unverändert) |

## Nicht behaupten

- keine fertige Windows-App allein durch Unit-Tests
- kein neuer Blind-99-%-Claim
- Agent-VM-RAM/Zeiten ≠ Laptop-Nachweis
## PR-Tool-Hinweis

`ManagePullRequest` schlägt fehl mit *PR URL must belong to the current repository* (Agent-Kontext verweist auf ein anderes Repo als Karrierekrake). Branch ist gepusht: `cursor/one-model-cv-write-d85b` @ HEAD; PR https://github.com/deadfrogface/Karrierekrake/pull/99 — Body ggf. manuell aktualisieren.
