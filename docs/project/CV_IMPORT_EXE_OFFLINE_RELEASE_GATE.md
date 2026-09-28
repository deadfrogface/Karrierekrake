# CV-Import Offline-EXE — Release-Gate Status

**Branch:** `cursor/cv-import-exe-offline-bundle-d85b`  
**Stand:** 2026-09-28  

## Root cause: `model_missing` auf dem Laptop

Die Produktions-GGUF liegt **nicht** in der Onefile-EXE, sondern als Sidecar:

`models/qwen3.5-4b/Qwen3.5-4B-Q4_K_M.gguf` **neben** `Karrierekrake.exe`.

Wer nur die EXE kopiert/herunterlädt (wie die alte README-Anweisung), bekommt `model_missing`.  
CI-E2E lief bisher im Build-`dist/` mit vorhandenem Sidecar — das maskierte den Install-Fehler.

## Fix in diesem Stand

| Thema | Änderung |
|-------|----------|
| Auslieferung | `scripts/package_windows_release.py` → `Karrierekrake-Windows.zip` (EXE + `models/` + INSTALL.txt) |
| CI | Sidecar-Pflicht (`--require-cv-model-sidecar`); Stage in leeren Install-Ordner; E2E von dort |
| E2E | DE + EN Import; Negativ: corrupt + EXE-only → `model_missing`; `KARRIEREKRAKE_MODELS_DIR` isoliert |
| Resolve | Stale `KARRIEREKRAKE_CV_LLM_MODEL` fällt auf Sidecar zurück |
| Docs | README verlangt Zip, nicht EXE allein |
| UI | Günther-Unavailable-Texte ohne Modellmarkennamen |

## Frühere Metriken (Commit `e2bae4f` / `8026afc`, nur DE, Build-`dist/`)

| Metrik | Wert |
|--------|------|
| EXE-Größe | ~242 MB; Sidecar-GGUF ~2,6 GiB |
| Startzeit | ~20 s |
| Import DE_01 | ~236 s |
| Anschreiben | ~20 s |
| Peak (Host-Child) | ~74 MiB — **nicht** Job-Object i3/8 GB |

**Neuere Metriken** (Install-Simulation + EN + Negatives) erst nach dem nächsten grünen Windows-Smoke dieses Commits in `artifacts/cv_import_exe_offline_e2e.json` gültig.

## Release-Status

| Schritt | Status |
|---------|--------|
| Ursache EXE-only → `model_missing` | **behoben im Code/Packaging** |
| Windows CI mit staged Install | **ausstehend / zu belegen** |
| Heim-Laptop | **NICHT GETESTET** |
| Öffentlicher Release | **weiter blockiert** bis Zip-Gate + Laptop-Abnahme |

Siehe auch: `docs/project/GROK_PRUEFPLAN_STATUS.md`
