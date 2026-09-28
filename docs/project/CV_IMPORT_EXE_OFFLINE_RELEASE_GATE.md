# CV-Import Offline-EXE — Release-Gate Status

**Branch:** `cursor/cv-import-exe-offline-bundle-d85b`  
**Stand:** 2026-09-28  
**CI-Commit:** `e2bae4f` — Windows Smoke Offline-E2E **grün** (`release_blocked: false`)

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
| Modell-Auflösung | `core/cv_llm_runtime.py`: `_MEIPASS/models/…`, `<exe_dir>/models/…` Sidecar (ohne AppData-Copy), Vendor; Fail-closed |
| Packaging | Sidecar `dist/models/…` neben EXE; optional Embed; `llama_cpp` collect_all; Unsloth-Spiegel für CI-Download |
| Prepare | `scripts/prepare_bundled_cv_model.py` (SHA-256, optional HF nur auf Build-Maschine) |
| UI | `desktop/i18n.py`, `cv_import_child.py`, Settings ohne Qwen/Docpick/DET |
| Gate | `scripts/ci_cv_import_exe_offline_e2e.py` + Windows-Smoke/Build-Workflows |
| Robustheit | Think-Block-Strip vor JSON-Parse; Parser-Timeout 300 s (CI 600 s) |

## Metriken (Windows Smoke CI, Artifact `cv_import_exe_offline_e2e.json`)

| Metrik | Wert |
|--------|------|
| EXE-Größe | **242 717 868 Bytes** (~232 MiB); Sidecar-GGUF ~2,6 GiB |
| Startzeit | **~20,3 s** |
| Importzeit (DE_01) | **~235,6 s** — Mara König / mara.koenig@example.com |
| Restart | **~21,6 s** — Profil persistiert |
| Anschreiben | **~19,9 s**, gleiches GGUF, 480 Zeichen |
| Peak (Host-Child, best-effort) | **~74 MiB** (nicht Job-Object i3/8 GB) |

## Release-Status

| Schritt | Status |
|---------|--------|
| Code: Bundle-Resolve + llama_cpp collect + UI-Copy | **umgesetzt** |
| Unit-Tests | **CI grün** |
| Windows saubere Umgebung offline E2E | **CI grün** (`build-and-exe-smoke`) |
| Manuelle Extra-Prüfung außer CI | optional |

**Offline-EXE-Gate für diesen PR: erfüllt.**
