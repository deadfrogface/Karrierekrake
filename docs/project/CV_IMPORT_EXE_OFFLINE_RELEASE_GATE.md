# CV-Import Offline-EXE — Release-Gate Status

**Branch:** `cursor/cv-import-exe-offline-bundle-d85b`  
**Stand:** 2026-09-28  
**CI-Commit:** `c60867f` — Windows Smoke Offline-E2E **grün** (`release_blocked: false`)

## Root cause: `model_missing` auf dem Laptop

Die Produktions-GGUF liegt **nicht** in der Onefile-EXE, sondern als Sidecar:

`models/qwen3.5-4b/Qwen3.5-4B-Q4_K_M.gguf` **neben** `Karrierekrake.exe`.

Wer nur die EXE kopiert/herunterlädt, bekommt `model_missing`.  
Auslieferung ist jetzt **`Karrierekrake-Windows.zip`** (EXE + `models/` + INSTALL.txt).

## Metriken (Windows Smoke CI, staged Install-Ordner)

Quelle: `artifacts/cv_import_exe_offline_e2e.json` (Run nach `c60867f`)

| Metrik | Wert |
|--------|------|
| EXE-Größe | **242 715 746 Bytes** (~232 MiB) |
| Sidecar-GGUF | **2 740 937 888 Bytes** (~2,55 GiB) |
| Startzeit | **~24,9 s** |
| Import DE_01 | **~196 s** — Mara König / mara.koenig@example.com |
| Import EN_01 | **~168 s** — Emily Carter / emily.carter@example.com |
| Restart | **~19,6 s** — Profil persistiert |
| Anschreiben | **~20,4 s**, gleiches GGUF, 480 Zeichen |
| Corrupt PDF | `unreadable_cv`, verständliche DE-Meldung, keine Technikbegriffe |
| EXE ohne models | `model_missing`, „neu installieren“, nichts übernommen |
| Peak (Host-Child) | **~72 MiB** — **nicht** Job-Object i3/8 GB |

Transport: `inprocess` · Install-Pfad: frischer Temp-Ordner (Zip-Simulation), nicht Build-`dist/`.

## Release-Status

| Schritt | Status |
|---------|--------|
| Code: Bundle-Resolve + Zip + UI-Copy | **umgesetzt** |
| Unit-Tests | **CI grün** (`c60867f`) |
| Windows staged-install offline E2E (DE+EN+Negatives) | **CI grün** |
| Heim-Laptop | **NICHT GETESTET** |
| Öffentlicher Release | **weiter blockiert** bis Laptop-Abnahme |

Siehe auch: `docs/project/GROK_PRUEFPLAN_STATUS.md`
