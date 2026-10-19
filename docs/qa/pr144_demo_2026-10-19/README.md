# Belege: Demo-Wiederholung T16.03 auf der Box (19.10.2026)

Paket: `Karrierekrake-Alpha-1.0-Linux-x86_64.tar.gz`, sha256 `6165086420f2491070ab7cec8ae755a055425c6ac70e6831a5eef834be76fe82`, aus Artefakt 12163653246 (Desktop Platforms 39200083290). App-Identität `e0f9c3839c0b0b9bdd78ff71fbc28dca6787855c` (Merge von PR-Head `2470ca16` in `main` `6db9c47f`). Programmdatei nach dem Entpacken: sha256 `d6b35d8a5bdefe20a8bb2f014055ac2d33720e1698b1f262884fbc71a474e147`, gleich dem CI-Wert.

Box: Debian 13, x86_64, 8 vCPU „Intel Xeon Processor“, 16 GB RAM. Keine grafische Sitzung (`QT_QPA_PLATFORM=offscreen`), kein Keyring geprüft.

Treiber-Skripte stammen aus dem Worktree am PR-Head `2470ca16` und laufen mit dem venv `/workspace/kk-144-venv`:

| Datei | Befehl | Zeit (MESZ) |
|---|---|---|
| `acceptance.json`, `acceptance.log` | `python scripts/ci_native_acceptance.py --exe <entpackt>/Karrierekrake --out … --model /workspace/models/Qwen3.5-4B-Q4_K_M.gguf` (Modell-SHA256 vom Skript gegen `CV_MODEL_SHA256` `00fe7986…` geprüft; Proxy auf 127.0.0.1:1, LLM in-process) | 06:59:45–07:03:37 |
| `backup-restore.json` | `python scripts/ci_native_backup_restore.py --exe … --out …` | 07:08:34–07:08:41 |
| `gui-startup.json` | `python scripts/ci_native_gui_startup.py --exe … --out …` | 07:08:41–07:08:43 |
| `search-deps.json` | `unshare -rn sh -c 'python scripts/ci_frozen_search_deps_check.py --exe … --out …'` (Netz-Namespace nur mit `lo`; geprüft: Verbindung zu 1.1.1.1:443 → `Network is unreachable`) | nicht protokolliert (nach 07:08:43) |
| `source-tests.log` | `python -m pytest -q` auf 15 Quelltest-Dateien am Head `2470ca16` (Liste im Protokoll) | nicht protokolliert |

Alle Skripte arbeiten in temporären Datenordnern (`KARRIEREKRAKE_DATA_DIR`). Daten: nur die fiktiven Korpus-CVs `tests/fixtures/cv_corpus/DE_01_Klassisch.pdf` und `EN_01_Classic_Resume.pdf`.
