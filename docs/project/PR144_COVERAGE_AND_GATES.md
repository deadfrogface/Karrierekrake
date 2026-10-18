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
- **Tests:** `tests/test_native_upgrade_baseline.py` (33, offline, gemockte API), `tests/test_ci_native_upgrade.py` (+1 Log-Test); Datei in der `linux-pytest`-Liste. Lokal grün — **VM, nicht CI**. CI-Run für diesen PR: ausstehend — **UNSICHER**.
- **Risiko:** Laufen mehr als 30 neuere erfolgreiche Läufe als die erste API-Seite, gibt es keine ältere Baseline → Schritt rot (sichtbar, nicht falsch-grün). Läufe, deren Artefakt abgelaufen ist, werden weiter übersprungen.
- **UNSICHER:** Ob die `macos-15-intel`-Abnahme nach dem Fix vollständig grün wird (andere Ursachen im Upgrade-Schritt nicht ausgeschlossen); Sequenz = Run-ID setzt voraus, dass GitHub Run-IDs monoton nach Startzeit vergeben.
- **Freigabe:** Berührt den Upgrade-/Release-Weg; Merge nur mit Damianos ausdrücklicher Freigabe.


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

Basis `adc297cf27039f806066597e02b4da21a7ff8926`, Branch `data-engine/pr144-schedule-service-linux-v2`, Code-Stand Commit `6f014124e6e29f35a9f6251647230f3a260c2255` (on_login-Fix `99c4eb3be2c574044a5c79e1715bbff18bf5ea3c`, darauf nur dieser Doku-Commit). Nachweis: **VM ohne systemd, nicht i3 — kein Nachweis für echtes systemd; CI-Run: ausstehend.** Kein Punkt wird hier FERTIG gesetzt; T04.08 bleibt OFFEN.

| Item | Neuer Nachweis in diesem Patch | Plattform / Lauf | Ergebnis | Risiko / Status |
|---|---|---|---|---|
| ScheduleService Linux | `desktop/services/native_schedule.py`: fehlgeschlagene Aktivierung (kein `systemctl`/User-Bus, `launchctl bootstrap` scheitert, 20-s-Timeout) entlädt den Job zuerst per Name und räumt danach geschriebene Unit-/Plist-Dateien weg; `remove()` entlädt auch ohne vorhandene Dateien per Name und entfernt verwaiste Dateien auch ohne `systemctl`-Binary (`ok=True`). **Neu (Commit `99c4eb3`, Kritiker-Fund on_login):** statt eines gemeinsamen `systemctl --user disable --now <timer> <service>` jetzt `systemctl --user stop <unit>` je Unit einzeln per Name (funktioniert ohne Dateien, Fehler ignoriert) und `systemctl --user disable <unit>` nur für Units, deren Datei existiert (on_login schreibt keinen Timer). `remove()` mit nur der Service-Datei liefert `ok=True`; der Rollback deaktiviert die vorhandene Service-Unit vor dem Löschen (kein `default.target.wants`-Symlink). Regressionen in `tests/test_schedule_service_linux.py` (on_login Install→Timeout→Rollback→Pause, on_login `remove()`, geladener Timer ohne Dateien, Timer-Modus `remove()`, jeweils exakte Kommandolisten; Gegenprobe: 5 davon rot mit altem Code) und `tests/test_adversarial_final_fix.py` | VM Linux x86_64 **ohne systemd** (PID 1 `tini`, kein `systemctl`, kein User-Bus), Python 3.12.14, lokal, nur gezielte Testdateien; jeder neue Commit per `git rebase -x` mit Zeitplaner-Stubs geprüft | alle gezielten Tests grün, `calls.log` leer, keine echten `systemctl`/`launchctl`/`schtasks`-Aufrufe | Risiko gering (nur Nicht-Windows-Pfad). Verhalten auf echtem systemd (`stop` eines nicht geladenen Timers, `disable` nach Timeout) nur gemockt — **UNSICHER**, Nachweis über Job `linux-real-systemd` ausstehend; CI-Run: ausstehend; Status OFFEN bis Kritiker |
| ScheduleService auf echtem systemd (Kandidat für T04.08) | Separater CI-Job `linux-real-systemd` (ubuntu-latest, 10 min, `contents: read`; alle anderen Jobs unverändert): `sudo loginctl enable-linger`, `XDG_RUNTIME_DIR=/run/user/<uid>`, bis zu 30 s Warten auf `systemctl --user` (sonst Job rot). `scripts/ci_real_systemd_schedule_check.py` (Commits `bfbf4f2`, `81e5372`): **Gate** `systemctl --user is-system-running` (Ausgabe + Exit-Code im Log): akzeptiert nur `running` und `degraded`; bei `degraded` wird `systemctl --user list-units --failed` ausgegeben und der Lauf ist rot, falls dort eine Karrierekrake-Unit steht; `offline`, `stopping`, `maintenance`, kein Bus, Sonstiges oder nach 30 s noch `starting` → rot. Danach je Modus `on_login` und `once_daily` nacheinander: Installation, **Pause wie in der App** (`automation_paused=True` + `ScheduleService(cfg).sync_from_config()`, vgl. `MainWindow.set_automation_paused`, Einstellungsseite) → `remove_task()`/`remove()`, `remove()` erneut, erneute Installation, `remove()` auf installierten Units; Rückgabewerte, jeder `systemctl`-Exit-Code und `list-unit-files`/`list-units --all 'karrierekrake*'` nach jedem Schritt, `ls -la` von `default.target.wants`/`timers.target.wants` nach jedem Entfernen. **Assertion** nach jeder Pause/jedem `remove()`: `ok=True`, keine Karrierekrake-Unit-Datei, kein `karrierekrake*`-Eintrag (auch verwaist) in beiden `*.wants`-Verzeichnissen, keine Karrierekrake-Unit in `list-units --all`/`list-unit-files`, sonst rot. ExecStart ist `/bin/true` (CI-Unterklasse überschreibt `_python_command`, der App-Lauf startet nie). Offline-Tests `tests/test_ci_real_systemd_schedule_check.py` (systemctl-Modell in `tmp_path`; Gate-, Pause- und Rest-Fehlerpfade) | CI ubuntu-latest (geplant); lokal nur Offline-Tests mit Modell | offline 23 passed; **CI-Run: ausstehend** | **UNSICHER** bis der CI-Lauf es zeigt. **Nur Linux-Nachweis (systemd-User-Manager auf ubuntu-latest); sagt nichts über Windows (`schtasks`) oder das i3-Zielsystem.** Ob das für T04.08 reicht, entscheidet der Kritiker (`WorkingDirectory="..."` wird nicht per `systemd-analyze verify` geprüft). Toleranz nur für `list-units --all`: nach dem `daemon-reload` von `remove()` bis zu 5 s Polling, bis keine Karrierekrake-Unit mehr gelistet ist; danach noch gelistet → rot, für jede Unit wird `systemctl --user show -p LoadState -p ActiveState <unit>` geloggt (Commit `6f01412`). Unit-Dateien, `*.wants`-Symlinks und `list-unit-files`: keine Toleranz, sofort rot. **Grenzen:** (1) Der Rollback nach einem Timeout von `enable` (der eigentliche Fehlerfall aus #179) wird von `linux-real-systemd` **nicht** gegen echtes systemd geprüft, nur gemockt: **UNSICHER**. (2) `linux-real-systemd` steht nicht in den `needs` von `unit-tests`; ein roter Lauf blockiert nur, weil jeder Check einzeln verlangt wird. Der Kritiker prüft ihn vor der Freigabe ausdrücklich. Kritiker akzeptiert `degraded` nur, wenn `--failed` keine Karrierekrake-Unit enthält. T04.08 bleibt OFFEN |
| linux-pytest-Liste um #180-Tests erweitert | Merge-Commit `7569b8138fda559465b40540af16cca3e5705d7d` übernimmt den #144-Stand inkl. #181 (`b8445f5da35d7325a679750025b47ecb6aa78324`): Jobs `linux-pytest` und `linux-real-systemd` beide unverändert erhalten. Commit `b4a4b12554924c57a9af83e632734a0710de5958` ergänzt nur Listenzeilen der expliziten `linux-pytest`-Dateiliste (11 → 13 Dateien): `tests/test_schedule_service_linux.py`, `tests/test_ci_real_systemd_schedule_check.py` (alle von #180 neu angelegten Testdateien, `git diff --name-status adc297cf..f5ed9d0 -- tests/`, Status A). Auf Kritiker-Wunsch ergänzt Commit `d567fac4714905602f6925d373851793d66c4213` nur die Listenzeile `tests/test_adversarial_final_fix.py` (enthält `test_schedule_service_safe_without_schtasks`, Zeitplaner gemockt, HOME in `tmp_path`; 13 → 14 Dateien) | VM Linux x86_64 ohne systemd, Python 3.12.14, lokal, gleiche Flags wie der Job (`pytest -q -rs`, HOME/XDG_CONFIG_HOME temporär, QT_QPA_PLATFORM=offscreen, Scheduler-Stubs); jeder neue Commit einzeln geprüft — **VM, nicht CI, nicht i3** | 13 Listendateien: 134 passed, 0 failed, 0 skipped; 14 Listendateien (ab `d567fac`): 152 passed, 0 failed, 0 skipped; `calls.log` leer. CI-Lauf auf `226190b` (13 Dateien): `linux-pytest` 134 passed, Guard-Log leer, `linux-real-systemd` `RESULT: PASS` (Run 39101766329) | CI-Run: ausstehend — **UNSICHER**; Status OFFEN bis Kritiker |

## Linux-pytest-CI-Job — 18.10.2026 (Branch `data-engine/pr144-linux-pytest-ci`)

| Gate | Status | Nachweis |
|---|---|---|
| Neuer CI-Job `linux-pytest` (ubuntu-latest) in `.github/workflows/ci.yml`, explizite Dateiliste ohne Glob/`nullglob` (fehlende Datei → Job rot): `tests/test_native_schedule.py`, `tests/test_schedule_once_entrypoint.py`, `tests/test_pause_resume.py`, `tests/test_native_model_download.py`, `tests/test_model_download_logs.py`, `tests/test_model_download_recovery.py`, `tests/test_model_download_tls.py`, `tests/test_device_model_setup.py`, `tests/test_setup_model_source_audit.py`, `tests/test_setup_recovery.py`, `tests/test_provider_setup_guides.py` (11 Dateien). Scheduler-Stub-Protokoll (`$RUNNER_TEMP/kk-scheduler-guard/calls.log`) wird im eigenen Schritt `Scheduler guard log` (`if: always()`) ausgegeben; nicht leer → Job rot. PRs #176/#178/#180 ergänzen ihre eigenen Testdateien in dieser Liste. | IMPLEMENTIERT (CI-Head-Commit `667185de8bc4f1d540776059c37c0a20e9c48b0a`; Job eingeführt in `b2cac8a4320685beb9505a263b257cbf37d987d3`) | Lokal: 97 passed, 0 failed, 0 skipped — **VM, nicht CI, nicht i3** (Python 3.12.14, HOME/XDG_CONFIG_HOME temporär, QT_QPA_PLATFORM=offscreen, Scheduler-Stubs; calls.log leer). CI-Run: ausstehend — **UNSICHER**. |
| Änderung an bestehendem Job | ENTWURF, Review nötig (Commit `0a9135687b14bee6f6b2c8066ae6cc18f3c926e0`) | Einzige Änderung an einem bestehenden Job (Entscheidung Teamlead): `unit-tests` bekommt `linux-pytest` in `needs` UND prüft im neuen letzten Schritt `Require linux-pytest success` (`if: always()`) `needs.linux-pytest.result`; damit blockt ein roter, übersprungener oder abgebrochener Linux-Lauf über `unit-tests`. Bestehende Schritte von `unit-tests` unverändert. CI-Nachweis ausstehend — **UNSICHER**. |

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

## T01.10 synthetisches Mail-/Kalenderkonto — Abnahmetests gegen Personaler-Gold (18.10.2026, Branch `data-engine/pr144-t0110-synthetic-mail-calendar`)

- **Commit-Reihenfolge:** Inputs `0e17877`, `164f885`, `reference_now` `2f5ab8b` → Gold `86a0e89` (Personaler, `tests/fixtures/t0110_synthetic_account/expected.json`, sha256 `5cd3a9947d8fe1d08081a49d5a73a0d83ec7e9db37bb94a0c551f65cb20dea6c`, unverändert) → Tests `a4f6ecd1fe1180da3ff85f2b6f4f629f6ee884a4` → dieser Listen-/Doku-Commit. Keine Produkt- und keine Fixture-Änderung.
- **Testdateien:** `tests/test_t0110_synthetic_mail_calendar.py` (Uhr eingefroren auf `reference_now` 2026-10-18T09:00:00+02:00; je Mail Kategorie/Fallzuordnung/Entwurf gegen Gold; Import zweimal; IMAP-Stand-in-Sync; `auto_status=False`; Slots Mail 3/4; ICS; SendGate/CalendarWriteGate-Default; sha256-Pin des Golds; Evidenz `t0110_evidence.json/.md` nur in tmp, nicht committet) und `tests/test_t0110_no_network_send.py` (Socket-Guard auch für Loopback, 0 Versuche; Guard rot bei Verstoß; kein `smtplib` in `integrations/`, `core/`, `desktop/`). Beide in der `linux-pytest`-Liste ergänzt (nur Listenzeilen).
- **Lokales Ergebnis — VM, nicht CI:** Python 3.12.14, HOME/XDG_CONFIG_HOME temporär, QT_QPA_PLATFORM=offscreen. Zwei Dateien: 102 Tests, **82 passed, 20 failed** (alle 20 = Abweichung Produkt ↔ Gold, Tests bleiben rot). Ganze `linux-pytest`-Liste (21 Dateien): 367 passed, 20 failed (dieselben 20), 1 skipped. Netzwerkversuche: 0. CI-Run: ausstehend — **UNSICHER**.
- **Gold-Abweichungen (rot):** Mail 1/2 keine Fallzuordnung (Absender `bewerbung@`/`karriere@`, Kennziffer nicht nutzbar: `ApplicationCase` hat kein Referenzfeld); Mail 6 Kategorie `review` statt `document_request`; Mail 9 Kategorie `interview` statt `interview_cancelled`; Mail 3 Slots: Parser liest feste Termine als Wochentagsfenster mit erster Uhrzeit, rankt nie angebotene 21.10./23.10./30.10. und 28.10. 10:00 statt 14:00; ICS: `DTSTART:20261027T090000Z` statt `DTSTART;TZID=Europe/Berlin:20261027T100000` (Zeitpunkt korrekt), kein `LOCATION`; kein Generator für CANCELLED-Update (gleiche UID, SEQUENCE+1) zu Mail 9; Entwürfe: Anrede immer `Guten Tag <wie geschrieben>,` (Mail 5/9 `Guten Tag Frau Helene Brinkmann,`), Kennziffer nie im Entwurf, Mail 3 drei Slots statt genau einem, Mail 4 und Mail 9 kein Entwurf (`no_slots`).
- **UNSICHER / nicht offline prüfbar:** Günther-/LLM-Pfade (gestubbt); semantische must_not-Punkte nur per Stichwort-Heuristik; Ton von „kurzer Dank“/„Kenntnisnahme“; Anhänge (ReplyDraft hat kein Anhangsfeld); user_hints; echte Provider.
- **Kritiker-Nachtrag (18.10.2026):** Netzwerk-Guard sperrt zusätzlich UDP `sendto`/`sendmsg` (inkl. Loopback, Test rot bei Verstoß); `KK_T0110_EVIDENCE_DIR` innerhalb des Repos wird abgelehnt (Warnung, Fallback tmp). Lokal 88 passed, 20 failed (dieselben 20) — **VM, nicht CI**. Nicht im Gold (5cd3a994) festgelegt, daher kein Test: M5 ohne „Rückfragen“/„nächsten Schritte“ und feste UID für das M3-ICS (Gold verlangt nur `uid_stable_on_rerun`) — ausstehend als Gold-Nachtrag des Personalers.
- **Gold-Nachtrag 1 (Personaler, 18.10.2026):** `tests/fixtures/t0110_synthetic_account/expected_addendum_1.json`, sha256 `375961821f46d9da96ebf986871fbbbfad477d51d6dbe286a176b5af419b075f`, byte-identisch im eigenen Commit `c90aca3`; `extends.sha256` = expected.json `5cd3a994…` (Test). Neue Tests M5/M6 (je Punkt ein Test): 8 als `xfail(strict=True, raises=AssertionError)` (M5 must_not_add[0..2], must_contain_add[0]; M6 must_contain_add[0..1], must_not_add[0..1]), grün: M5 `max_sentences_body` 3, Hash-, extends- und Checker-Selbsttest. Prüfungen sind Stichwort-/Regex-Heuristiken — **UNSICHER**. Lokal 92 passed, 20 failed (dieselben 20), 8 xfailed — **VM, nicht CI**. Feste M3-ICS-UID steht auch im Nachtrag nicht, weiterhin kein Test.
- **Kritiker-Bedingung M6-Anhang (18.10.2026):** Der Test „Arbeitszeugnis beigefügt“ prüft das Feld `ReplyDraft.attachments`, nicht den Text. Fehlt das Feld, gibt es einen AssertionError. Erlaubt ist nur `Arbeitszeugnis_Vorarbeitgeber.pdf` (Gold `attachments_allowed`), also kein SQL-Zertifikat, kein Lebenslauf und kein Anschreiben. Der Test ist `xfail(strict=True)`, Grund: „ReplyDraft has no attachments field“. Die Textnennung ist ein eigener, zusätzlicher xfail-Test. Lokal 92 passed, 20 failed (dieselben 20), 9 xfailed — **VM, nicht CI**.
- **Strict-xfail der Original-Abweichungen (Teamlead-Entscheidung, bindend, 18.10.2026):** Dieser Commit folgt auf den Gold-Nachtrag, weil die Gold-Commits schon vorlagen. Jeder Marker lautet `xfail(strict=True, raises=AssertionError, reason="M<n> <Gold-Feld>: <Abweichung>")`. Jeder Test prüft genau eine Abweichung mit genau einem Assert-Block; Tests mit mehreren Asserts sind aufgeteilt, nichts ist abgeschwächt. Ergebnis lokal: beide T01.10-Dateien 106 passed, 0 failed, 40 xfailed, 0 XPASS; ganze `linux-pytest`-Liste (21 Dateien) 391 passed, 1 skipped, 40 xfailed — **VM, nicht CI**.

  **Original-Abweichungen: 20 rote Tests werden 31 strict-xfail-Tests**

  | # | Mail | Test | Gold-Feld | Abweichung | Punkt |
  |---|---|---|---|---|---|
  | 1 | M1 | `test_mail_association_linked_when_gold_has_case[1]` | `case_id` | association_status not linked; no case assignment (sender bewerbung@/karriere@, reference number unusable) | 1 |
  | 2 | M1 | `test_mail_case_assignment_matches_gold[1]` | `case_id` | no case assignment (sender bewerbung@/karriere@, reference number unusable) | 1 |
  | 3 | M2 | `test_mail_association_linked_when_gold_has_case[2]` | `case_id` | association_status not linked; no case assignment (sender bewerbung@/karriere@, reference number unusable) | 1 |
  | 4 | M2 | `test_mail_case_assignment_matches_gold[2]` | `case_id` | no case assignment (sender bewerbung@/karriere@, reference number unusable) | 1 |
  | 5 | M3 | `test_mail3_rank1_is_gold_rank1` | `slot_rank_1` | rank 1 is 21.10. 10:00 instead of 27.10. 10:00 | 4 |
  | 6 | M3 | `test_mail3_ranked_slots_none_invented` | `slots_allowed` | ranks never-offered 21.10./23.10./30.10. and 28.10. 10:00 (weekday-window parse) | 4 |
  | 7 | M3 | `test_mail3_ranked_slots_none_missing` | `slots_allowed` | gold slot 28.10. 14:00-15:00 missing | 4 |
  | 8 | M3 | `test_mail3_ics_dtend_tzid_form_per_gold` | `ics.dtend` | DTEND in UTC Z form, no TZID=Europe/Berlin | 5 |
  | 9 | M3 | `test_mail3_ics_dtstart_tzid_form_per_gold` | `ics.dtstart` | DTSTART:20261027T090000Z (UTC Z) instead of DTSTART;TZID=Europe/Berlin:20261027T100000 | 5 |
  | 10 | M3 | `test_mail3_ics_location_exact` | `ics.location` | no LOCATION in the product ICS | 5 |
  | 11 | M3 | `test_draft_must_contain[mail3-BW-DA-7731]` | `must_contain` | reference number BW-DA-7731 never in the draft | 8 |
  | 12 | M3 | `test_draft_type_item[3-acceptance_wording]` | `draft_type.acceptance_wording` | proposes slots, no acceptance wording | 8 |
  | 13 | M3 | `test_draft_type_item[3-exactly_one_slot]` | `draft_type.exactly_one_slot` | proposes three dates (21.10./23.10./27.10.) instead of accepting exactly one | 8 |
  | 14 | M4 | `test_draft_must_contain[mail4-Projektkoordination Marketing]` | `must_contain` | no product draft (no_slots:fail_safe:no_candidates) | 8 |
  | 15 | M4 | `test_draft_must_contain[mail4-TM/26/118]` | `must_contain` | no product draft (no_slots:fail_safe:no_candidates) | 8 |
  | 16 | M4 | `test_draft_must_contain[mail4-Talweg Medien]` | `must_contain` | no product draft (no_slots:fail_safe:no_candidates) | 8 |
  | 17 | M4 | `test_draft_offered_when_gold_allows[4]` | `draft_allowed` | no product draft (no_slots:fail_safe:no_candidates) | 8 |
  | 18 | M4 | `test_draft_salutation_exact[4]` | `salutation` | no product draft (no_slots:fail_safe:no_candidates) | 8 |
  | 19 | M4 | `test_draft_type_item[4-alternative_request]` | `draft_type.alternative_request` | no product draft (no_slots:fail_safe:no_candidates) | 8 |
  | 20 | M4 | `test_draft_type_item[4-no_acceptance]` | `draft_type.no_acceptance` | no product draft (no_slots:fail_safe:no_candidates) | 8 |
  | 21 | M5 | `test_draft_salutation_exact[5]` | `salutation` | 'Guten Tag Frau Helene Brinkmann,' instead of 'Sehr geehrte Frau Brinkmann,' | 7 |
  | 22 | M6 | `test_mail_category_matches_gold[6]` | `category` | product review instead of document_request | 2 |
  | 23 | M6 | `test_draft_must_contain[mail6-BW-DA-7731]` | `must_contain` | reference number BW-DA-7731 never in the draft | 8 |
  | 24 | M9 | `test_mail_category_matches_gold[9]` | `category` | product interview instead of cancellation | 3 |
  | 25 | M9 | `test_mail9_cancelled_update_higher_sequence` | `calendar_after_import.proposed_change` | no SEQUENCE > original; no generator for a CANCELLED update (calendar_write/ics_export lack STATUS/SEQUENCE) | 6 |
  | 26 | M9 | `test_mail9_cancelled_update_same_uid` | `calendar_after_import.proposed_change` | no update with UID t0110-interview-nordlicht-nl-2026-0412@nordlicht-logistik.example.org; no generator for a CANCELLED update (calendar_write/ics_export lack STATUS/SEQUENCE) | 6 |
  | 27 | M9 | `test_mail9_exactly_one_cancelled_update` | `calendar_after_import.proposed_change` | 0 CANCELLED updates; no generator for a CANCELLED update (calendar_write/ics_export lack STATUS/SEQUENCE) | 6 |
  | 28 | M9 | `test_draft_offered_when_gold_allows[9]` | `draft_allowed` | no product draft (no_slots:fail_safe:no_conflict_free_slots) | 8 |
  | 29 | M9 | `test_draft_salutation_exact[9]` | `salutation` | no product draft (no_slots:fail_safe:no_conflict_free_slots) | 8 |
  | 30 | M9 | `test_draft_type_item[9-no_own_dates]` | `draft_type.no_own_dates` | no product draft (no_slots:fail_safe:no_conflict_free_slots) | 8 |
  | 31 | M9 | `test_draft_type_item[9-short]` | `draft_type.short` | no product draft (no_slots:fail_safe:no_conflict_free_slots) | 8 |

  **Alt → neu**

  | Alter roter Test | Neu (jede Original-Assertion steht in genau einem Test) |
  |---|---|
  | `test_mail_category_matches_gold[6]`, `[9]` | unverändert, markiert |
  | `test_mail_case_assignment_matches_gold[1]`, `[2]` (2 Asserts) | `case_id ==` → `test_mail_case_assignment_matches_gold[n]`; `association_status == linked` → `test_mail_association_linked_when_gold_has_case[n]` |
  | `test_mail3_ranked_slots_exactly_gold` (`sorted(got) == sorted(gold)`) | `…_none_invented` (got−gold = ∅) + `…_none_missing` (gold−got = ∅) + `…_no_duplicates` (grün); zusammen dieselbe Multimengen-Gleichheit |
  | `test_mail3_rank1_is_gold_rank1` (2 Asserts) | `ranked_slots` nicht leer → `test_mail3_has_ranked_slots` (grün); Rang 1 == Gold → `test_mail3_rank1_is_gold_rank1` |
  | `test_mail3_ics_dtstart_dtend_tzid_form_per_gold` (2 Asserts) | `test_mail3_ics_dtstart_tzid_form_per_gold` + `test_mail3_ics_dtend_tzid_form_per_gold` |
  | `test_mail3_ics_location_exact` | unverändert, markiert |
  | `test_mail9_cancellation_proposal_same_uid_higher_sequence` (Gold-Precondition + erzeugt/UID/STATUS/SEQUENCE) | Gold-Precondition → `test_mail9_gold_requires_cancelled_update_same_uid_higher_sequence` (grün); erzeugt + STATUS → `test_mail9_exactly_one_cancelled_update` (Anzahl == 1); UID → `test_mail9_cancelled_update_same_uid`; SEQUENCE > Original (0) → `test_mail9_cancelled_update_higher_sequence` |
  | `test_draft_offered_with_gold_draft_type[3]`, `[4]`, `[9]` (Entwurf vorhanden + alle draft_type-Prüfungen) | Entwurf vorhanden → `test_draft_offered_when_gold_allows[n]`; jede draft_type-Prüfung → `test_draft_type_item[n-item]` (M3 `slot_time` grün) |
  | `test_draft_salutation_exact[4]`, `[5]`, `[9]` (Entwurf vorhanden + Anrede) | Entwurf vorhanden → `test_draft_offered_when_gold_allows[n]`; Anrede == Gold → `test_draft_salutation_exact[n]` (ohne Entwurf ungleich) |
  | `test_draft_must_contain[mail3/mail4×3/mail6]` (Entwurf vorhanden + needle) | Entwurf vorhanden → `test_draft_offered_when_gold_allows[n]`; needle im Text → `test_draft_must_contain[…]` (ohne Entwurf leerer Text) |

  **Gold-Nachtrag 1: 9 strict-xfail-Tests**

  | # | Mail | Test | Nachtrag-Feld | Abweichung |
  |---|---|---|---|---|
  | 1 | M5 | `test_m5_addendum_no_offer_to_answer_questions` | `must_not_add[0]` | bietet Rückfragen an |
  | 2 | M5 | `test_m5_addendum_no_next_steps_or_interview_expectation` | `must_not_add[1]` | „freue mich auf die nächsten Schritte“ |
  | 3 | M5 | `test_m5_addendum_no_generic_boilerplate` | `must_not_add[2]` | allgemeiner GENERAL_REPLY-Textbaustein |
  | 4 | M5 | `test_m5_addendum_thanks_for_feedback` | `must_contain_add[0]` | nur „Dank für Ihre Nachricht“ |
  | 5 | M6 | `test_m6_addendum_refers_to_requested_documents` | `must_contain_add[0]` | kein Bezug auf die Unterlagen |
  | 6 | M6 | `test_m6_addendum_arbeitszeugnis_attached_field` | `must_contain_add attachment` | ReplyDraft hat kein Feld attachments |
  | 7 | M6 | `test_m6_addendum_arbeitszeugnis_named_attached_in_text` | `must_contain_add[1] text` | Arbeitszeugnis im Text nicht als beigefügt genannt |
  | 8 | M6 | `test_m6_addendum_no_questions_or_next_steps_substitute` | `must_not_add[0]` | Rückfragen/„nächste Schritte“ statt einer Antwort |
  | 9 | M6 | `test_m6_addendum_no_generic_boilerplate` | `must_not_add[1]` | Textbaustein |

- **Status:** T01.10 bleibt **OFFEN**. Personaler-Urteil über Evidenz und rote Punkte ausstehend. `PR144_WORK_ITEMS.json` unverändert (status_reason kommt über PR #187). Kein Merge nach main.
