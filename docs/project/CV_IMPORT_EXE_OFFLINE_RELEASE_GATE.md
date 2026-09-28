# CV-Import Offline-EXE — Release-Gate Status

**Branch:** `cursor/cv-import-exe-offline-bundle-d85b`  
**Stand:** 2026-09-28

## Anforderung

Nach frischer Installation muss der Lebenslauf-Import **offline** funktionieren:

- Modell + Inferenz-Runtime + Abhängigkeiten in der ausgelieferten Windows-Installation
- kein Download, kein Modellpfad, kein Terminal, kein manuell gestarteter Dienst
- kein Phi-/DET-Fallback
- UI ohne Modellnamen / interne Technikbegriffe
- Fehler: verständliche Meldung + sinnvolle Aktion; Technik nur in Diagnose-Logs
- Nachweis: App starten → PDF importieren → Vorschau → übernehmen → Neustart → Profil; plus Anschreiben mit demselben Modell
- Metriken: EXE-Größe, Startzeit, Importzeit, Peak-Speicher

## Umsetzung in diesem PR

| Thema | Änderung |
|-------|----------|
| Modell-Auflösung | `core/cv_llm_runtime.py`: `_MEIPASS/models/…`, `<exe_dir>/models/…`, Vendor, dann AppData; Materialisierung nach AppData ohne Download |
| Packaging | Sidecar `dist/models/…` neben EXE (Standard); optional Embed via `KARRIEREKRAKE_EMBED_CV_MODEL_IN_EXE`; `llama_cpp` collect_all; Require-Flag |
| Prepare | `scripts/prepare_bundled_cv_model.py` (SHA-256, optional HF nur auf Build-Maschine) |
| Sidecar | `dist/models/qwen3.5-4b/…` neben EXE (schneller Start als reines onefile-Extract) |
| UI | `desktop/i18n.py`, `cv_import_child.py`, Settings-Label ohne Qwen/Docpick/DET |
| Gate | `scripts/ci_cv_import_exe_offline_e2e.py` + Windows-Smoke/Build-Workflows |

## Metriken (Platzhalter bis Windows-CI)

Datei: `artifacts/cv_import_exe_offline_e2e.json` (CI-Artifact).

| Metrik | Status |
|--------|--------|
| EXE-Größe | **CI misst** (`exe_bytes` / `build_metadata.txt`) |
| Startzeit | **CI misst** (`start_wall_s`) |
| Importzeit | **CI misst** (`import_wall_s`) |
| Peak-Speicher | **CI misst** (best-effort children RSS; Job-Object i3/8 GB weiter separat) |

## Release-Status

| Schritt | Status |
|---------|--------|
| Code: Bundle-Resolve + llama_cpp collect + UI-Copy | **umgesetzt** |
| Unit-Tests (Resolve, Policy, UI ohne Tech-Namen) | **lokal lauffähig** |
| Windows saubere Umgebung offline E2E | **CI-Gate verdrahtet — Nachweis erst nach grünem `build-and-exe-smoke`** |
| Agent-VM hat keinen Windows-Worker | **kein lokaler Windows-EXE-Lauf hier** |

**Solange der Windows-Offline-E2E-Step rot oder fehlend ist, bleibt der Release blockiert.**
