# Grok-Bot-Prüfplan — Statusmatrix (ohne Heim-Laptop)

**Branch:** `cursor/cv-import-exe-offline-bundle-d85b`  
**Stand:** 2026-09-28  
**Ziele getrennt:** (1) persönlich nutzbarer Bewerbungsablauf · (2) öffentlicher Release  
**Hinweis:** Kein Laptop-Test und kein fertiger öffentlicher Release werden hier behauptet.

Legende: **PASS** = mit Commit/CI/Fixtures belegt · **FAIL** = bekannte Lücke · **NICHT GETESTET** = braucht Heim-Gerät / private Konten / Live-Portale

| # | Abschnitt | Status | Commit/Beleg | Blocker | Nächste Aktion |
|---|-----------|--------|--------------|---------|----------------|
| 1a | Ursache `model_missing` (EXE ohne `models/`) | **PASS** (Ursache fixiert) | Packaging: Sidecar + Zip; Resolve-Fallthrough | Alte EXE-only Builds | Zip `Karrierekrake-Windows.zip` nutzen |
| 1b | Offline-EXE Import DE (CI Install-Simulation) | **PASS** bis `8026afc`; **neu zu belegen** nach Packaging-Härte | `artifacts/cv_import_exe_offline_e2e.json` in Windows Smoke | CI-Lauf dieses Commits | Windows Smoke abwarten |
| 1c | Offline-EXE Import EN + Negativfälle | **neu in CI** | `--cv-en`, corrupt, EXE-only | CI-Lauf | Windows Smoke abwarten |
| 1d | UI ohne Modell-/Techniknamen | **PASS** (Unit) | `test_cv_import_exe_regression`, `fallbacks` sanitisiert | — | Laptop: Dialoge spotten |
| 1e | Parser NV3 Blind F1 0,980 | **NICHT GETESTET** | Bekannte Post-Analysis nicht als Blindersatz | Versiegelter Korpus | Neues Blind-Protokoll |
| 1f | Laptop Peak/Freeze/OOM | **NICHT GETESTET** | i3-Gate offen | Echtes Gerät | Heim-Messung |
| 2a | Jobquellen Unit/Contracts | **PASS** | `test_source_contracts` u. a. | — | — |
| 2b | Live StepStone/Indeed/LinkedIn | **FAIL** / rot | `live-sources.yml` zuletzt failure | Live-Health | Job debuggen |
| 2c | Matching Personaler-Gold | **FAIL** (fehlt) | `parser_debt`: kein Matching-Gold | Fixtures | Gold-Set anlegen |
| 2d | BRouter Unit + PR #100 | **PASS** | PR #100 merged | — | — |
| 2e | BRouter in Windows-EXE | **NICHT GETESTET** | `smoke_brouter_windows.py` nicht in CI | EXE-Gate | Smoke anhängen |
| 3a | Anschreiben 12-Gold + Preview-UI | **PASS** | `anschreiben_gold/`, Preview-Tests | — | — |
| 3b | 20 DE + 20 EN Personaler | **FAIL** (Claim) | nur 12 Fixtures | Korpus erweitern | oder Claim korrigieren |
| 3c | Reply-Templates synthetisch | **PASS** | `reply_safety_corpus.json` | — | — |
| 4a | Fake-Mail/Kalender/OAuth-Sim | **PASS** | Lifecycle-E2E, Fake-Provider | — | — |
| 4b | Echte OAuth-Testkonten | **NICHT GETESTET** | bewusst | Test-Tenant + Privacy-URL | Heim/Testkonten |
| 5a | Dataflow/Tokens/Redaction/CI | **PASS** | `docs/privacy/*`, security jobs | — | Fachlich prüfen lassen |
| 5b | GPL-3.0 vs. kommerzieller Vertrieb | **FAIL** / offen | `LICENSE` GPL-3.0 | Counsel | Lizenz klären |
| 5c | GGUF-Redistribution Lizenz | **NICHT GETESTET** | Teil-Audit CV-Parser | NOTICE/SBOM | Counsel + NOTICE |
| 6 | UI-Unit (Pills, Icon, Settings) | **PASS** | Unit-Shards | Visuell Laptop | Heim-Spotcheck |
| 7 | CI Perf/Smoke | **PASS** (eng) | Offline-E2E-Metriken | i3 Peak | Laptop |
| 8 | Commercial Ship (Payment/Website) | **FAIL** | Commerce NOT_IMPLEMENTED | Legal+Paddle | nach Ziel 1 |

## Heim-Gerät — konkrete Schritte (Ziel 1)

1. Artifact **`Karrierekrake-Windows.zip`** vom grünen Windows-Smoke/Build dieses Branches laden (nicht nur die EXE).
2. Zip vollständig entpacken; `Karrierekrake.exe` **im gleichen Ordner** wie `models\` belassen.
3. Offline (Flugmodus): App starten → DE-PDF importieren → Vorschau korrigieren → Übernehmen → App neu starten → Profil prüfen → Anschreiben erzeugen.
4. EN-CV wiederholen; eine kaputte Datei wählen (erwartete verständliche Meldung, nichts übernommen).
5. Optional: EXE allein auf den Desktop kopieren → Import muss „Modell fehlt / neu installieren“ zeigen.
6. Peak-RAM, Freeze, Start-/Importzeit auf dem Laptop notieren (i3-Gate bleibt offen bis dahin).
7. BRouter: Jobsuche mit Entfernungsfilter; angezeigte km dürfen keine Luftlinie sein.
