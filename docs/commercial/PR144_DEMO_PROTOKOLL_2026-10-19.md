# Demo-Wiederholung mit Paket – Protokoll (T16.03, 19.10.2026)

Bezug: Ablauf „Zehnminütige Demo ohne echte Bewerbungen“ in `DEMO_AND_12_MONTH_PLAN.md`. Durchführung: Personaler (HR-Reviewer) auf der Box, ohne Zuschauer, headless. Zeiten in MESZ.
Das ist **keine** Live-Demo vor Menschen und **keine** Geräteabnahme. Status T16.03 bleibt `IMPLEMENTIERT – PRÜFUNG OFFEN`.

## Paket

- Linux x86-64, `Karrierekrake-Alpha-1.0-Linux-x86_64.tar.gz`, sha256 `6165086420f2491070ab7cec8ae755a055425c6ac70e6831a5eef834be76fe82`, aus Desktop Platforms 39200083290, Job 117891044917 (`success`).
- App-Identität `e0f9c3839c0b0b9bdd78ff71fbc28dca6787855c`, Version `1.0.0-alpha.1`. Das ist der `pull_request`-Merge von PR-Head `2470ca16` in `main` `6db9c47f`, siehe `docs/beta/PR144_PACKAGE_IDENTITIES_2470ca16.md`.
- „Final“ gilt nur für diesen Head. Ein neuer Commit auf #144 oder `main` macht das Paket veraltet.
- macOS- und Windows-Pakete desselben Heads gibt es (gleiche Übersicht). Auf der Box laufen sie nicht, deshalb hier keine Demo damit.

## Umgebung

Box: Debian 13, x86_64, 8 vCPU, 16 GB RAM, `QT_QPA_PLATFORM=offscreen`, kein Keyring und keine grafische Sitzung. Isolierte temporäre Datenordner. Nur die fiktiven Korpus-CVs `DE_01_Klassisch.pdf` und `EN_01_Classic_Resume.pdf`. Keine Konten verbunden, kein Versand, kein Checkout. CV-Modell: Qwen3.5-4B Q4_K_M, lag schon auf der Box (sha256 vom Skript gegen den Katalogwert geprüft). Dabei gab es keinen Modell-Download.
Belege: `docs/qa/pr144_demo_2026-10-19/` (`SHA256SUMS` OK).

## Ergebnis je Demo-Schritt

| Schritt (Plan) | Am Paket geprüft | Nur am Quellstand `2470ca16` geprüft | Blockiert / nicht geprüft |
|---|---|---|---|
| 1 Problem zeigen | – | – | Präsentationsteil, nicht technisch prüfbar |
| 2 Synthetischen CV importieren, Felder prüfen, Fehler korrigieren | **Ja:** Paket-Smoke (MainWindow, DB-Schema, `pages=8`) und Offline-Import DE_01/EN_01 in-process, je `ok`, je 3 Sprachen, 5 Skills, 6 Software, 3 Zertifikate; Laufzeit 117,6 s / 103,6 s (VM, nicht übertragbar) | `tests/test_cv_replace_keeps_manual_entries.py` (manuelle Einträge bleiben erhalten) | Geprüft sind nur Identität und Mengen, keine Feldwerte gegen das Sollwert-Blatt. Prüfdialog und Korrektur in der Paket-GUI wurden nicht bedient |
| 3 Suche filtern, Dry-Run, Entwurf prüfen, Grenze vor Versand | **Teilweise:** eingefrorene Suchabhängigkeiten (JobSpy/curl_cffi/libcurl, kein `tls_client`) im Netz-Namespace ohne Netzwerk `ok` | `tests/test_search_offline_fixture_pipeline.py`, `tests/test_dry_run_all_adapters.py`, `tests/test_force_submit_respects_dry_run.py` | Echte Suche (Netz) bewusst nicht ausgeführt. **Anschreiben-Entwurf im Paket: BLOCKIERT.** Das Linux-Paket hat keinen headless Einstieg für den Writer. Das HR-Urteil vom 18.10.2026 lautet „Papierkorb“ für beide Modelle (siehe `PR144_COVERAGE_AND_GATES.md`). Den Windows-CI-Schritt `cover_letter` (`ok`, Modus `CI_Python_using_verified_install_sidecar_not_packaged_writer_UI`) habe ich nicht qualitativ geprüft. **Matching-Qualität: nicht geprüft.** Die deterministische Fit-Anzeige ist nur über `tests/test_jobs_apps_timeline_ux.py` am Quellstand abgedeckt |
| 4 Bewerbung manuell markieren, Erinnerung/Kalenderentwurf | – | `tests/test_jobs_apps_timeline_ux.py` (Timeline/Status-Labels, Entwurf nur mit Freigabe), `tests/test_followup_eligibility.py` (Erinnerungen bleiben nach Neustart erhalten, kein Autoversand), `tests/test_calendar_universal_export.py`, `tests/test_t0110_synthetic_mail_calendar.py` | In der Paket-GUI nicht bedient. Ob es einen eigenen Test für das manuelle Markieren selbst gibt, habe ich nicht gezielt gesucht (**UNSICHER**). **Bekannte Produktlücken** (31 `xfail`, alle in `test_t0110_synthetic_mail_calendar.py`): ICS mit UTC-`Z` statt `TZID=Europe/Berlin`, keine `LOCATION`, falsche Terminrangfolge, kein Entwurf bei M4, generische Antworten bei M5/M6, keine Fallzuordnung M1/M2. Den Kalenderentwurf deshalb nur mit Hinweis auf diese Lücken zeigen |
| 5 Export/Backup, Offline-Neustart, Lizenz ohne Kaufzwang | **Ja:** Backup anlegen → prüfen → in neuen Ordner wiederherstellen → Smoke auf Wiederherstellung, synthetischer Marker erhalten, `ok`. GUI-Start ohne Tray vor Onboarding mit Startquittung `ok` (1,4 s) | `tests/test_privacy_export_completeness.py`, `tests/test_local_backup_restore.py`, `tests/test_offline_free_policy.py`, `tests/test_commercial_signed_licenses.py`, `tests/test_sponsor_consent.py` | Privacy-Export und Lizenzbereich am Paket nicht bedient. Kein Checkout (wie geplant) |
| 6 Grenzen offen zeigen | – | `tests/test_growth_scenarios.py`, `tests/test_beta_acceptance_report.py` | Grenzen stehen in diesem Protokoll |

Quelltests (15 Dateien, Head `2470ca16`, Box): **241 passed, 31 xfailed**, 0 failed (`source-tests.log`).

## Bewertung (Personaler)

- Geprüft am finalen Paket für diesen Head: Start, Offline-CV-Import mit fiktiven Daten, Backup/Restore/Neustart, GUI-Start und Suche ohne Netzwerk. Die Ergebnisse auf der Box stimmen mit den CI-Belegen im Artefakt überein. Die Programmdatei-Hashes sind gleich.
- Nicht geprüft oder blockiert: Anschreiben (HR „Papierkorb“; im Paket nicht headless erreichbar), Matching, GUI-Bedienung der Schritte 2–5 (kein Bildschirmtest), Kalenderentwurf ohne die bekannten Lücken, Plattformen außer Linux, echte Geräte und Keyring.
- Die vollständige Demo laut Plan ist mit dem Paket deshalb **nicht** wiederholt. Wegen der Anschreiben- und Kalenderlücken darf die Demo diese Funktionen nicht als fertig vorführen.
- UNSICHER: Das CI-Gesamtergebnis von Lauf 39200083213 (`cv-regression`) stand bei Erhebung noch aus.
