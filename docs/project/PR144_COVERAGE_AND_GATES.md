> **Aktualisierung 14.10.2026:** Der konkrete Stand dieser Fortsetzung steht in [PR144_IMPLEMENTATION_HANDOFF.md](PR144_IMPLEMENTATION_HANDOFF.md). Ältere Aussagen unten zu fehlender Zahlungsanbindung, reinem Sandbox-Reducer oder manuellem nativen Update beschreiben frühere Zwischenstände. Tests/CI und externe Freigaben bleiben offen.

# PR #144 — vollständige Arbeitszerlegung und Abnahme-Gates

Stand: 13.10.2026. **Kein Punkt ist allein durch eine PR-Nummer als erledigt anzusehen.** Alle nachfolgenden Änderungen bleiben bis zum späteren Review ungemergt.

| Paket | Bereits vorbereitete PRs | Weitere zwingende Nachweise / Implementierungen |
|---|---|---|
| T01 Kernfunktionen/CI | #145 | Laufzeit-Baseline, parallele Tests ohne Coverage-Verlust, Parser/Suche/Filter/Löschung/Dry-Run/Freeze-Regressions |
| T02 Modellinstallation | #146 #147 #148 #149 #150 #151 | Echter Download, SHA256, Wiederaufnahme, Probe, Aktivierung, Neustart auf Windows |
| T03 Updater | – | Fehler reproduzieren, Download/Checksum/Asset/Recovery/Profil-Erhalt E2E |
| T04 Desktop-OS | – | Windows/Linux/macOS Build-Matrix, native Smoke, physische Testgeräte |
| T05 Setup/UI/Browser | #148 #151 | Wizard-Start, Navigation, Browser-Auswahl, Popup-Fokus, 125–200%-Tests |
| T06 Security/CRA | #154 | Security-Audit, Dependency-Freeze/Advisories, Incident-Verifikation, CRA-Rechtsprüfung |
| T07 Datenschutz | – | Export/Löschung/Neustart-Tests, Logging-Redaktion, Datenflussabgleich |
| T08 SBOM/Lizenzen | #156 | Native Abhängigkeiten, Modelle, Daten, Lizenztexte, SBOM im Release |
| T09 Verbraucherrecht | #153 | Finales AGB/Impressum/Widerruf mit echten Anbieterangaben und juristischer Freigabe |
| T10 Barrierefreiheit | – | NVDA/VoiceOver, Tastatur, Kontrast, Skalierung, BFSG-Einstufung |
| T11 Free/Premium/Ads | #155 | Implementierte Offline-Free-Gates, Werbeeinwilligung und geprüfte Premium-Abgrenzung |
| T12 Payments | #155 | Paddle Sandbox, idempotente Entitlements, Refund/Cancel/Offline-Tests; Verträge offen |
| T13 Betrieb | #154 | Support- und Restore-E2E, Verantwortlichkeiten, reale Unternehmensdaten |
| T14 Website/Marke | #153 | Website-Implementierung, Domain-/Markenprüfung, Anbieterfreigabe |
| T15 Beta | #152 | Menschliche Windows/Linux/macOS Durchläufe und dokumentierte Befunde |
| T16 Wachstum | #155 | Validierte Kostenannahmen, Demo, belastbare Zahlen, reale Kontakte |

## Technische Gate-Regeln
1. Jede PR beginnt vom unveränderten aktuellen `main` und enthält einen begrenzten, prüfbaren Scope.
2. Ein erfolgreicher Unit-Test ist kein Endnutzer-E2E-Beleg. Statuswerte: ENTWURF / IMPLEMENTIERT / CI-BESTÄTIGT / REALGERÄT-BESTÄTIGT.
3. Keine reale Bewerbung, Mail, Zahlung, Kontoanlage, Werbeausspielung oder Veröffentlichung in CI.
4. CI darf nicht durch Entfernen/Skippen bestehender Tests beschleunigt werden.
5. Gleichzeitige PRs, die dieselben Dateien ändern, müssen vor dem Merge auf Konflikte geprüft und neu basiert werden.
6. Menschliche Freigaben und externe Anbieter-Verifizierung sind ausdrücklich nicht durch Code ersetzbar.

## Bestandsabgleich mit main
`core/app_updates.py`, `core/native_updates.py`, `desktop/services/browser_install.py`, `core/privacy/lifecycle.py` und diverse Security-/Accessibility-Dokumente existieren bereits. Die Arbeit besteht aus Lückenanalyse, Reparatur und Tests, **nicht** dem erneuten Erfinden dieser Funktionen.


## Konsolidierter Integrationsstand — 13.10.2026
**Einziger offener Integrations-PR ist #144.** Die ehemaligen Einzel-PRs #145–#174 wurden nach Übernahme der Änderungen geschlossen; #110 ist nicht Bestandteil. Die alte Spalte „Bereits vorbereitete PRs“ oben ist ein historisches Herkunftsregister, keine Liste offener PRs.

Technisch enthalten: CI-Importkorrektur, Modell-Setup-Fortschritt/Fehler/Probe/Resume/Aktivierungsprüfung, Update-Fehlerbehandlung, native Manifest-Validierung, Backup mit Settings-Aktionen/CLI, Privacy-Export, Redaction, SBOM-Exporter, Accessibility-Regressionstests, Beta-Skripte, Offline-Free-Richtlinie, Zahlungs-Sandbox, Szenariorechner, Incident-Triage, Website-Entwurf sowie die Dokumentationspakete.

**Nicht als abgenommen markieren:** Endnutzer-Modell-Download und Neustart, Update mit Rollback und Profil-Erhalt, reale Windows/macOS/Linux-Installationen, Screenreader und Skalierung, Google-Anbieterfreigabe, externe Zahlungsabwicklung, juristische Texte, reale Betatests und Marketing-/Unternehmensentscheidungen. Diese Gates benötigen zusätzliche automatisierte Nachweise bzw. echte Geräte/Menschen. Ein „grüner“ CI-Lauf ersetzt keine Realgerät-Prüfung.

### Integrations-Fixes nach Sammel-Commit
- Redaction: Auch unklassifizierte verschachtelte Strings mit Bearer-Token werden redigiert.
- Backup: Restore-Ziel darf kein Symlink sein; Archiv-Mitgliedstypen werden vor Path-Konvertierung validiert.
- Privacy-Export: Abgelehnte Dokumente melden keine Dateinamen in `skipped`.
- Regressionstests entsprechend aktualisiert.

### Nächste verbindliche Prüfreihenfolge
1. Alle CI-Jobs für **letzten** PR-Head abwarten; Fehlschläge reproduzieren und beheben, ohne Tests zu entfernen.
2. Cross-Feature-Regressionen für Modellinstallationswizard, Privacy-Export und Restore prüfen.
3. Paket- und Release-Smokes auf Windows/macOS/Linux durchführen und Ergebnisse in der Beta-Matrix protokollieren.
4. Nichtautomatisierbare Abnahmen als blockiert mit Verantwortlichem und Nachweis offen lassen.


## CI-Meilenstein — 13.10.2026, Commit 42f49464
Alle drei zentralen GitHub-Workflows dieses **konkreten** Commit-Stands waren erfolgreich:
- CI: https://github.com/deadfrogface/Karrierekrake/actions/runs/38415274859
- Windows Smoke: https://github.com/deadfrogface/Karrierekrake/actions/runs/38415274775
- Desktop Platforms: https://github.com/deadfrogface/Karrierekrake/actions/runs/38415276260

Dieser Beleg ist **nicht automatisch auf nachfolgende Commits übertragbar**. Spätere Sicherheitskorrekturen müssen ihre eigene CI bestehen.

### Gate-Zustand nach bestandenem Integrationslauf
| Gate | Status | Grund |
|---|---|---|
| Konsolidierte Codebasis | CI-BESTÄTIGT (42f49464) | 3/3 Workflows erfolgreich |
| Modell-Download auf Endnutzergerät inkl. Neustart | OFFEN | echter Modell-Download und Modell-Probe auf Windows fehlen |
| Upgrade von installierter Altversion und Rollback | OFFEN | echte installierte Altversion / Profilmigration nicht nachgewiesen |
| Windows/macOS/Linux reale Installation | OFFEN | CI-Builds sind kein physischer Test |
| Screenreader, 125–200% Skalierung | OFFEN | reale assistive Technologie nicht nachgewiesen |
| Google OAuth / Anbieterfreigabe | BLOCKIERT EXTERN | Anbieterprüfung und Kontofreigabe |
| Rechtstexte und Anbieterkennzeichnung | BLOCKIERT MENSCH | verbindliche Anbieterangaben / Freigabe |
| Zahlungsvertrag und echte Transaktionen | BLOCKIERT MENSCH/EXTERN | keine Sandbox als Ersatz für Vertrag |
| Beta-Tests mit realen Testpersonen | OFFEN | anonymisierte Testprotokolle fehlen |
| Marketing, Marke, Domain, Werbepartner | BLOCKIERT MENSCH/EXTERN | Entscheidungen, Prüfungen und Verträge |

**Abschlussdefinition:** Alle technisch prüfbaren Gates benötigen aktuelle Nachweise; blockierte externe und menschliche Gates dürfen nicht ohne reale Freigabe auf ERLEDIGT gesetzt werden. Keine Veröffentlichung oder Merge durch diesen PR.


## Fortsetzung 13.10.2026 — aktuelle Abnahmebedingungen
- Security T06: OSV-Scannerberichte werden vor dem Lauf entfernt; fehlerhafte/unvollständige Berichte blockieren. Unbekannte CVSS-Vektoren gelten vorsorglich als ungeprüft/blockierend; Regressionstests in `tests/test_security_scan_severity.py`.
- Setup T05: Nutzer können ein geeignetes Modell selbst auswählen und nach der Installation wechseln. Das Windows-Smoke-Build soll keine GGUF-Gewichte mehr einbetten; die CV-Import-Abnahme provisioniert ein isoliertes Modell als Test-Fixture.
- **CI-Gates**: Änderungen nach dem letzten erfolgreichen vollständigen Drei-Workflow-Lauf benötigen neue grüne Ergebnisse für denselben HEAD. Ein ausstehender oder abgebrochener Lauf ist kein Beleg.
- **Realgerät-Gates**: Windows-Download und Neustart, Linux/macOS-Installation, tatsächliche Mail-/Kalender-Anbieter-Verbindung und Browser-Setup müssen auf realen Endnutzergeräten bestätigt werden.
- **Mensch/extern**: Unternehmens- und Anbieterangaben, Rechtstexte, BFSG/CRA-Rechtsbewertung, Zahlungsanbieter-Vertrag, Marken-/Domainprüfung, reale Betatester und Veröffentlichung bleiben ausdrücklich offen. Keine Freigabe durch CI simulieren.
- **Merge-Regel**: PR #144 bleibt bis zu ausdrücklicher Freigabe ungemergt; PR #110 bleibt unangetastet.


## CI-Abnahme und offene Nachweise — 14.10.2026

- **Grüner Integrationsstand:** Commit `f627e585ffd25166f1696d5c87123a9a2cdea3d1`, CI 38485076732, Windows Smoke 38485076748, Desktop Platforms 38485076770: alle drei erfolgreich.
- **Danach geändert:** First-Run-Datenträgererkennung für noch nicht existierende Modellverzeichnisse (`b0dc24b`) sowie Regressionstest (`8287af7`). Der neue Head benötigt eigene vollständige CI-Nachweise.
- **T01–T16:** Bestehende Implementierungen und Tests gelten nicht allein durch den Sammel-PR als reale Endnutzerabnahme. Insbesondere T02 echter Modelltransfer/Probe/Neustart, T03 Update/Rollback von installierter Altversion, T04 reale Desktopinstallationen, T05 Browser- und Wizard-Endnutzerablauf bleiben nachzuweisen.
- **T06–T08, T10, T13:** Automatische Security-, Datenschutz-, SBOM-, Accessibility- und Backup-Prüfungen sind vorhanden; reale/organisatorische Nachweise und ggf. regulatorische Bewertungen sind getrennte Gates.
- **T09, T11–T12, T14–T16:** Entwürfe, Sandbox- und Dokumentationsanteile ersetzen weder verbindliche Unternehmensangaben noch Werbe-/Zahlungsverträge, juristische Freigaben, Marken-/Domainentscheidungen oder reale Beta- und Markttests.
- **Freigaberegel:** Kein Merge, Release oder fingierter Abschluss ohne dokumentierten Nachweis; PR #110 bleibt außerhalb des Scopes.


## T03 Updater — zusätzlicher Code-Gate-Stand (14.10.2026)
- Konsolidierter PR-Branch: `cursor/roadmap-execution-20261012-d85b` (vor Merge; kein Release).
- Windows-Komponentenupdater lehnt ältere Manifest-Sequenzen und unvollständige Cross-Version-Teilupdates ab.
- Fehlende Modellkomponente darf weiterhin aus dem *installierten* Manifest provisioniert werden, ohne App-Version zu mischen.
- Regressionen in `tests/test_app_updates.py` für Downgrade, Cross-Version-App-Teilupdate und beschädigte installierte Release-Kennung ergänzt.
- Bereits vorhanden: HTTPS, SHA256-Prüfung der Parts und der Gesamtdatei, temporärer Download, Dateibackups und PowerShell-Rollback bei Kopierfehlern; unveränderte Nutzerprofile werden nicht in Installationsziele aufgenommen.
- **OFFEN, nicht als T03-Fertigstellung werten**: finaler CI-Lauf für den letzten Head, echter Windows-Altversion→Update→Neustart→Rollback inklusive Profil-Erhalt, Stromausfall-/Startfehler-Rückfall und native macOS/Linux-Update-Abnahme (dort wird aktuell nur der Download eines neuen Pakets geöffnet).

### T03 nativer Upgrade-Baseline-Fix — 18.10.2026 (Branch `data-engine/pr144-native-upgrade-baseline-order`)
- **Ursache:** Die Kandidaten-Sequenz ist `github.run_id` (`desktop-platforms.yml`, `--sequence ${{ github.run_id }}`). `scripts/native_upgrade_baseline.py` wählte den neuesten erfolgreichen `desktop-platforms.yml`-Lauf mit anderem `head_sha`, auch wenn dessen Run-ID **höher** war (später gestartet, früher fertig). `core/native_update_install._validate` lehnt das korrekt als Downgrade ab (`invalid_native_release`), Schritt `Actual installed build upgrade and preserved profile` auf `macos-15-intel` rot. Belegt: #177 Run 39086930936 gegen Baseline 39087873965; #178 Run 39088395098 und #182 Run 39088121412 gegen Baseline 39088631239.
- **Fix:** `select_baseline` bekommt die aktuelle Run-ID explizit, überspringt Läufe mit ID ≥ aktueller ID und nimmt den neuesten älteren erfolgreichen Lauf mit anderem `head_sha`. Kein älterer Lauf → `native_upgrade_baseline_unavailable:no_older_baseline`, Exit 1 (Schritt rot, kein stilles Überspringen). Fehlende/ungültige `GITHUB_RUN_ID` → `native_upgrade_current_run_id_invalid`, Exit 1 vor jedem API-Aufruf. Log: aktuelle Run-ID, übersprungene neuere Run-IDs, gewählte Baseline; `ci_native_upgrade.py` loggt vor `stage_update` Sequenz/Commit von Kandidat und installiertem Stand (nur Logging).
- **Unverändert:** `core/native_update_install.py` (`_validate`, Sequenzlogik, Downgrade-Sperre) und die Sequenz-Definition in `desktop-platforms.yml`.
- **Tests:** `tests/test_native_upgrade_baseline.py` (33, offline, gemockte API), `tests/test_ci_native_upgrade.py` (+1 Log-Test); Datei in der `linux-pytest`-Liste. Lokal grün — **VM, nicht CI**. ~~CI-Run für diesen PR: ausstehend — UNSICHER~~ **Korrektur 18.10.2026 (Kritiker):** #183 gemergt als `78200cc9` (Eltern `0666ce08`, `0b37a4e1`), CI 21/21 grün (per GitHub-API auf `0b37a4e1` und `78200cc9` geprüft: je 21 Check-Runs, alle `success`).
- **Risiko:** Laufen mehr als 30 neuere erfolgreiche Läufe als die erste API-Seite, gibt es keine ältere Baseline → Schritt rot (sichtbar, nicht falsch-grün). Läufe, deren Artefakt abgelaufen ist, werden weiter übersprungen.
- **UNSICHER:** Ob die `macos-15-intel`-Abnahme nach dem Fix vollständig grün wird (andere Ursachen im Upgrade-Schritt nicht ausgeschlossen); Sequenz = Run-ID setzt voraus, dass GitHub Run-IDs monoton nach Startzeit vergeben.
- **Freigabe (Korrektur 18.10.2026):** gemergt als `78200cc9` (Eltern `0666ce08`, `0b37a4e1`), CI 21/21 grün, Merge-Sperre von Damiano am 2026-10-18 17:43 aufgehoben. Der UNSICHER-Punkt zur `macos-15-intel`-Abnahme ist für diesen Stand durch die grüne Desktop-Platforms-Matrix erledigt; für spätere Heads gilt weiter eigene CI.


## Implementierungsinventur für T01–T16 — 14.10.2026

**Ziel:** Nach der Code- und Dokumentationsarbeit bleiben nur CI/Tests und ausdrücklich notwendige externe bzw. menschliche Freigaben. Diese Inventur ist keine Fertigmeldung.

| Paket | Bereits im PR vorhanden | Noch vor einer reinen Testphase zu implementieren / entscheiden |
|---|---|---|
| T01 | Parser-/Such-/Filter-/Dry-Run-Code und Regressionen | Code-Lücken aus vollständiger End-to-End-Pfadprüfung beseitigen; Laufzeit-Baseline dokumentieren |
| T02 | Modell-Download, Hash/Resume, Auswahl und Aktivierungslogik | Fehlerpfade für realen Transfer und Neustart anhand Laufzeitbefunden reparieren |
| T03 | Windows-Komponentenupdater, native Manifest-Checks | Native macOS/Linux-Aktualisierung ist bislang Paketdownload/Öffnen statt atomarem Upgrade/Rollback; Produktumfang festlegen und implementieren |
| T04 | Windows/macOS/Linux Build-Matrix und Paketierung | DMG-Resource-busy-Retry auf allen Runnern verifizieren; reale Geräte bleiben Test-Gate |
| T05 | Setup-Wizard, Browsererkennung, UI-Geometrie | UI-Überläufe und Fokuspfade vollständig abgleichen; echte Browser- und DPI-Tests bleiben Gate |
| T06 | Security-Scanner, Incident-Triage, Bedrohungsmodell | Security-Funde aus vollständigem Audit beheben; CRA-Rechtsbewertung extern |
| T07 | Datenexport/-löschung, Redaction, Datenflussdokumentation | Inkonsistenzen aus Datenflussabgleich beseitigen |
| T08 | SBOM-Exporter, Lizenzinventar | Release-SBOM einschließlich nativer Pakete/Modelle/Daten vervollständigen, falls Inventar lückenhaft |
| T09 | Unveröffentlichte Rechtstext-Entwürfe | Anbieter-/Vertriebsangaben fehlen; finale Rechtstexte benötigen echte Angaben und Freigabe |
| T10 | Accessibility-Bausteine/Regressionen | Festgestellte Tastatur-/Kontrast-/Skalierungslücken beheben; Screenreader-/BFSG-Gates bleiben |
| T11 | Offline-Free-Richtlinie, Premium-/Werbeentwurf | Produktive Werbeeinwilligung und verbindliche Free-/Premium-Gates nur nach Werbe-/Preisentscheidung finalisieren |
| T12 | Paddle-/Entitlement-Sandbox | Live-Zahlungsintegration erfordert Anbieterzugang, Vertrags- und Produktentscheidungen; keine simulierte Freigabe |
| T13 | Support-/Backup-Entwurf, Backup-Aktionen | Betriebshandbuch an tatsächlich implementierten Restore angleichen; reale Kontaktdaten offen |
| T14 | Website-Entwurf | Produktionswebsite, Domain, Marke und Anbieterkennzeichnung sind nicht durch Entwurf ersetzt |
| T15 | Beta-Skripte und Protokollvorlagen | Reale Beta-Durchläufe sind Test-Gate; kein Code-Ersatz |
| T16 | Szenariorechner und Demo-/Wachstumsplanung | Reale Kosten, Kontakte und Marketingentscheidungen nicht aus Code ableitbar |

**Arbeitsregel:** Keine Aufgaben ohne Codebeleg als IMPLEMENTIERT kennzeichnen; keine Rechts-/Provider- oder Gerätefreigaben simulieren. PR #144 nicht mergen, PR #110 nicht anfassen.


## Implementierungsfortsetzung vom 14.10.2026

Der aktuelle paketweise Code-/Übergabestand steht in `PR144_IMPLEMENTATION_HANDOFF.md`. Er ergänzt die historischen Inventuren oben: nativer atomarer Updater, gemeinsamer Modellinstaller, vollständigerer Credential-Wipe, asynchrone Backup-/Restore-Oberfläche, Release-SBOM-Hook und persistente Zahlungssandbox wurden ergänzt. **Keine Tests ausgeführt; CI nicht abgewartet.** Externe Voraussetzungen und Tests sind dort getrennt aufgeführt; keine Produkt-/Rechtsfreigabe.


## Data Engine – ScheduleService Linux (18.10.2026)

Basis `adc297cf27039f806066597e02b4da21a7ff8926`, Branch `data-engine/pr144-schedule-service-linux-v2`, Code-Stand Commit `6f014124e6e29f35a9f6251647230f3a260c2255` (on_login-Fix `99c4eb3be2c574044a5c79e1715bbff18bf5ea3c`, darauf nur dieser Doku-Commit). Nachweis: **VM ohne systemd, nicht i3 — kein Nachweis für echtes systemd.** Kein Punkt wird hier FERTIG gesetzt; T04.08 bleibt OFFEN.

> **Korrektur 18.10.2026 (Kritiker):** #180 wurde als `0666ce08` in den #144-Branch gemergt; sein `linux-real-systemd`-`RESULT: PASS` (Run 39101766329) war ein **False-PASS**: Die erzeugte Service-Unit war wegen `WorkingDirectory="..."` nie ladbar (`LoadState=bad-setting`, Rotnachweis #184, Run 39138285294). Ersetzt/korrigiert durch **#185**, gemergt als `7c388c7f` (gepinnt auf `c1903e82`, 21/21 grün; `linux-real-systemd` Job 117717924588 zeigt Stamp-Entfernung und `clean --what=state ... ok`, `RESULT: PASS`). Die Angaben „CI-Run: ausstehend“ und der `linux-real-systemd`-PASS in den beiden folgenden Zeilen sind dadurch überholt. **T04.08 bleibt OFFEN** bis zur grünen Head-CI auf `7c388c7f`; FERTIG entscheidet Damiano.

| Item | Neuer Nachweis in diesem Patch | Plattform / Lauf | Ergebnis | Risiko / Status |
|---|---|---|---|---|
| ScheduleService Linux | `desktop/services/native_schedule.py`: fehlgeschlagene Aktivierung (kein `systemctl`/User-Bus, `launchctl bootstrap` scheitert, 20-s-Timeout) entlädt den Job zuerst per Name und räumt danach geschriebene Unit-/Plist-Dateien weg; `remove()` entlädt auch ohne vorhandene Dateien per Name und entfernt verwaiste Dateien auch ohne `systemctl`-Binary (`ok=True`). **Neu (Commit `99c4eb3`, Kritiker-Fund on_login):** statt eines gemeinsamen `systemctl --user disable --now <timer> <service>` jetzt `systemctl --user stop <unit>` je Unit einzeln per Name (funktioniert ohne Dateien, Fehler ignoriert) und `systemctl --user disable <unit>` nur für Units, deren Datei existiert (on_login schreibt keinen Timer). `remove()` mit nur der Service-Datei liefert `ok=True`; der Rollback deaktiviert die vorhandene Service-Unit vor dem Löschen (kein `default.target.wants`-Symlink). Regressionen in `tests/test_schedule_service_linux.py` (on_login Install→Timeout→Rollback→Pause, on_login `remove()`, geladener Timer ohne Dateien, Timer-Modus `remove()`, jeweils exakte Kommandolisten; Gegenprobe: 5 davon rot mit altem Code) und `tests/test_adversarial_final_fix.py` | VM Linux x86_64 **ohne systemd** (PID 1 `tini`, kein `systemctl`, kein User-Bus), Python 3.12.14, lokal, nur gezielte Testdateien; jeder neue Commit per `git rebase -x` mit Zeitplaner-Stubs geprüft | alle gezielten Tests grün, `calls.log` leer, keine echten `systemctl`/`launchctl`/`schtasks`-Aufrufe | Risiko gering (nur Nicht-Windows-Pfad). Verhalten auf echtem systemd (`stop` eines nicht geladenen Timers, `disable` nach Timeout) nur gemockt — **UNSICHER**, Nachweis über Job `linux-real-systemd` ausstehend; CI-Run: ausstehend; Status OFFEN bis Kritiker |
| ScheduleService auf echtem systemd (Kandidat für T04.08) | Separater CI-Job `linux-real-systemd` (ubuntu-latest, 10 min, `contents: read`; alle anderen Jobs unverändert): `sudo loginctl enable-linger`, `XDG_RUNTIME_DIR=/run/user/<uid>`, bis zu 30 s Warten auf `systemctl --user` (sonst Job rot). `scripts/ci_real_systemd_schedule_check.py` (Commits `bfbf4f2`, `81e5372`): **Gate** `systemctl --user is-system-running` (Ausgabe + Exit-Code im Log): akzeptiert nur `running` und `degraded`; bei `degraded` wird `systemctl --user list-units --failed` ausgegeben und der Lauf ist rot, falls dort eine Karrierekrake-Unit steht; `offline`, `stopping`, `maintenance`, kein Bus, Sonstiges oder nach 30 s noch `starting` → rot. Danach je Modus `on_login` und `once_daily` nacheinander: Installation, **Pause wie in der App** (`automation_paused=True` + `ScheduleService(cfg).sync_from_config()`, vgl. `MainWindow.set_automation_paused`, Einstellungsseite) → `remove_task()`/`remove()`, `remove()` erneut, erneute Installation, `remove()` auf installierten Units; Rückgabewerte, jeder `systemctl`-Exit-Code und `list-unit-files`/`list-units --all 'karrierekrake*'` nach jedem Schritt, `ls -la` von `default.target.wants`/`timers.target.wants` nach jedem Entfernen. **Assertion** nach jeder Pause/jedem `remove()`: `ok=True`, keine Karrierekrake-Unit-Datei, kein `karrierekrake*`-Eintrag (auch verwaist) in beiden `*.wants`-Verzeichnissen, keine Karrierekrake-Unit in `list-units --all`/`list-unit-files`, sonst rot. ExecStart ist `/bin/true` (CI-Unterklasse überschreibt `_python_command`, der App-Lauf startet nie). Offline-Tests `tests/test_ci_real_systemd_schedule_check.py` (systemctl-Modell in `tmp_path`; Gate-, Pause- und Rest-Fehlerpfade) | CI ubuntu-latest (geplant); lokal nur Offline-Tests mit Modell | offline 23 passed; **CI-Run: ausstehend** | **UNSICHER** bis der CI-Lauf es zeigt. **Nur Linux-Nachweis (systemd-User-Manager auf ubuntu-latest); sagt nichts über Windows (`schtasks`) oder das i3-Zielsystem.** Ob das für T04.08 reicht, entscheidet der Kritiker (`WorkingDirectory="..."` wird nicht per `systemd-analyze verify` geprüft). Toleranz nur für `list-units --all`: nach dem `daemon-reload` von `remove()` bis zu 5 s Polling, bis keine Karrierekrake-Unit mehr gelistet ist; danach noch gelistet → rot, für jede Unit wird `systemctl --user show -p LoadState -p ActiveState <unit>` geloggt (Commit `6f01412`). Unit-Dateien, `*.wants`-Symlinks und `list-unit-files`: keine Toleranz, sofort rot. **Grenzen:** (1) Der Rollback nach einem Timeout von `enable` (der eigentliche Fehlerfall aus #179) wird von `linux-real-systemd` **nicht** gegen echtes systemd geprüft, nur gemockt: **UNSICHER**. (2) `linux-real-systemd` steht nicht in den `needs` von `unit-tests`; ein roter Lauf blockiert nur, weil jeder Check einzeln verlangt wird. Der Kritiker prüft ihn vor der Freigabe ausdrücklich. Kritiker akzeptiert `degraded` nur, wenn `--failed` keine Karrierekrake-Unit enthält. T04.08 bleibt OFFEN |
| linux-pytest-Liste um #180-Tests erweitert | Merge-Commit `7569b8138fda559465b40540af16cca3e5705d7d` übernimmt den #144-Stand inkl. #181 (`b8445f5da35d7325a679750025b47ecb6aa78324`): Jobs `linux-pytest` und `linux-real-systemd` beide unverändert erhalten. Commit `b4a4b12554924c57a9af83e632734a0710de5958` ergänzt nur Listenzeilen der expliziten `linux-pytest`-Dateiliste (11 → 13 Dateien): `tests/test_schedule_service_linux.py`, `tests/test_ci_real_systemd_schedule_check.py` (alle von #180 neu angelegten Testdateien, `git diff --name-status adc297cf..f5ed9d0 -- tests/`, Status A). Auf Kritiker-Wunsch ergänzt Commit `d567fac4714905602f6925d373851793d66c4213` nur die Listenzeile `tests/test_adversarial_final_fix.py` (enthält `test_schedule_service_safe_without_schtasks`, Zeitplaner gemockt, HOME in `tmp_path`; 13 → 14 Dateien) | VM Linux x86_64 ohne systemd, Python 3.12.14, lokal, gleiche Flags wie der Job (`pytest -q -rs`, HOME/XDG_CONFIG_HOME temporär, QT_QPA_PLATFORM=offscreen, Scheduler-Stubs); jeder neue Commit einzeln geprüft — **VM, nicht CI, nicht i3** | 13 Listendateien: 134 passed, 0 failed, 0 skipped; 14 Listendateien (ab `d567fac`): 152 passed, 0 failed, 0 skipped; `calls.log` leer. CI-Lauf auf `226190b` (13 Dateien): `linux-pytest` 134 passed, Guard-Log leer, `linux-real-systemd` `RESULT: PASS` (Run 39101766329) — **False-PASS, siehe Korrektur oben; ersetzt durch #185 (`7c388c7f`)** | Am Head `7c388c7f` enthält die `linux-pytest`-Liste **15 Dateien** (zusätzlich `tests/test_native_upgrade_baseline.py` aus #183). Status OFFEN bis Kritiker |

## Linux-pytest-CI-Job — 18.10.2026 (Branch `data-engine/pr144-linux-pytest-ci`)

| Gate | Status | Nachweis |
|---|---|---|
| Neuer CI-Job `linux-pytest` (ubuntu-latest) in `.github/workflows/ci.yml`, explizite Dateiliste ohne Glob/`nullglob` (fehlende Datei → Job rot): `tests/test_native_schedule.py`, `tests/test_schedule_once_entrypoint.py`, `tests/test_pause_resume.py`, `tests/test_native_model_download.py`, `tests/test_model_download_logs.py`, `tests/test_model_download_recovery.py`, `tests/test_model_download_tls.py`, `tests/test_device_model_setup.py`, `tests/test_setup_model_source_audit.py`, `tests/test_setup_recovery.py`, `tests/test_provider_setup_guides.py` (11 Dateien). Scheduler-Stub-Protokoll (`$RUNNER_TEMP/kk-scheduler-guard/calls.log`) wird im eigenen Schritt `Scheduler guard log` (`if: always()`) ausgegeben; nicht leer → Job rot. PRs #176/#178/#180 ergänzen ihre eigenen Testdateien in dieser Liste. | IMPLEMENTIERT (CI-Head-Commit `667185de8bc4f1d540776059c37c0a20e9c48b0a`; Job eingeführt in `b2cac8a4320685beb9505a263b257cbf37d987d3`) | Lokal: 97 passed, 0 failed, 0 skipped — **VM, nicht CI, nicht i3** (Python 3.12.14, HOME/XDG_CONFIG_HOME temporär, QT_QPA_PLATFORM=offscreen, Scheduler-Stubs; calls.log leer). CI-Run: ausstehend — **UNSICHER**. |
| Änderung an bestehendem Job | ENTWURF, Review nötig (Commit `0a9135687b14bee6f6b2c8066ae6cc18f3c926e0`) | Einzige Änderung an einem bestehenden Job (Entscheidung Teamlead): `unit-tests` bekommt `linux-pytest` in `needs` UND prüft im neuen letzten Schritt `Require linux-pytest success` (`if: always()`) `needs.linux-pytest.result`; damit blockt ein roter, übersprungener oder abgebrochener Linux-Lauf über `unit-tests`. Bestehende Schritte von `unit-tests` unverändert. CI-Nachweis ausstehend — **UNSICHER**. |

## Data Engine – JobSpy/curl_cffi im gebauten Paket und Datenflussabgleich (18.10.2026)

Basis `adc297cf27039f806066597e02b4da21a7ff8926`, Branch `data-engine/pr144-jobspy-package-dataflow`, Code-Stand Commit `d0811e7fcb8acb41fe630ce69790c776dc9f2d9a` (darauf nur der Doku-Commit). Nachweis lokal: **VM, nicht i3. CI-Run: ausstehend.** Kein Punkt wird hier FERTIG gesetzt.

| Item | Neuer Nachweis in diesem Patch | Plattform / Lauf | Ergebnis | Risiko / Status |
|---|---|---|---|---|
| T06.05.07.05.04.02 | `tests/test_search_offline_fixture_pipeline.py`: synthetische Indeed-GraphQL- und LinkedIn-Guest-Fixtures durch den echten JobSpy-1.3.0-Parser, `IndeedSource`/`LinkedInSearchSource`, `normalize_portal_job` und `core.deduplicator.deduplicate`; Socket/DNS/libcurl blockiert, Guard-Selbsttest; `tls_client` in `sys.modules` auf None | VM Linux x86_64, Python 3.12.14, lokal | grün (siehe Patch-README) | UNSICHER bis CI; Fixtures synthetisch, kein Mitschnitt |
| T06.05.07.05.04.03 | `--selfcheck-deps` (`core/security/jobspy_runtime.selfcheck_search_dependencies`) im Desktop-Entry vor Qt; `scripts/ci_frozen_search_deps_check.py` als Schritt in `desktop-platforms` (linux-x86_64, macos-arm64, macos-x86_64) und `windows-smoke/exe-smoke-worker`; Artefakt `search-deps.json` | Lokal nur minimaler PyInstaller-6.22.3-Build (Linux, gleiche Content-Policy, nur Suchstack); vollständiges Paket nicht gebaut | Lokal: jobspy/curl_cffi/libcurl-Native/Scraper/CA-Bundle im Frozen-Prozess OK, tls_client absent; Fehler bei fehlender dist-info für `requests` gefunden und behoben, Re-Build ausstehend | UNSICHER; CI auf allen vier Zielen ausstehend |
| T06.05.07.05.04.04 | Nur OSV/pip-audit der Python-Pakete (wörtlich in `docs/security/JOBSPY_TRANSPORT_DEPENDENCY_DECISION_PR144.md`) | OSV-API, pip-audit 2.10.1 | keine Python-Advisories | OFFEN: native C/BoringSSL/qh3-Quellen, Lizenzen, Advisories nicht erhoben |
| T07.06 | `scripts/network_target_inventory.py` + `docs/privacy/NETWORK_TARGETS_PR144.json` + `tests/test_network_target_reconciliation.py` (neuer Host im Paket ohne Einordnung ⇒ Test rot) | statisch, VM | 54 Hosts: 32 DOKUMENTIERT, 12 UNDOKUMENTIERT, 10 UNSICHER | Inkonsistenzen OFFEN (u. a. Microsoft Graph/IMAP/CalDAV, BRouter, GeoNames, DuckDuckGo nicht im `DATA_INVENTORY`) |

Entscheidung: **tls_client wird nicht aufgenommen** (JobSpy 1.3.0 hat keinen Codepfad dorthin; Indeed/LinkedIn laufen über `requests`, curl_cffi nur als Modulimport). Details und Einordnung des Vorbefunds auf main `accb5cb4`: `docs/security/JOBSPY_TRANSPORT_DEPENDENCY_DECISION_PR144.md`.

### Data Engine – Kritiker-Review Runde 1 (18.10.2026)

- **Abnahmeregel T07.06:** T07.06 bleibt OFFEN, solange irgendein Host mit `kind` = `request` in `docs/privacy/NETWORK_TARGETS_PR144.json` den Status UNDOKUMENTIERT oder UNSICHER hat. Grüne CI (`tests/test_network_target_reconciliation.py`) belegt nur, dass jeder gefundene Host eingeordnet ist; das ist keine Datenschutz-Abnahme. Ein Host darf auf DOKUMENTIERT wechseln, sobald `core/privacy/inventory.py` (`DATA_INVENTORY`) und das Register gemeinsam angepasst sind; kein Test erzwingt mehr, dass bestimmte Hosts undokumentiert bleiben.
- **Netzfreiheit des Self-Checks (T06.05.07.05.04.03):** Linux (`desktop-platforms`, ubuntu-22.04): **ein einziger** Aufruf `sudo unshare -n -- sudo -u "$USER" env HOME="$HOME" PATH="$PATH" sh -c '…'` prüft im Namespace zuerst, dass außer `lo` kein Interface existiert und TCP-Verbindungen zu 1.1.1.1:443 und 8.8.8.8:53 scheitern (sonst rot), und startet danach im **selben** Namespace per `exec` den Self-Check als Runner-User (Review Runde 2; vorher getrennte Namespaces für Vorprüfung und Self-Check). **macOS (arm64, x86_64) und Windows: Netzfreiheit nur im Prozess-Test belegt** (`test_selfcheck_sends_no_request` blockiert Socket/DNS/`Curl.perform`; im Paket zusätzlich Proxy auf 127.0.0.1:1). Restrisiko: Auf diesen drei Zielen gibt es keinen harten Nachweis auf Betriebssystemebene. Der Schritt selbst installiert und lädt nichts (kein pip, kein Download).
- Ergebnisdatei wird atomar geschrieben (`.tmp` + `os.replace`). Bei Timeout wird der Prozessbaum beendet (POSIX: eigene Session + `killpg`; Windows: `taskkill /T /F /PID`, Einschränkung siehe unten). Fehlende informative Module werden als `unavailable` gemeldet, statt den Check abzubrechen.
- Windows-Timeout-Kill (**UNSICHER, nicht abgehakt**): `taskkill /T /F /PID` greift nur, solange der PyInstaller-Bootloader lebt. Stirbt er vorher, bleibt das Kind ohne Elternprozess hängen, und `/T` findet es nicht. Sauber wäre ein Job Object mit `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` (oder eine Suche nach `_MEI`-Prozessen über den Pfad). Bis dahin UNSICHER. Nicht auf echtem Runner geprüft.
- Review Runde 2: Ein Exit-Code ≠ 0 der gebauten Exe zählt jetzt auf **allen** Plattformen als Problem (`evaluate()` in `scripts/ci_frozen_search_deps_check.py`), auch wenn das JSON bereits mit `ok=true` geschrieben wurde (Absturz nach dem Schreiben ⇒ rot). Vorher wurde der Exit-Code unter Windows ignoriert. Offline-Tests in `tests/test_frozen_search_deps_selfcheck.py`.
- CI-Fix Windows-Shard (Commit `207fe66`): `unit-tests-shard (6)` auf `aadc3bd` war rot, weil `tests/test_frozen_search_deps_selfcheck.py::test_ci_timeout_kills_whole_process_tree_on_posix` `sys.platform` auf linux setzt und `os.killpg(pid, signal.SIGKILL)` prüft; unter Windows gibt es `signal.SIGKILL` nicht (`AttributeError`). Nur dieser eine Test hat jetzt `skipif(sys.platform == 'win32')` mit ausdrücklichem Grund (kein Datei-Skip); die POSIX-Assertion ist unverändert und läuft auf Linux/macOS. Der Produktionscode ist nicht betroffen: `scripts/ci_frozen_search_deps_check.py` nutzt `os.killpg`/`signal.SIGKILL` nur im Nicht-win32-Zweig. Neuer Test: ohne `signal.SIGKILL`/`os.killpg` (wie unter Windows) beendet der win32-Timeout-Pfad per `taskkill /T /F` und `run()` bleibt rot (`selfcheck_timeout_after_180s_process_tree_killed`, keine Ergebnisdatei). Die Windows-Exit-Code-Fälle (`exit_code≠0` trotz ok-JSON, fehlender Exit-Code) bleiben ungeskippt. Der Skip-Grund erscheint im Shard-Log, weil die Shards pytest mit `-vv` starten (zeigt `SKIPPED (<Grund>)`; ein `-rs` gibt es dort nicht, Workflow unverändert).
- Status unverändert: nichts FERTIG; .04 OFFEN; .03 offen bis `search-deps.json` auf allen vier Plattformen mit leerem `_problems` vorliegt. Nachweis lokal: VM, nicht i3.
- `linux-pytest`-Liste (Freigabe Teamlead 2026-10-18 20:18): ergänzt ein eigener Commit nur Listenzeilen der expliziten Dateiliste in `.github/workflows/ci.yml`; nach dem Merge von #188-Head `63b75aed` (Revert von #178, `f4cb380a`) 19 → 23 Dateien: `tests/test_jobspy_transport.py` (war vorher nicht gelistet), `tests/test_search_offline_fixture_pipeline.py`, `tests/test_frozen_search_deps_selfcheck.py`, `tests/test_network_target_reconciliation.py`. Kein Test prüft Liste oder Anzahl; die Zählungen weiter oben (11, 13, 14 Dateien) beschreiben frühere Commits und bleiben unverändert. CI-Run: ausstehend — **UNSICHER**.
- Netns-Vorprüfung Linux, nur Log (Freigabe Teamlead 2026-10-18 20:18): Der Schritt in `.github/workflows/desktop-platforms.yml` gibt zusätzlich jede Zeile von `ip -o link show` als `netns_precheck_link: …` aus und je gescheitertem TCP-Connect (1.1.1.1:443, 8.8.8.8:53) eine Zeile `netns_precheck_connect_failed: <ziel> rc=<exit> error=<letzte Fehlerzeile>`, beides vor `netns_precheck_ok`. Abbruchbedingungen unverändert (Interface außer `lo` oder erfolgreicher Connect ⇒ rot), kein Skip, kein `continue-on-error`, keine neuen Rechte, Self-Check-Aufruf unverändert. Test: `test_linux_selfcheck_runs_in_netns_without_network_as_runner_user` prüft die neuen Ausgabezeilen zusätzlich; bestehende Assertions unverändert. CI-Log: ausstehend — **UNSICHER**.

## T02.09-Vorarbeit — CV-Korpus-Modellvergleich (18.10.2026)

| Feld | Inhalt |
|---|---|
| Arbeitspaket | T02.09 (Status in `PR144_WORK_ITEMS.json` bleibt **BLOCKIERT – EXTERN**; Abnahme verlangt: „Downloadvolumen und verbindlichen Qualitätsmaßstab freigeben“). Das hier ist nur Vorarbeit und keine Freigabe. |
| Commit (geprüft) | `adc297cf27039f806066597e02b4da21a7ff8926` (`cursor/roadmap-execution-20261012-d85b`) |
| Plattform | VM 16 GB/8 vCPU, nicht i3 |
| Modelle | ISTA-DASLab Qwen3.5-4B GSQ Q2_K_XL (1 940 825 248 B, sha256 `b7d9ec51fb4d726d31e6bfd47062fb74574a974b93951da6a435b5e35185cb5a`) vs. unsloth Qwen3.5-4B Q4_K_M (2 740 937 888 B, sha256 `00fe7986ff5f6b463e62455821146049db6f9313603938a70800d1fb69ef11a4`) |
| Ergebnis | Q4_K_M: `tests/test_cv_corpus.py` und `tests/test_cv_sollwerte_corpus.py` 24/24 grün, 312/312 Felder, keine Erfindung, Spitze RSS 4603 MiB, 1188 s für 10 CVs. Q2_K_XL: 23/24, Sollwert-Gate rot in beiden Läufen (jeweils DE_05 AUSBILDUNG_1); der Feld-Diff fand im 10-CV-Lauf zusätzlich einen DE_03-Zuordnungsfehler, den das Gate nicht prüft, keine Erfindung, Spitze RSS 2548 MiB, 1351 s. Anschreiben (16 Gold-Fälle): BLOCKIERT (Laufzeit). Matching: nicht evaluiert. 8B/27B: nicht evaluiert. Bericht: `docs/qa/PR144_MODEL_COMPARE_GSQ4B_Q4KM_2026-10-18.md` |
| Risiko | **RAM-Gate:** Q4_K_M verfehlt das 3,3-GB-Peak-Gate (`docs/devops/i3-8gb-peak-rss-gate.md`, ≤ 3 300 000 000 B) schon auf der VM (10-CV-Lauf 4603 MiB, pytest 4649 MiB). Der Peak auf dem i3 ist ungeprüft. Gemessener RSS enthält eingeblendete Gewichtsseiten und ist nicht gleich dem Job-Object-Commit. **Keine Modellempfehlung.** Q2_K_XL spart ca. 45 % RAM, verfehlt aber das Sollwert-Gate reproduzierbar (DE_05, n=2). Als Standardmodell nicht freigabefähig. VM-Zeiten sind nicht auf i3/Endgeräte übertragbar. Kein Qualitätsmaßstab für Anschreiben/Matching gemessen. Unbeaufsichtigtes Senden bleibt aus. |

### Statusvermerk T15.03 / T16.03 (18.10.2026)

Beide stehen in `PR144_WORK_ITEMS.json` auf `IMPLEMENTIERT – PRÜFUNG OFFEN` (wie auf `63b75aed`, Standardstatus) und haben dort keinen `evidence`-Eintrag; die Begründung steht in `status_reason`. Offen bis zum Nachweis:
- **T15.03**: verlangt „Neue Paket-/Commitidentitäten in Ergebnisvorlage übernehmen“. Dafür muss ein finales Paket mit Commit-Identität existieren und in die Beta-Ergebnisvorlage eingetragen sein. Nicht nachgewiesen.
- **T16.03**: verlangt „Demo mit finalem Paket und überprüften Funktionen wiederholen“. Dafür werden ein finales Paket und geprüfte Funktionen benötigt. Nicht nachgewiesen, und dieser Modellvergleich liefert das nicht (Anschreiben/Matching blockiert).

### T02.09 — HR-Urteil Anschreiben-Lauf (18.10.2026)

| Feld | Inhalt |
|---|---|
| Commit | `30af2e2885f08faa2ef61c7f159299bd54e35678` (Branch `personaler/pr144-gsq4b-vs-q4km-compare`, PR #182; Beleg- und Urteils-Commit). Geprüfter Code-Stand des Laufs: `ffa483c34bfc212a86c40ff9392960ed74195ecf` |
| Lauf | Anschreiben-Lauf 2026-10-18 18:38:49–20:23:36 MESZ auf der Box-VM; 16 Gold-Fälle (`docs/qa/anschreiben_gold_briefe.md`, alle `interview`) × 2 Modelle, 32 Läufe, alle Exit 0, keiner abgebrochen |
| Plattform | Linux-VM, **nicht i3** |
| Ergebnis | Q4_K_M: 1 Brief zurückgegeben (cl-10), 15 `review_required`; Q2_K_XL (GSQ 4B): 2 Briefe (cl-10, cl-30), 14 `review_required`. HR-Urteil: **Papierkorb für beide Modelle** (cl-10 Q4: unbelegte Muttersprache, „SAP TM und SAP TM“; cl-30 Q2: falsche Anrede statt „Sehr geehrte Frau Quendel,“; cl-10 Q2: „ideale Kandidatin“ ohne Profilbeleg). Guard fing ADR-Schein (cl-07) und erfundene Ausbildung (cl-20) bei Q4_K_M ab. Keine Qualitätsfreigabe für Anschreiben; Q2_K_XL auch beim Extrakt ohne Freigabe (DE_05 rot). Matching nicht bewertet, 8B/27B nicht bewertet. Belege: `docs/qa/pr144_model_compare_2026-10-18/letters_full/` (`SHA256SUMS` OK). Bericht: `docs/qa/PR144_MODEL_COMPARE_GSQ4B_Q4KM_2026-10-18.md` Abschnitt 4, `docs/personaler/BLIND_REVIEW_BERICHT.md` Abschnitt 7 |
| Risiko | Guard-Lücken (neue Produktfunde, Guard-PR durch Data Engine geplant): falsche Anrede bei benannter Ansprechperson (Entwürfe cl-09/20/28/30, beide Modelle), unbelegte Muttersprache, geschlechtsbezogene Selbstbezeichnung ohne Profilangabe. Unbeaufsichtigtes Absenden bleibt aus. VM-Zeiten/RSS nicht auf i3 übertragbar; Q4_K_M liegt mit 4534–4584 MiB über dem 3,3-GB-Gate. n=1 Lauf je Modell. Briefsprache für cl-10 im Gold nicht festgelegt (**UNSICHER**). |

## PR #176 Download — Versuchsbudget und echte Proxy-Läufe (18.10.2026)

- **Commit:** `0da7d9c` (Fix), dazu die Test-Commits `602a9ed` (Windows: `st_blocks` fehlt dort, der 472-MB-Resume-Test läuft trotzdem) und `1659c8b` (die echte Backoff-Folge min(k, 10) mit Summe 145 s bei 20 Versuchen). Download-Code ändert sich nach `0da7d9c` nicht.
- **Änderung:** Ein Versuch verbraucht das Budget von 3 nur, wenn er keinen gesicherten Fortschritt brachte. Als Fortschritt gilt eine gültige Antwort und eine geflushte `.part`, die mindestens 1 MiB über der bisher größten `.part` liegt. Harte Obergrenze: 20 Versuche. Backoff: höchstens 145 s. Alle drei Werte sind **Schätzungen (UNSICHER)** und nicht gemessen. Content-Range-Prüfung, 416-Pfad, Größen-Cap, SHA-256, atomare Aktivierung und alle Fehlercodes bleiben unverändert. TLS- und Zertifikatsfehler werden nie wiederholt.
- **Plattform:** Linux-Box, echter Download über huggingface.co mit einem TCP-Schnitt im CONNECT-Tunnel. Das ist **kein Zielhardware-Nachweis**.
- **Belege:** `docs/qa/pr144_realdl_2026-10-18/` (Evidence-JSON, App-Logs, beide Harness-Versionen, `SHA256SUMS`).
  - Lauf 1 auf `856768c`: **FAIL** wegen eines Harness-Fehlers (der Schnitt wurde auf einem schon getrennten Tunnel verbraucht). Das App-Log zeigt zusätzlich, dass die App nach 3 Versuchen trotz Fortschritt aufgab.
  - Lauf 2 auf `856768c`: PASS. Vorher-Beleg für den reparierten Harness und den Range-Start gleich `.part`-Größe, zählt nicht für T03.
  - Lauf 3 auf `0da7d9c`: PASS. 4 Versuche, davon nur einer gezählt. Der Range-Start war bei allen Fortsetzungen gleich der `.part`-Größe, die Antworten 206 mit passendem `Content-Range`, die SHA-256 gleich Katalog. Aktivierung erst nach SHA und Probe.
- **Gültigkeit:** Lauf 3 gilt für den finalen #176-Head nur, wenn `git diff 0da7d9c..<final>` weder `guenther/model_manager.py` noch `guenther/setup_models.py` noch eine andere Download-Datei berührt.
- **CI:** Head-CI und `linux-pytest` mit den vier Download-Testdateien von #176 (`tests/test_model_download_resume_interrupted.py`, `tests/test_model_download_restart_truncate.py`, `tests/test_model_download_evidence_logs.py`, `tests/test_model_download_progress_budget.py`; abgeglichen mit der Liste in `.github/workflows/ci.yml`) stehen nach dem #181-Merge und dem Listen-Commit aus.
- **Harness-Skripte (nur Stil, nach den Läufen):** ruff-Funde in beiden Harness-Skripten behoben: Ausführbar-Bit gesetzt (EXE001, Inhalt unverändert), Import-Reihenfolge in `child_main` (I001), `check=False` beim Kind-`subprocess.run` (PLW1510; der Code wertet `returncode` selbst aus, Verhalten wie vorher). Die Läufe 1–3 liefen mit dem vorherigen Stand der Skripte (Stand `e712a5f`, Hashes in `README.md` des Beleg-Ordners); `SHA256SUMS` ist auf den neuen Stand aktualisiert.
- **Risiko:** Die Netzabbrüche außer dem Schnitt kamen vom Box-Netz und sind nicht reproduzierbar. Eine Leitung, die je Versuch weniger als 1 MiB schafft, gibt nach 3 Versuchen auf.

## PR #178 Setup-Schwellen — zurückgenommen (Revert #188)

#178 wurde als `f4cb380a` in #144 gemergt (Eltern `0cb20efc`, `3700879`) und mit #188 (`63b75aed`, `git revert -m 1 f4cb380a`) vollständig zurückgenommen; Baum von `63b75aed` == Baum von `0cb20efc`. Grund: Die Bedingung „#178 nur zusammen mit dem Designer-PR“ (strict-xfail `test_wizard_offers_recommended_4b_on_8gb_laptop`) war bei der Kritiker-Freigabe übersehen worden. Der frühere #178-Abschnitt beschreibt Code, der am Head nicht mehr existiert, und ist entfernt. Wiedereinführung nur im Designer-Paket per Revert-Revert von `63b75aed`; ein erneuter Merge von #178 holt nichts zurück. Nachweis dort je Datei: `git diff <#144-Head> <Revert-Revert>` für die 12 #178-Dateien == Patch `0cb20efc..3700879`, außerhalb davon kein Unterschied.

## Kritiker-Stand 18.10.2026 — #144-Head `cd4bb8d0` (nach Merge #188) und Entscheidungen Damiano

Bezug: `docs/project/PR144_WORK_ITEMS.json` (Schema `karrierekrake.pr144.work-items.v1`), `evidence_commit` `cd4bb8d05ce9e44a8beafa17f0fbd548cfecfaa4` (#144-Head nach Merge von #188, gepinnt auf `63b75aed`; Baum von `cd4bb8d0` == Baum von `63b75aed` (Revert des #178-Merges `f4cb380a`) == Baum von `0cb20efc` (Merge #176, gepinnt auf `bd1106ca`)), Datum 2026-10-18. Die Statusänderungen wurden auf `7c388c7f` erhoben; #176, #178 und #188 ändern `PR144_WORK_ITEMS.json` nicht.

**Entscheidungen Damiano (2026-10-18):**
- 17:45: i3-Messung entfällt. Nur Kriterien, die ausschließlich durch eine Messung auf echter i3-Zielhardware erfüllbar waren, werden `ENTFALLEN` (nie FERTIG). Gates im Code bleiben unverändert. T01.09.03 (CI-Laufzeit) und T08.05.06 (Modell-Lizenztexte) bleiben OFFEN.
- 18:58: (1) ThinkPad-Speedtest bleibt (Performance Optimizer misst); Hardwarezahlen werden nur als Geschwindigkeit mit Gerätename, CPU und RAM laut Messung protokolliert, nicht als i3-Nachweis. (2) i3-Messung entfällt wie oben. (3) Synthetische Accounts/Daten statt echter Accounts/Nutzer/Tester. (4) Das Team entscheidet als Damianos HR (auch T02.09): Personaler urteilt nach `ABNAHME_CHECKLISTE.md`, Kritiker prüft Belege, keine gesenkten Sollwerte, keine echten Bewerbungen.

**Statusänderungen:**

| ID | alt | neu | Grund |
|---|---|---|---|
| T05.06 | OFFEN | ENTFALLEN | Entscheidung Damiano 2026-10-18 17:45: i3-Messung entfällt (nur durch Messung auf schwacher Zielhardware erfüllbar) |
| T01.10 | BLOCKIERT – EXTERN | OFFEN | Entscheidung Damiano 2026-10-18: synthetische Accounts/Daten statt echter |
| T05.07 | BLOCKIERT – EXTERN | OFFEN | Entscheidung Damiano 2026-10-18: synthetische Accounts/Daten statt echter |
| T15.04 | BLOCKIERT – EXTERN | OFFEN | Entscheidung Damiano 2026-10-18: synthetische Accounts/Daten statt echter (Geräte UNSICHER) |
| T02.09 | BLOCKIERT – EXTERN | OFFEN | Entscheidung Damiano 2026-10-18 18:58: Team als HR nach ABNAHME_CHECKLISTE.md |
| T02.08 | BLOCKIERT – EXTERN | OFFEN | Entscheidung Damiano 2026-10-18 18:58: ThinkPad-Speedtest, nur Geschwindigkeit mit Gerätename/CPU/RAM, kein i3-Nachweis; Fujitsu-Verfügbarkeit UNSICHER |
| T15.05 | BLOCKIERT – EXTERN | BLOCKIERT – EXTERN (unverändert, Grund ergänzt) | Teilkriterium Veröffentlichungsfreigabe liegt bei Damianos menschlicher Prüfung von #144 (Veröffentlichen verboten); übrige Teile mit synthetischen Personas |

Unverändert mit ergänztem `status_reason`: T04.08 (OFFEN bis grüne Head-CI auf `7c388c7f`; FERTIG entscheidet Damiano). T15.03 und T16.03 stehen am Head als `IMPLEMENTIERT – PRÜFUNG OFFEN`; der Nicht-Standard-Status `BLOCKIERT/UNSICHER` (Commit `1fc7d822`, #182) ist im #144-Head nicht vorhanden, daher keine Normalisierung.

**Zählstand (232 Leaf-Kriterien):**

| Status | vorher (78200cc9 = 7c388c7f) | jetzt |
|---|---|---|
| FERTIG | 77 | 77 |
| OFFEN | 72 | 76 |
| IMPLEMENTIERT – PRÜFUNG OFFEN | 51 | 51 |
| BLOCKIERT – EXTERN | 32 | 27 |
| ENTFALLEN | 0 | 1 |

**CI:** `7c388c7f` (Merge #185) 21/21 grün (CI 39146079128, Desktop Platforms 39146079075, Windows Smoke 39146079088). Head `63b75aed` (#188): 21/21 Check-Runs `success` (per GitHub-API geprüft), gelaufen als `pull_request` auf dem Merge-Ref `ae6bb93` (Basis `f4cb380a`): CI 39153900734, Windows Smoke 39153900810, Desktop Platforms 39153900724; Logs je Schritt geprüft: `linux-pytest` 19 Dateien 286 passed, Unit-Test-Shards zusammen 7054 passed / 84 skipped / 4 xfailed / 0 failed; `build-and-exe-smoke` ist nur ein Aggregations-Gate (3 s), kein eigener Build-Nachweis. **Diese CI lief auf dem `63b75aed`-Merge-Ref, nicht auf `cd4bb8d0` selbst** (Baum gleich, Commit verschieden). CI auf `cd4bb8d0`: **UNSICHER/ausstehend**, bis sie gelaufen ist. T04.08 bleibt unverändert OFFEN; die Bewertung folgt separat auf dem stabilen #144-Head.

**Hinweise zur CI-Evidenz (UNSICHER, offen):**
- **Upgrade-Baseline der Desktop-Builds aus fremden PR-Branch-Läufen:** Im Desktop-Platforms-Lauf 39153900724 nutzten `build (macos-14, macos-arm64)` und `build (macos-15-intel, macos-x86_64)` die Baseline 39153816811 (Branch `data-engine/pr144-jobspy-package-dataflow`, `2f89ca26`), `build (ubuntu-22.04, linux-x86_64)` die Baseline 39150814493 (Branch `perf/pr144-setup-thresholds` = #178, `37008790`). Die installierte Altversion stammt damit nicht aus einem früheren #144-Stand — als Upgrade-Nachweis für #144 **UNSICHER**.
- **cv-regression Exit-Code hinter Pipe:** Schritt `CV corpus pytest (record slowest cases)` (`.github/workflows/ci.yml`, `shell: pwsh`) leitet `python -m pytest … | Tee-Object -FilePath cv_corpus_matrix.txt`. Dass ein roter pytest-Lauf durch die Pipe den Schritt rot macht, ist nicht per Rotnachweis belegt — **UNSICHER** (der grüne Lauf 39153900734 zeigt 50 passed im Log).

**linux-pytest:** Explizite Dateiliste in `.github/workflows/ci.yml` am Head `cd4bb8d0` (Baum == `63b75aed`): 19 Dateien (15 an `7c388c7f` plus die vier Download-Testdateien aus #176). Die drei #178-Dateien (`tests/test_setup_thresholds.py`, `tests/test_device_check.py`, `tests/test_setup_fits_parity.py`) sind mit #188 wieder entfernt und kommen nur mit dem Designer-Paket zurück. Der CI-Punkt im #176-Abschnitt oben („stehen … aus“) ist erledigt.

## T02.08 — Geschwindigkeit auf dem ThinkPad (PO, 18.10.2026)

- **Plattform:** DESKTOP-JTA4OIM (Lenovo ThinkPad T14 Gen 1), AMD Ryzen 5 PRO 4650U (6 Kerne/12 Threads), 24938991616 B RAM, Windows, llama-cpp-python 0.3.36 (CPU), 6 Threads. **Nur Geschwindigkeit. Kein i3-Nachweis und kein Beleg für das 3,3e9-Byte-Gate** (Entscheidung Damiano, 18.10.2026); `--attest-physical-i3` wurde nicht benutzt.
- **Belege:** `docs/qa/pr144_thinkpad_speed_2026-10-18/` (`speed_8b.json`, `speed_4b.json`, das Messskript byte-identisch wie gelaufen, `SHA256SUMS`, `README.md`). 4B-Datei vor dem Lauf gegen Katalog geprüft (1940825248 B, SHA-256 `b7d9ec51…cb5a`).
- **Ergebnis** (fester deutscher CV-Prompt, n_ctx 2048, max_tokens 128, temperature 0, seed 1, je 3 Läufe):

| Modell | Laden | Prompt tok/s (3 Läufe) | Ausgabe tok/s (3 Läufe) | Wandzeit je Lauf | Spitzen-RSS |
|---|---|---|---|---|---|
| 8B GSQ Q3_K_M | 4,47 s | 17,61 / 16,16 / 14,64 | 4,71 / 4,14 / 4,60 | 46,1 / 51,5 / 50,6 s | 5735849984 B (5,34 GiB) |
| 4B GSQ Q2_K_XL | 1,18 s | 27,80 / 24,10 / 25,78 | 7,09 / 6,56 / 7,04 | 24,5 / 27,3 / 25,5 s | 2284265472 B (2,13 GiB) |

- **Grenzen:** Gleicher Prompt, aber unterschiedliche Tokenizer (8B 335, 4B 309 Prompt-Tokens). 8B erzeugte 128 Tokens (Limit), 4B 94 Tokens (früher beendet); deshalb Raten statt Wandzeiten vergleichen. Der Fujitsu-Teil von T02.08 und jede Qualitätsaussage (Personaler, T02.09) sind hier **nicht** enthalten. T02.08 bleibt BLOCKIERT/OFFEN; den Status setzt nur der Kritiker.
- **Risiko:** Ryzen-Werte lassen sich nicht auf den i3 übertragen. RAM- und Peak-Gates bleiben unverändert.

## PR #178 Setup-Schwellen — Gerätebericht und `low_free_ram` (18.10.2026)

- **Commit:** siehe Head von PR #178 (Branch `perf/pr144-setup-thresholds`); CI-Run des Heads steht aus. **Plattform:** nur Linux-Box, Unit-Tests mit tmp-`HOME`; keine Zielhardware.
- **Ergebnis:** `guenther.device_check.recommend()` übernimmt Modell und Warnungen von `recommend_setup_model`. Bei `low_free_ram` zeigt `DeviceCheck.message()` den Wizard-Text über denselben i18n-Schlüssel `setup.model.warning.low_free_ram` (Wortlaut Designer, DE/EN). Test 7,7/3,0/2: 4B, `low_free_ram`, Berichtszeile == `tr(...)` in DE und EN; 7,7/5,0/2 ohne Zeile.
- **Grenze:** `model_budgets.LOW_FREE_RAM_WARN_GIB`, für 4B etwa 3,57 GiB (3,3e9-Byte-Gate plus 0,5 GiB). Abgeleitet, nicht auf Zielhardware gemessen. T05.06 ist **ENTFALLEN** (Entscheidung Damiano, 18.10.2026 17:45); Wert und Gates bleiben unverändert.
- **Risiko / Grenze des Nachweises:** `check_device()` und `DeviceCheck.message()` werden außerhalb der Tests nirgends aufgerufen; der Gerätebericht wird in der App **nicht angezeigt**. Paritätstests und Hinweiszeile sind daher **kein** Nachweis für UX oder T05.05. Ob der Bericht angezeigt wird, ist eine eigene Aufgabe (Designer, Damiano), nicht Teil von #178.
- **Qualität 4B GSQ (Personaler, 18.10.2026, VM):** 4B GSQ ist **nicht gleichwertig** zu Q4_K_M. Extrakt nicht interview-ready (UNSICHER), Sollwert-Test rot: `test_sollwerte_corpus_production_path_all_pass` (Q2_K_XL 9/10, reproduzierbar rot an DE_05 AUSBILDUNG_1 in beiden Läufen; Q4_K_M 10/10). T02.09 bleibt OFFEN.
- **OFFEN, Entscheidung Damiano:** Darf 4B GSQ trotz rotem Sollwert-Test die Voreinstellung (Empfehlung ohne Attest) bleiben? #178 trifft diese Entscheidung nicht. Die Empfehlung sagt nur, ob ein Modell auf das Gerät passt, nicht wie gut es ist. VM-Spitzen (Q2_K_XL 2587 MiB, Q4_K_M 4649 MiB) sind kein Gate-Beleg; das 3,3e9-Byte-Gate zählt nur auf dem i3 und bleibt unverändert.

### PR #178 — Stand nach Merge von #181 (18.10.2026, Box, Linux, kein Zielhardware-Nachweis)

- **8-GB-Assistent bietet 4B noch nicht an (strict-xfail, Designer).** `tests/test_setup_thresholds.py::test_wizard_offers_recommended_4b_on_8gb_laptop` bleibt strict-xfail, bis der Designer-PR das `ModelSetupPanel` auf `model_budgets.usable_ram_fits` umstellt und den Marker entfernt. Ersatz durch Skip oder neuen xfail ist unzulässig. #178 geht nur zusammen mit dem Designer-PR in #144.
- Commits: `25a82a1` (`st_blocks` nur per `hasattr` übersprungen, mit Warnung), `e5b5f21` (Merge-Commit `b8445f5`), `0733dd4` (`linux-pytest`-Liste: `tests/test_setup_thresholds.py`, `tests/test_device_check.py`), `87dd3e2` (nur ruff-Stil: Import-Block in `guenther/setup_models.py`, `.values()` in einem Test; kein Verhalten geändert).
- Volle Suite auf `0733dd4` (tmp-HOME, offscreen): 7156 passed, 12 failed, 29 skipped, 5 xfailed. Alle 12 roten Tests sind CV-Corpus-Tests mit `model_missing` (Umgebung ohne Corpus-Modell), also weder Beleg noch Gegenbeleg; maßgeblich ist `cv-regression` in der Head-CI.
- Gezielt auf `87dd3e2`: `test_setup_thresholds.py`, `test_device_check.py`, `test_device_model_setup.py` 185 passed, 1 xfailed (der strict-xfail oben).
- `7e1126f` (`recommend_setup_model`: `fits` und Alternativen aus `model_budgets.usable_ram_fits` plus Platte; neue Datei `tests/test_setup_fits_parity.py`, Parität Empfehlung/`fits` über 1584 Rasterfälle). Danach eigener Commit: `tests/test_setup_fits_parity.py` in der `linux-pytest`-Liste von `.github/workflows/ci.yml` (nach `tests/test_device_check.py`).
- ruff (0.17.1) auf den durch #178 geänderten `.py`-Dateien, verglichen mit #144-Head `0666ce08` (je Datei und Regel): 16 neue Funde, alle in `tests/test_model_download_resume_interrupted.py` — 1× F401 (`os` ungenutzt), 15× RUF059 (`part` 8×, `final` 5×, `stages` 2×). Die frühere Aussage „keine neuen Funde gegenüber `b8445f5`“ gilt nicht gegenüber `0666ce08`. Ursache: #178 enthält diese Datei im Stand aus dem Download-Commit `2107be4` (plus `dd4ce21`, `25a82a1`), also vor dem Stil-Fix `e712a5f` in #176. Die Funde entfallen, sobald #176 in #144 ist und #144 in #178 gemergt wird. Die Testdatei wird in #178 bewusst nicht geändert. Alle übrigen Funde sind vorbestehend.
- Nachtrag nach dem Merge von #144-Head `0cb20efc` (enthält #176): `tests/test_model_download_resume_interrupted.py` ist jetzt identisch mit dem #144-Stand, die 16 Funde aus der alten Kopie entfallen damit. Gegenüber `0cb20efc` bleibt in den von #178 geänderten `.py`-Dateien genau ein zusätzlicher Fund: I001 (Import-Reihenfolge) in `guenther/setup_models.py`, `inspect_setup_device`. Er bestand schon auf `ee13f48` und ist reiner Stil.
- Risiko/OFFEN: 4B-GSQ-Standard, Fall (24,18,6) und Peak-Gates pro Modellklasse entscheidet Damiano. Head-CI inkl. `cv-regression` ausstehend.
