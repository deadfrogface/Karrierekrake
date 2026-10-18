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
| Arbeitspaket | T02.09 (Status in `PR144_WORK_ITEMS.json` seit Damianos Entscheidung 2026-10-18 18:58 **OFFEN**, nicht mehr BLOCKIERT – EXTERN; Abnahme verlangt: „Downloadvolumen und verbindlichen Qualitätsmaßstab freigeben“). Das hier ist nur Vorarbeit und keine Freigabe. |
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

**CI:** `7c388c7f` (Merge #185) 21/21 grün (CI 39146079128, Desktop Platforms 39146079075, Windows Smoke 39146079088). Head `63b75aed` (#188): 21/21 Check-Runs `success` (per GitHub-API geprüft), gelaufen als `pull_request` auf dem Merge-Ref `ae6bb93` (Basis `f4cb380a`): CI 39153900734, Windows Smoke 39153900810, Desktop Platforms 39153900724; Logs je Schritt geprüft: `linux-pytest` 19 Dateien 286 passed, Unit-Test-Shards zusammen 7054 passed / 84 skipped / 4 xfailed / 0 failed; `build-and-exe-smoke` ist nur ein Aggregations-Gate (3 s), kein eigener Build-Nachweis. **Diese CI lief auf dem `63b75aed`-Merge-Ref, nicht auf `cd4bb8d0` selbst** (Baum gleich, Commit verschieden). CI auf `cd4bb8d0` selbst (Nachtrag 18.10.2026, 22:40 MESZ): **21/21 grün** (pull_request-Lauf von #144: CI 39159592716, Windows Smoke 39159592701, Desktop Platforms 39159592764); Logs je Schritt geprüft: `linux-pytest` (Job 117769898534) 19 Dateien 286 passed, Shards zusammen 7054 passed / 84 skipped / 4 xfailed / 0 failed, `linux-real-systemd` (Job 117769898354) `RESULT: PASS`, `build-and-exe-smoke` nur Aggregations-Gate. Nachweis gilt für CI-Runner, nicht für Zielhardware. T04.08 bleibt unverändert OFFEN; die Bewertung folgt separat auf dem stabilen #144-Head.

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

## Data Engine – Anschreiben-Guard: Anrede, Geschlecht, Muttersprache (18.10.2026)

- **Basis:** `63b75aed` (Head von #188, Revert von `f4cb380a`; #188 noch nicht gemerged). Branch `data-engine/pr144-letter-guard-salutation`, Guard-Commit `87df598`.
- **Anlass:** Personaler-Urteil zum 16-Fälle-Lauf `letters_full_2026-10-18`: Q4_K_M cl-10 („Meine Muttersprache ist Deutsch“, Profil Deutsch C2), Q2_K_XL cl-10 („ideale Kandidatin“, Bewerber Nils, Profil ohne Geschlecht), Q2_K_XL cl-30 („Sehr geehrte Damen und Herren“, Anzeige nennt Frau Quendel) kamen als `letter_returned` durch.
- **Änderung (`core/cover_guard.py`, nur strenger):** `screen_prepared_letter` meldet zusätzlich (1) eine Anrede, die nicht genau der Anrede entspricht, die `compose_cover_letter` aus genau einer benannten Ansprechperson einer deutschen Anzeige baut (`_greeting_from_ad`), auch fehlende Anrede; (2) gegenderte Selbstbezeichnung (Kandidat/in, Bewerber/in, Fachmann/Fachfrau) ohne ausdrückliche Profilangabe oder mit unpassender Angabe; Vorname zählt nie; (3) Muttersprache/muttersprachlich/native/mother tongue für eine Sprache, die der bestätigte Sprachen-Abschnitt nicht als Muttersprache führt (C2 ist keine). Funde laufen über den bestehenden Weg (`unsupported_personal_claim` → `review_required`; Vorschau-Dialog sperrt Freigabe).
- **Tests:** `tests/test_cover_guard_salutation_gender_native.py` (38), Fixtures `tests/fixtures/letter_guard_2026-10-18/` (echte synthetische Briefe + Gold-Profil/Anzeige, SHA-256 der Evidenz). Vorher rot: 29 failed, 9 passed (alter Guard). Nachher: 38 passed. Gezielte Guard-/Brief-Tests (17 Dateien inkl. neuer): 383 passed, 0 failed, 0 skipped — **VM Linux, nicht CI, nicht i3**. Keine bestehende Testerwartung geändert. Neue Datei in der `linux-pytest`-Liste (19 → 20).
- **Sollwerte:** unverändert. **CI-Run:** ausstehend.
- **Risiko / UNSICHER:** Profil hat kein Geschlechtsfeld → heute ist jede gegenderte Selbstbezeichnung ein Fund (Parameter `applicant_gender` nur vorbereitet). Im LLM-Pfad (`rewrite_cover_letter`) ohne verifizierte Kontakt-Claims meldet der bestehende Kontakt-Validator jede Personenanrede; zusammen mit Regel (1) gehen Anzeigen mit benannter Ansprechperson dort derzeit immer in `review_required` (strenger, kein Brief mehr ohne Prüfung). Mögliche Fehlalarme: Plural mit Artikel („die Bewerber“), Satz, der eine Muttersprachanforderung der Anzeige zitiert. Status OFFEN; Personaler prüft fachlich, Kritiker reviewt.
- **Nachtrag (Teamlead-Entscheidung zu #190):** Nur die technischen Komposita „React Native“ und „cloud-native“ (Leerzeichen oder Bindestrich, groß/klein egal) sind kein Sprach-Claim; jedes andere „native“ zählt weiter. „first language“ zählt im Profil-Level als Muttersprache (`_NATIVE_LEVEL`). Neue Tests: React-Native-/cloud-native-Sätze kein Fund; „native speaker“ und „Muttersprachler“ bleiben Funde (Profil nur C2 und Profil mit Deutsch, nicht Englisch, als Muttersprache; auch im selben Satz wie „React Native“/„cloud-native“); „first language“ erlaubt nur die so markierte Sprache. Rot auf `cbdeaa55`: 5 failed, 44 passed; danach 49 passed; gezielte Guard-/Brief-Tests (17 Dateien): 394 passed, 0 failed, 0 skipped — **VM Linux, nicht CI, nicht i3**. Keine andere Lockerung, keine bestehende Testerwartung geändert. Status OFFEN.
- **Nachtrag (Kritiker-GATE #190, 2 Funde):** (1) Muttersprach- und Geschlechtsprüfung laufen jetzt für jeden Satz **vor** dem Überspringen von Bewerbungssätzen (`_APPLICATION_SENTENCE`: „bewerbe ich mich“, „ausgeschriebene Position“, „persönlichen Gespräch“, „Sehr geehrte“, „Mit freundlichen Grüßen“); der Skip gilt nur noch für die älteren Claim-Prüfungen. Die zweite Fundstelle (`unconfirmed_licence_codes`) prüft nur Führerscheinklassen, keine Muttersprach-/Geschlechtsprüfung, unverändert. (2) Eine Muttersprach-Aussage über eine Sprache, die das Profil nicht als Muttersprache führt, ist ein Fund, auch wenn das Profil eine andere Muttersprache führt: erweiterte geschlossene Sprachliste plus Muster („Muttersprache ist <Wort>“, „<Wort> ist meine Muttersprache“, „Muttersprachler in <Wort>“, „native <Wort> speaker“; nur großgeschriebene Wörter). Rot auf `83ebd14`: 9 failed, 52 passed (u. a. „Hiermit bewerbe ich mich als ideale Kandidatin für die ausgeschriebene Position.“, „Als Muttersprachler bewerbe ich mich …“, „Meine Muttersprache ist Albanisch.“ bei Profil-Muttersprache Deutsch); danach 61 passed; gezielte Guard-/Brief-Tests (17 Dateien): 406 passed, 0 failed, 0 skipped — **VM, nicht CI**. Keine Lockerung, keine bestehende Testerwartung geändert. Status OFFEN.
- **Nachtrag (Kritiker + Personaler #190, auf `3ec2d1f`):** (1) Sprachnamen Deutsch/Englisch werden auf eine Sprach-Id abgebildet (German=Deutsch, English=Englisch, French=Französisch, … Albanian=Albanisch, Persian=Persisch=Farsi, Tigrinya, Kurdish=Kurdisch usw., geschlossene Liste) — in der Muttersprach-Prüfung und in der allgemeinen Claim-Prüfung: „German“ gilt dort nur dann nicht als unbestätigter Anzeigenbegriff, wenn der bestätigte Sprachen-Abschnitt Deutsch führt; Level/Muttersprache folgen daraus nicht. „I am a native German speaker.“ / „My native language is German.“ (Profil Deutsch Muttersprache) und „I speak fluent English.“ (Profil Englisch C1) sind kein Fund mehr; „I speak fluent German.“ ohne Deutsch im Profil bleibt Fund; „Meine Muttersprache ist Albanisch.“, „I am a native Albanian speaker.“, „I am a native English speaker.“ (Englisch B2) bleiben Funde. (2) „Muttersprachler“/„Muttersprachlerin“ zählen als gegenderte Selbstbezeichnung. **Strengere Erwartungsänderung:** die frühere Positivkontrolle „Hiermit bewerbe ich mich als Muttersprachler in Deutsch …“ (Profil Deutsch Muttersprache, ohne Geschlecht) ist jetzt ein Fund; grün nur mit `applicant_gender='m'`, „Muttersprachlerin“ nur mit `'w'`. Rot auf `3ec2d1f`: 7 failed, 69 passed; danach 76 passed; gezielte Guard-/Brief-Tests (17 Dateien): 421 passed, 0 failed, 0 skipped — **VM, nicht CI**. Status OFFEN.
- **Nachtrag (finales Regelwerk Teamlead/Kritiker/Personaler #190, auf `822aeb9`):** (1) Muttersprach-Prüfung satzweise fail-closed: Satz mit Muttersprache/muttersprachlich/Muttersprachler(in)/native/mother tongue/first language muss mindestens eine erkennbare Sprache nennen, und jede genannte Sprache muss im Profil Muttersprache sein; keine erkennbare Sprache = Fund. (2) Einzige Ausnahme Niveau-Aussagen („auf muttersprachlichem Niveau“, „muttersprachliche (Deutsch-/Englisch-)Kenntnisse“): nur wenn genau diese Sprache im Profil C2 oder Muttersprache ist; B2 oder fehlende Sprache = Fund. (3) Gegentests mit Profil Deutsch C2 ohne Muttersprache: „Meine Muttersprache ist Deutsch.“, „Als Muttersprachlerin …“ (Geschlecht w), „I am a native German speaker.“ bleiben Funde. (4) Profilseite: „C2 (nahezu muttersprachlich)“, near native, near-native = C2, nie Muttersprache; Negationen (non-native, keine Muttersprache, nicht muttersprachlich, not native) nie Muttersprache. (5) `apply/manager.py` `_screen_approved_cover`: zusätzlich `screen_prepared_letter(prepare_cover_check(...))`; beide Scans müssen bestehen (alter Scan bleibt, keine Lockerung). Test über den echten Pfad `prepare_and_apply` (Freigabe per `approve_cover_letter`): allgemeine Anrede bei benannter Ansprechperson → `needs_confirmation: unsubstantiated_claims`, Applier nicht aufgerufen (rot auf `822aeb9`). **Strengere Erwartungsänderung:** der aufgezeichnete Q4-cl-10-Brief ist mit Profil Deutsch Muttersprache jetzt ein Fund (der Satz nennt auch Englisch B2); ersetzt durch Einzelsatz-Kontrolle „Meine Muttersprache ist Deutsch.“. Rot auf `822aeb9`: 15 failed, 88 passed; danach 103 passed; gezielte Guard-/Brief-Tests (17 Dateien): 448 passed; Apply-Pfad-Dateien (`test_captcha_stop`, `test_adversarial_final_fix`, `test_submit_guard_auto_flag`, `test_force_submit_respects_dry_run`): 26 passed; jeweils 0 failed, 0 skipped — **VM, nicht CI**. Status OFFEN.
- **Nachtrag (Kritiker-GATE Punkte 1 und 3 #190, auf `c511b8b`):** (1) Zusätzlich zur Satzregel wird jeder Teilsatz (Trennung an `,`/`;`) mit Muttersprach-Marker einzeln geprüft: er braucht eine erkennbare, im Profil erlaubte Sprache (Muttersprache; bei reiner Niveau-Aussage C2/Muttersprache), und das erste Wort links/rechts jedes Markers (Füllwörter wie „ist“, „als“, „ich spreche“, „ebenfalls“, „eigentlich“, „meine“, „speaker“ werden übersprungen) muss eine erlaubte Sprache oder ein bekanntes Nicht-Sprachwort sein, sonst Fund (auch kleingeschrieben). Damit geschlossen: „…, Kurmandschi spreche ich ebenfalls muttersprachlich.“ neben erlaubtem Deutsch. (2) „native“ direkt vor „speaker(s)“ zählt immer als Muttersprach-Marker, auch nach „cloud“/„React-“; „Ich entwickle mit React Native.“ und „cloud-native Architekturen“ bleiben kein Fund. Neue Tests mit den genauen Kritiker-Sätzen (7× Profil Deutsch Muttersprache, 2× Profil Englisch B2) plus Kontrollen. Rot auf `3ec2d1f`: alle 7 Kurmandschi-Sätze und „Als cloud native speaker für Englisch …“; „Als React-Native speaker of English …“ war auf `3ec2d1f` schon Fund (über die allgemeine Claim-Prüfung, „English“ unbestätigt), rot erst auf `c511b8b`. Rot auf `c511b8b`: 3 failed, 115 passed; danach 118 passed; gezielte Guard-/Brief-Tests (17 Dateien): 463 passed; Apply-Pfad-Dateien (4): 26 passed; jeweils 0 failed, 0 skipped — **VM, nicht CI**. Keine Lockerung, keine bestehende Testerwartung geändert. Status OFFEN.
- **Nachtrag (Kritiker-Funde 1–6 + Teamlead-Entscheidungen #190, nach Merge `d031bdf` mit #144-Head `cd4bb8d0`):** Merge-Commit `d031bdf` (kein Rebase, kein Force). (1) Aufzählung: jedes Wort eines Teilsatzes mit Muttersprach-Marker, das kein Füllwort und nicht der Marker selbst ist, zählt als mögliche Sprache und muss erlaubt sein (Muttersprache; bei reiner Niveau-Aussage genau C2/Muttersprache) – „Meine Muttersprache ist Deutsch und auch Kurmandschi.“, „Meine Muttersprachen sind Deutsch und Zazaki.“, „I am a native speaker of German and Kurmanji.“, „Mother tongue: German and Kurmanji.“, „muttersprachliche Kenntnisse in Deutsch und Kurmandschi“ (Profil Deutsch C2) sind Funde. (2) `_STOP` beendet die Prüfung nicht mehr; eine Negation im Marker-Teilsatz ist ein Fund („… ist das Kurmandschi und ich spreche Deutsch.“, „… ist nicht Deutsch sondern Kurmandschi.“). (3) Neue Signale „Erstsprache“, „natively“, „zweisprachig“, „bilingual“ (Teamlead); zweisprachig/bilingual brauchen zwei genannte Sprachen, beide Muttersprache im Profil. (4) Profilseite: „fast wie Muttersprache“, „muttersprachenah“, „Muttersprachniveau“, „almost native“, „native-like“ = C2; „kein native speaker“, „Muttersprache: nein“ = weder C2 noch Muttersprache; Negation wird vor der Annäherung geprüft. (5) `apply/manager.py`: der alte Scan (`screen_cover_letter`) bekommt Muttersprachen, Niveau-Sprachen und Geschlecht aus `prepare_cover_check`; vorher blockierte er jede Muttersprach-Aussage (auch die erlaubte). Neuer Apply-Test mit Sprachprofil (erlaubt/verboten) rot auf `3ec2d1f`, `de7c702` und `d031bdf` (je 1 failed, 1 passed: der erlaubte Fall wurde blockiert). (6) Windows-Shard 3: `test_apply_path_named_contact_letter_reaches_applier` vergleicht die Bytes wie `test_cover_approval_apply.py:125` (gespeicherte Freigabe-Bytes), Inhalt nach `\r\n`→`\n` exakt gleich; Ursache: `save_cover_letter` schreibt im Textmodus (Windows `\r\n`), kein Produktfehler. Rot nur per Windows-Simulation (`Path.write_text` mit `\r\n`) auf der VM. Hinweise: „Ich bin deutscher Muttersprachler.“ – Adjektiv deutscher/deutsche/deutsches → deutsch; Fund bei Geschlecht w/d/unbekannt, grün nur bei m mit Deutsch Muttersprache, Fund bei Deutsch C2. Sprachfeld „Deutsch (Muttersprache)“ → deutsch, Muttersprache (Klammer mit Niveau zählt mit dem Level-Feld, niedrigere Klasse gewinnt). Akzeptierte Fehlalarme bleiben Funde. Rot auf `d031bdf` (neue Tests): Fund 1 6 failed, Fund 2 2 failed, Fund 3 4 failed, Fund 4 7 failed, Fund 5 1 failed/1 passed, Hinweise 4 failed/7 passed. Danach: Guard-Datei 150 passed; 14 Guard-/Brief-/Apply-Dateien 487 passed; `tests/test_cover*.py` + `tests/test_apply*.py` 347 passed; jeweils 0 failed, 0 skipped – **VM, nicht CI**. ruff (E/F/W/I/B/UP, 120) sauber. Keine Lockerung, keine Testerwartung geändert außer der Zeilenende-Normalisierung (6). Status OFFEN.
- **Nachtrag (Teamlead-Entscheidungen #190 auf `b59ae738`):** (1) Leeres Geschlecht: der Guard rät nichts; jede gegenderte Selbstbezeichnung der bestehenden Regel (Kandidat/in, Bewerber/in, Fachmann/-frau, Muttersprachler/in, auch „deutscher Muttersprachler“) und jeder Muttersprach-Fund endet im Apply-Pfad in `needs_confirmation: unsubstantiated_claims` (Job-Status `needs_review`, Applier nicht aufgerufen, freigegebene Bytes unverändert); das war schon so, Nachweis-Test grün auf `b59ae73`. „Ingenieurin“ gehört nicht zur bestehenden Regel (UNSICHER). (2) Fehlalarme: statt „jedes Nicht-Füllwort im Teilsatz“ jetzt eine Sprach-Slot-Prüfung: vom Marker aus über Füllwörter zum Slot-Wort, dann weiter durch Aufzählungen (und/and/oder/sowie/sondern/noch/als auch/as well as/Komma); jedes Slot-Wort muss erlaubte Sprache sein, ein unbekanntes ist Fund; nach einem Verbinder beendet eine neue Phrase („und ich habe …“, „und im Team …“) die Prüfung; bekannte Inhaltswörter (Kenntnisse, Erfahrung, Berufserfahrung, Bereich, Team, Unternehmen, Stelle, Position, …) beenden sie ebenfalls. Teilsatzregel (Marker-Teilsatz braucht erlaubte Sprache; Negation = Fund) bleibt. 11 Gegenfälle ohne Muttersprach-/Geschlechtsfund (rot auf `438c01a`: 8 failed, 3 passed). Alle Kritiker-Sätze der Funde 1–4 bleiben Funde. Neu gefunden (vorher durchgelassen): „Meine Muttersprachen sind Deutsch, Zazaki und Kurmandschi.“, „Meine Muttersprache ist Deutsch, aber auch Kurmandschi.“; neu durchgelassen: „Meine Muttersprache ist Deutsch und die Sprache meiner Eltern Kurmandschi.“ (UNSICHER). (3) Profil: „Erstsprache“ = Muttersprache (Revert `7c37414` von `73342b5`); „zweisprachig“/„bilingual“ = C2 nur für die genannten Sprachen („Deutsch/Englisch: zweisprachig“ → beide C2; Level „zweisprachig“ ohne Sprachnamen → keine), nie Muttersprache; „nicht zweisprachig“/„not bilingual“ = nichts (rot auf `ff662ef`: 5 failed, 3 passed). Kritiker-Paar: Profil Englisch „zweisprachig“ + Brief „Ich bin zweisprachig mit Deutsch und Englisch aufgewachsen.“ = Fund (UNSICHER, Teamlead-Entscheidung offen); beide Muttersprache = kein Fund. Danach: Guard-Datei 174 passed; 14 Dateien 511 passed; `tests/test_cover*.py` + `tests/test_apply*.py` 371 passed; Windows-Simulation 178 passed; `scripts/privacy_scan.py` OK; jeweils 0 failed, 0 skipped – **VM, nicht CI**. Status OFFEN.
- **Nachtrag (Teamlead-Entscheidungen Runde 3 #190 auf `0cb89d05`):** (1) Muttersprach-Prüfung je beanspruchter Sprache: nur die Sprache im Slot eines Markers zählt und wird nur gegen den Profileintrag genau dieser Sprache geprüft; andere Sprachen im Satz mit eigener Niveau-Angabe („…, Englisch spreche ich auf B2-Niveau“, „…, Englisch auf B2“) zählen nicht. Komma nach gefundener Sprache setzt die Aufzählung fort, außer der folgende Teilsatz hat ein eigenes Niveau; nach gefundener Sprache beendet eine Präposition („bei der Nordkai …“) den Slot. „native“/„natively“ nur als eigene Aussage (Selbstbezug, bloßes „native“ nur neben einer Sprache); „mit Native Speakern“, „Native-Apps“, „native Apps“ kein Signal. „auf muttersprachlichem Niveau“ nur für die genannte Sprache (Profil Muttersprache/Erstsprache/C2 = kein Fund). Erwartungsänderung (Teamlead #4): „Meine Muttersprache ist Deutsch, Englisch spreche ich auf B2-Niveau.“ und der Q4-cl-10-Satz mit Profil Deutsch Muttersprache sind kein Fund mehr; Ersatz-Fund „Meine Muttersprache ist Deutsch und Englisch.“; Q4 cl-10 mit Deutsch C2 bleibt Fund. (2) `screen_findings`: Fund mit Satz, Art (native/gender/salutation/claim), Begründungsdaten und Schlüssel sha256(Brieftext + Satz + Art); native/gender/salutation bestätigbar, alle anderen Claims bleiben harte Sperre; die Anrede-Regel liefert denselben Fund (Brief wird nie geändert). (3) Vorschau: pro Fund Satz + Grund als Text und eine Checkbox „Trotzdem freigeben“ (AccessibleName mit Satz, Fokus auf dem ersten Fund, Umbruch bei 640 px); „Entwurf bestätigen“ erst, wenn jeder Fund bestätigt ist; Bestätigungen nur lokal in `logs/cover_guard_confirmations.jsonl` (Schlüssel, Art, Job-Id, Zeit; kein Satztext, kein Netz); nach Neugenerierung ist der Fund wieder offen. Texte schlicht DE/EN in `desktop/i18n.py`, finale Texte liefert das Design. (4) Umformulieren: Modellentwurf mit nur bestätigbaren Funden wird nicht verworfen (`reason=needs_confirmation`), sondern markiert (»…«) mit Grund gezeigt; der alte Text bleibt Standard; „Neuen Text übernehmen“ erst nach Einzelbestätigung; ohne Wahl wird nichts ersetzt. (5) Unbeaufsichtigter Pfad (vollautomatisch, kein Dry-Run): offener Fund bleibt `needs_review`, auch nach Bestätigung in der Vorschau; Applier nicht aufgerufen, Bytes unverändert (End-to-End-Test; grün auf Head, rot unter Mutation). fp190-Lauf (81 synthetische Briefe aus `/workspace/fp190_out`, eigenes Skript): 21 #190-Funde wie Basis, 0 verloren, 0 neu, 0 Fehlalarme/81. Danach: Guard-Datei 203 passed; Vorschau-Bestätigung 17 passed; 14 Dateien 540 passed; `tests/test_cover*.py` + `tests/test_apply*.py` 417 passed; Windows-Simulation 220 passed; linux-pytest-Liste 505 passed, 1 skipped (systemd-analyze fehlt auf der VM); `scripts/privacy_scan.py` OK – **VM, nicht CI**. Status OFFEN.

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

- **MissingDraft (Teamlead + Kritiker, 18.10.2026):** Die 9 Inhaltstests für M4/M9 (Anrede, must_contain, draft_type-Punkte) werfen ohne Entwurf ausdrücklich `MissingDraft(AssertionError)` und tragen `xfail(strict=True, raises=MissingDraft, reason="M<n> <Feld>: no product draft (point 8)")`. Erzeugt das Produkt einen falschen Entwurf, kommt ein normaler AssertionError, der nicht auf `raises` passt, und der Test wird rot. `test_draft_offered_when_gold_allows[4]/[9]` behält `raises=AssertionError`. Ein Selbsttest (kein xfail) belegt beides. M6 `getattr(draft, "attachments", None)` hatte schon einen Default. Lokal 107 passed, 0 failed, 40 xfailed, 0 XPASS — **VM, nicht CI**.
- **Produkt-Fix M9 (Punkte 3 und 6, 18.10.2026) — VM, nicht CI:**


  Jeder Fix-Commit entfernt genau die Marker, die er grün macht. Beide Commits einzeln geprüft (VM, nicht CI).

  | Commit | Zweck | Entfernte Marker | Geänderte Marker | T01.10-Dateien | ganze `linux-pytest`-Liste |
  |---|---|---|---|---|---|
  | `9d38b8e` (vorher) | MissingDraft | — | — | 107 passed, 0 failed, 40 xfailed, 0 XPASS | 392 passed, 1 skipped, 40 xfailed |
  | `3ddc798` | Punkt 3: M9 → `interview_cancelled` (`integrations/email_classify.py`, generische Regel `appointment_cancellation_hits`) | `test_mail_category_matches_gold[9]`; dazu `test_draft_offered_when_gold_allows[9]`, `test_draft_type_item[9-no_own_dates]` und `[9-short]`. Diese drei wären XPASS geworden: M9 ist nicht mehr interview-artig, deshalb gibt der Produktpfad M9 einen GENERAL_REPLY-Entwurf | `test_draft_salutation_exact[9]`: von `raises=MissingDraft` (Punkt 8) auf `raises=AssertionError`, „M9 salutation: 'Guten Tag Frau Helene Brinkmann,' instead of 'Sehr geehrte Frau Brinkmann,' (point 7)“ | 117 passed, 0 failed, 36 xfailed, 0 XPASS | 402 passed, 1 skipped, 36 xfailed |
  | `c145b05` | Punkt 6: CANCELLED-Update-Vorschlag (`integrations/calendar_write.py`: `propose_cancellation_update`, `cancellation_to_ics`, `export_approved_cancellation_ics`) | `test_mail9_exactly_one_cancelled_update`, `test_mail9_cancelled_update_same_uid`, `test_mail9_cancelled_update_higher_sequence` | — | 135 passed, 0 failed, 33 xfailed, 0 XPASS | 420 passed, 1 skipped, 33 xfailed |
  | `3312620` | CI-Fix Fixture (kein Produkt): `calendar.ics` ORGANIZER-Zeilen nach `mailto:` gefaltet statt mitten in der Domain (Privacy-Scan sah `@lindenhof-consulting.ex`/`@nordlicht-logistik.ex`); entfaltet byte-identisch, Domains bleiben `*.example.org`, Gold unverändert. `.gitattributes`: `tests/fixtures/t0110_synthetic_account/** -text` (Windows-Checkout byte-genau; mit `core.autocrlf=true` geprüft: expected.json `5cd3a994…`, Nachtrag `37596182…`; ohne Regel `66d194e0…`) | — | — | 135 passed, 0 failed, 33 xfailed, 0 XPASS | — |
  | `d7830c7` | Punkt 7: Anrede (`integrations/reply_draft.py` `_greeting`/`_formal_salutation`) | `test_draft_salutation_exact[5]`, `test_draft_salutation_exact[9]` | — | 155 passed, 0 failed, 31 xfailed, 0 XPASS | 440 passed, 1 skipped, 31 xfailed |

  Neue grüne Tests:
  - **Punkt 3:** 6 synthetische Fälle, die eine Überanpassung an die Fixture-Mail ausschließen. Jeder wird auch mit abgeschalteter Regel verglichen:
    - „Interview entfällt“ → `interview_cancelled`
    - „cancel the interview“ → `interview_cancelled`
    - Einladung mit „Falls Sie den Termin absagen müssen“ → bleibt `interview`
    - Absage der Bewerbung → bleibt `rejection`
    - Terminverschiebung → bleibt `interview`
    - Absage, die ein früheres Gespräch erwähnt → unverändert gegenüber der abgeschalteten Regel
  - **Punkt 6:**
    - Ohne Freigabe wird nichts exportiert oder geschrieben (`PermissionError`, keine Datei, Snapshot-Hash unverändert).
    - Export erst nach Freigabe; die Kalender-Datei bleibt unverändert, ein Export ist kein Kalender-Write.
    - Mails 1–8 bekommen keinen Vorschlag.
    - Kein Vorschlag bei fehlendem Datum, falscher Uhrzeit, Datum ohne Termin oder vergangenem Termin.
    - SEQUENCE wird aus dem Original gelesen (fehlt sie, gilt 0), dann +1: fehlend→1, 0→1, 1→2, 5→6.
  - Bestehende Produkttests zu Klassifikation (303 passed, 15 errors) und Kalender (553 passed, 17 skipped) haben dieselben Zahlen wie vor dem Fix.

  - **Punkt 7 (Anrede, `d7830c7`):** Regel: steht im verifizierten Kontaktnamen (wie geschrieben) ausdrücklich Frau/Herr (auch Fr./Hr.), dann „Sehr geehrte Frau <Titel> <Nachname>,“ / „Sehr geehrter Herr <Titel> <Nachname>,“; Dr./Prof. bleiben, der Vorname nie. Nachname = letztes Token, bei klein geschriebener Partikel ab dieser („von der Aue“), Doppelnamen ganz. Ohne Frau/Herr gilt die Gold-Regel unverändert: „Guten Tag <Name wie geschrieben>,“ (kein Geschlecht aus Vornamen); kein Kontakt bzw. nur „Frau“ → „Guten Tag,“. Neue grüne Tests: `test_greeting_rule_matches_every_gold_salutation[3,4,5,6,9]` (alle Gold-Anreden, auch M4 ohne Produktentwurf) und 13 synthetische Gegenfälle (Herr, Doppelname, Frau Dr., Herr Prof. Dr., Partikel, Hr., unbekannte Anrede, leer). Ohne Fix 14 rot.

  Gold (`5cd3a994`) und Nachtrag (`37596182`) sind unverändert. Die M9-Entwurfstests sind nicht abgeschwächt.

  ### Vom Produkt erzeugter M9-Entwurf (wörtlich, Pfad GENERAL_REPLY)
  Zu beurteilen gegen die M9-Goldfelder: `salutation` „Sehr geehrte Frau Brinkmann,“, `draft_type` `optional_kurze_kenntnisnahme` (kurz, keine eigenen Termine).

  ```text
  Betreff: Antwort zur Bewerbung

  Sehr geehrte Frau Brinkmann,

  vielen Dank für Ihre Nachricht zur Bewerbung als Sachbearbeitung Disposition (m/w/d) bei Nordlicht Logistik GmbH. Gerne beantworte ich Ihre Rückfragen und freue mich auf die nächsten Schritte.

  Mit freundlichen Grüßen
  Robin Muster
  ```

  Die Heuristiken `no_own_dates` und `short` sind grün; die Anrede entspricht seit `d7830c7` dem Gold. Inhaltlich ist es derselbe allgemeine Textbaustein wie bei M5/M6, mit Rückfragen-Angebot und „nächsten Schritten“ nach einer Terminabsage. Für M9 gibt es dazu kein Goldfeld; das beurteilt der Personaler.

  ### Vorgeschlagenes CANCELLED-Update für M9 (nur Vorschlag, nicht geschrieben)
  ```text
  BEGIN:VCALENDAR
  VERSION:2.0
  PRODID:-//Karrierekrake//DE
  METHOD:PUBLISH
  BEGIN:VEVENT
  SUMMARY:Vorstellungsgespräch Nordlicht Logistik (NL-2026-0412)
  DTSTART;TZID=Europe/Berlin:20261022T100000
  DTEND;TZID=Europe/Berlin:20261022T110000
  DTSTAMP:20261018T070000Z
  UID:t0110-interview-nordlicht-nl-2026-0412@nordlicht-logistik.example.org
  SEQUENCE:1
  LOCATION:Nordlicht Logistik GmbH\, Kaistraße 9\, 00000 Musterstadt
  STATUS:CANCELLED
  END:VEVENT
  END:VCALENDAR
  ```

  ### UNSICHER (M9-Fix)
  - **METHOD:PUBLISH:** Mit METHOD:PUBLISH + STATUS:CANCELLED entfernen manche Kalender den Termin nicht. iTIP (RFC 5546) sieht dafür METHOD:CANCEL vor. Das Gold legt die Methode nicht fest.
  - **RRULE:** Wiederkehrende Termine werden für eine Absage nie gematcht, es gibt dann keinen Vorschlag. Absagen einzelner Vorkommen (RECURRENCE-ID) werden nicht unterstützt.
  - **Datumsformat:** Der Vorschlag braucht ein Datum im Format dd.mm.yyyy im Mailtext. „22.10.“ ohne Jahr, „22. Oktober“ oder englische Datumsformate ergeben keinen Vorschlag.
  - **Sprachen:** Die Absage-Regel ist eine Stichwort-/Regex-Heuristik nur für Deutsch und Englisch.
  - **Datum + Uhrzeit:** Passen sie auf genau einen künftigen, aktiven Termin, wird dieser gewählt. Bei mehreren Treffern gibt es keinen Vorschlag, es wird nicht geraten.
  - **M9-Entwurf:** Siehe oben, Personaler-Urteil.
  - **M9-Text (kein Goldfeld):** Nach der Terminabsage stehen weiter „Rückfragen“/„nächsten Schritte“ im Entwurf, derselbe Textbaustein wie M5. Nicht geändert, weil kein M9-Goldfeld es verlangt.
  - **Anrede-Quelle:** Die Anrede kommt aus dem gespeicherten Kontaktnamen des Falls (`contact_name`, wie geschrieben), nicht direkt aus Signatur/Anrede der eingehenden Mail; `build_action_draft` bekommt die Mail nicht. Steht Frau/Herr nur in der Mail, bleibt es bei „Guten Tag <Name>,“.
  - **Nur ein Namensteil:** „Frau Helene“ (nur Vorname) ist nicht vom Nachnamen unterscheidbar und ergäbe „Sehr geehrte Frau Helene,“. Partikel-Liste (von, van, zu, de, der, …) ist eine Heuristik.

- **Status:** T01.10 bleibt **OFFEN**. Personaler-Urteil über Evidenz und rote Punkte ausstehend. `PR144_WORK_ITEMS.json` unverändert (status_reason kommt über PR #187). Kein Merge nach main.

### Konsolidierung `753b52e8` (Kritiker, 18.10.2026 22:45 MESZ)

Der Teamlead hat #187, #182, #177, #189, #191, #190 und #192 in den #144-Branch gemergt. Die Head-CI auf `753b52e8` ist **rot** und nicht freigegeben. Ursache laut Logs (u. a. `build (macos-14)` Job 117784300004, `exe-smoke-worker` Job 117784226938): `scripts/privacy_scan.py` meldet `tests/fixtures/t0110_synthetic_account/calendar.ics` (ICS-Faltung trennt `example.org` in den ORGANIZER-Zeilen, aus #192) und `tests/test_model_setup_ux.py: pattern windows_user_path` (aus #191). Die Unit-Shards liefen bei Erstellung noch. Aus #190, #191 und #192 wird kein Kriterium FERTIG, bevor die Head-CI 21/21 grün ist und die Logs je Schritt geprüft sind.

## Data Engine – Direkt-Pushes auf #144-Branch (18.10.2026, Box, nicht CI)

Neue Regel: Push direkt auf `cursor/roadmap-execution-20261012-d85b`. Je Push: vorher `git fetch` + `git pull --rebase` nur für eigene ungepushte Commits, betroffene Tests lokal grün. Alle Testzahlen: Box (Linux, offscreen), **nicht CI**.

### A) #192-CI-Fixes (T01.10)
- **Push 1 `2a89b87`** (cherry-pick von `3312620`): `calendar.ics` ORGANIZER nach `mailto:` gefaltet, `.gitattributes` `tests/fixtures/t0110_synthetic_account/** -text`. Grund: Head `753b52e8` CI rot (macos-14-Build, Privacy-Scan: `calendar.ics: non-example email domain @lindenhof-consulting.ex` / `@nordlicht-logistik.ex`). Box: `scripts/privacy_scan.py` auf `753b52e8` 3 Funde, auf `2a89b87` (nach Rebase auf `c503131`, der den `windows_user_path`-Fund des Designers behob) OK. Tests: `test_t0110_synthetic_mail_calendar.py` + `test_privacy_scan.py` + `test_production_content_gate.py` 186 passed, 33 xfailed.
- **Push 2 `466eb40`** (cherry-picks `d7830c7` → `7157a8f` Anrede M9, `126c5f8` → `466eb40` Doku): 12 betroffene Testdateien (T01.10, reply/lifecycle/communications/blackbox/e2e) 532 passed, 31 xfailed; Privacy-Scan OK; ruff auf den zwei Dateien: dieselben Befunde wie vorher (keine neuen; ruff ist kein CI-Gate).
- **Frischer Klon mit `core.autocrlf=true`** (Box, simuliert Windows-Checkout), alle Dateien im Fixture-Ordner byte-genau (`git ls-files --eol`: `attr/-text`, `calendar.ics` `i/crlf w/crlf`, Rest `i/lf w/lf`):
  - `expected.json` `5cd3a9947d8f…` == `GOLD_SHA256` ✔; `expected_addendum_1.json` `375961821f46…` == `ADDENDUM_SHA256` ✔; `extends.sha256` im Nachtrag == `5cd3a994…` == Hash der ausgecheckten Datei ✔ (`test_gold_addendum_1_extends_expected_json_hash`).
  - Weitere Dateien ohne Pin im Repo (nur zur Vollständigkeit): `calendar.ics` `cae79917…`, `inbox.mbox` `3ec11927…`, `account.json` `c1fbc45f…`, `cases.json` `1901df0e…`, `documents.json` `ec8b0e4b…`, `profile.json` `4e9866c8…`, `README.md` `94c4b8ba…` — identisch zum LF-Checkout. Ohne die Regel (Klon von `753b52e8`) wären alle verändert (z. B. `expected.json` `b55d1b11…`, Nachtrag `66d194e0…`). T01.10-Tests im autocrlf-Klon: 128 passed, 33 xfailed.
- **Push 3** (dieser Commit + Testcommit): `test_ics_parser_unfolds_line_folded_inside_mail_domain` und `test_fixture_calendar_organizers_unfold_to_full_example_addresses` in `tests/test_t0110_synthetic_mail_calendar.py` (schon in der linux-pytest-Liste; Workflows unverändert). **Grün von Anfang an**, kein Rot-Schritt möglich ohne Produktverschlechterung: Der Produktparser `integrations/calendar/local_ics.read_calendar` nutzt icalendar 7.3.0 `Calendar.from_ical`, das CRLF+Leerzeichen vor dem Parsen entfaltet. Nachweis, dass der Test greift: Mutation „Fortsetzungszeile nicht entfaltet“ (CRLF+SP → neue Property-Zeile) → 2 failed (`'mailto:…-logistik.ex' != '…example.org'`). Der gefaltete Text wird zur Laufzeit aus der vollen Adresse gebaut, damit der Quelltext keine abgeschnittene Domain für den Privacy-Scan enthält. T01.10 gesamt: 150 passed, 31 xfailed.
- **PR-#192-Text:** Der Satz „Gold, Fixtures und Produktcode bleiben unverändert.“ ist per `gh pr edit 192` ersetzt durch „Gold und Fixtures bleiben unverändert. **Korrektur:** Produktcode ist geändert (`3ddc798` classify, `c145b05` calendar).“ (PR ist gemergt/geschlossen; Body-Edit war möglich).
- **UNSICHER:** Ob Windows-CI mit dem `-text`-Attribut grün ist, ist erst mit der Head-CI belegt (Box, nicht CI). Andere Produkt-ICS-Pfade (`caldav/client.py`, `calendar_write.propose_cancellation_update`) nutzen ebenfalls `Calendar.from_ical`, sind aber nicht eigens mit Mittendomain-Faltung getestet.

## Data Engine – JobSpy-Lizenznachweis und Netzziel-Register T07.06 (18.10.2026, Branch `data-engine/pr144-jobspy-inventory`, nur lokal)

Basis: #144-Head `cd4bb8d05ce9e44a8beafa17f0fbd548cfecfaa4`. Nicht gepusht, kein PR (Vorgabe Damiano). Nachweisort: Box-VM Linux x86_64, venv `/workspace/kk-144-venv`, **nicht CI, nicht i3**.

| Punkt | Commit | Test | Ergebnis | Risiko / offen |
|---|---|---|---|---|
| Pin ↔ `packaging/license_evidence.json` (T08.02.01-Zulieferung) | `e460d92` (Test, rot), `55f7ecb` (Fix, grün) | `tests/test_license_evidence_pins.py` (neu): Evidenzversion = Pin in `constraints-runtime.txt`, jeder Eintrag gepinnt, JobSpy-Netzstack vollständig, Lizenzdatei-SHA256 = installierte Datei | Auf `e460d92`: 2 failed, 5 passed, 1 skipped (jobspy 1.1.82 ≠ 1.3.0; 8 Pakete ohne Eintrag). Auf `55f7ecb`: 16 passed (mit `test_distribution_license.py`) | Lizenzen der statisch eingebetteten libcurl-impersonate-Komponenten nur aus Upstream-Repos, **UNSICHER**; libidn2 GPLv2+/LGPLv3+ statisch gelinkt (Befund); ddgs/primp ungepinnt (Befund); Windows/macOS-Wheels nicht geprüft |
| T07.06 Host-Register `search/` + python-jobspy 1.3.0 in `docs/privacy/data-inventory.md` | `966cbcc` | nur Doku; `scripts/privacy_scan.py` OK | Alle Hosts aus `search/` und JobSpy mit Zweck, Codequelle, Standard/optional, Limits | Statische Analyse ohne Mitschnitt. Neu: `search.brave.com` (ddgs-Fallback). Befund: `company_sites` im Code standardmäßig aktiv (`core/config.py:374–376,1029–1032`). Keine Google Maps/Nominatim-HTTP. ToS/Rate-Limits der Quellen, dynamische Arbeitgeber-Hosts und Hosts außerhalb `search/` bleiben **UNSICHER/OFFEN**. T07.06 bleibt IMPLEMENTIERT – PRÜFUNG OFFEN |

Gezielter Lauf auf dem Branch-Stand: 12 Dateien (`test_license_evidence_pins`, `test_distribution_license`, `test_release_sbom`, `test_runtime_sbom`, `test_embedded_sbom`, `test_jobspy_transport`, `test_production_content_gate`, `test_company_web`, `test_web_search_guard`, `test_public_ats`, `test_source_contracts`, `test_search_adapter`) → 142 passed. CI: keiner (nicht gepusht).


### B) JobSpy-Inventar + `search.brave.com` (Box, nicht CI)
- Cherry-picks von `data-engine/pr144-jobspy-inventory` (Head `968df079`, Basis `cd4bb8d0`) auf #144: `e460d92`→`bbb6b12` (Test rot), `55f7ecb`→`30fffb3` (Fix), `966cbcc`→`7f46c64` (T07.06-Register in `docs/privacy/data-inventory.md`), `968df07`→`f974237` (Doku). Konflikt nur in dieser Datei: beide Seiten behalten. Der Abschnitt „JobSpy-Lizenznachweis …“ oben sagt „nur lokal / nicht gepusht“ – das ist mit diesem Push überholt; er liegt jetzt auf dem #144-Branch.
- Neue Testdatei `tests/test_license_evidence_pins.py` → eine Zeile an die linux-pytest-Liste in `.github/workflows/ci.yml` angehängt (Teamlead-Freigabe); sonst keine Workflow-Änderung.
- **`search.brave.com`:** `test_ddgs_fallback_backend_host_is_scanned` in `tests/test_network_target_reconciliation.py` (rot: 1 failed, 6 passed) → Fix: `scripts/network_target_inventory.py` löst `backend="…"`-Literale in First-Party-Dateien mit `DDGS` auf das ausgelieferte Modul `ddgs/engines/<backend>.py` auf (fehlt ddgs/Engine: sichtbarer Eintrag `ddgs-backend-unresolved:<backend>` statt stillem Auslassen); Register-Eintrag `search.brave.com` `request`/`UNDOKUMENTIERT`/ohne Inventarklasse (wie `html.duckduckgo.com`) → 7 passed. Scan-Labels: `search/company_web.py (ddgs backend=brave)`, `third_party:ddgs/engines/brave.py` (ddgs 9.16.0 im venv).
- Gezielter Lauf (14 Dateien: Lizenz/SBOM/JobSpy/Websuche/Netzziele/Privacy): 153 passed. Privacy-Scan OK.
- **UNSICHER/Befund (nicht geändert):** `company_sites` ist im Code standardmäßig aktiv (`core/config.py`), damit auch DuckDuckGo/Brave-Fallback; ddgs/primp ungepinnt; andere ddgs-Backends (z. B. `auto`) würden nur erkannt, wenn sie als Literal im First-Party-Code stehen. T07.06 bleibt OFFEN, keine Datenschutz-Abnahme.

### C) #190-Fixes am Anschreiben-Guard (Box, nicht CI)
Je Fix ein roter Testcommit, dann ein Fixcommit; gemeinsam gepusht (nur der grüne Endstand ist Head). Alle neuen Tests in bestehenden CI-Dateien (`tests/test_cover_guard_confirmation_ui.py`, `tests/test_cover_guard_salutation_gender_native.py`); Workflows unverändert.

| Fix | Test (rot) | Fix (grün) | Inhalt | Risiko / UNSICHER |
|---|---|---|---|---|
| 1 Überwachter Apply-Pfad | `4ec4204`: 1 failed, 23 passed | `0e8cd96`: 24 passed | `apply/manager.py::_screen_approved_cover`: nur bei `mode == review_before_submit` zählen Vorschau-Bestätigungen, wenn **jeder** Fund bestätigbar ist und sein Schlüssel (`finding_key` = sha256 Brieftext + Satz + Art) für genau diese Job-ID im lokalen Log steht und jede Verletzung beider Scans ein solcher Satz ist (`core/cover_guard.py`: `stored_confirmation_keys`, `confirmed_findings_release`; Log fehlt/kaputt → nichts). `fully_automatic` nutzt Bestätigungen nie. Tests: Freigabe bei exakt diesem Brief (Applier läuft, Dry-Run, Bytes unverändert); andere Briefversion / andere Art / andere Job-ID / kein Log → `needs_review`; harte Angabe (Führerschein) neben bestätigtem Fund → `needs_review`; **unbeaufsichtigter E2E-Test** mit Schlüsseln exakt der gespeicherten Briefversion → `needs_review`, kein Applier-Aufruf. | Der unbeaufsichtigte E2E-Test war auf dem Head schon grün (Head blockte alles); Rot nur per Mutation belegt: Moduscheck entfernt → 2 failed (beide Unattended-Tests), Schlüsselcheck entfernt → 4 failed (Manipulationsfälle). **UNSICHER:** „überwacht“ = `review_before_submit` (meine Auslegung). CRLF: Schlüssel werden auf LF-normalisiertem Brief geprüft (Windows `write_text`), gesendet werden die gespeicherten Bytes. |
| 2 `_show_draft` | `8a379f3`: 2 failed, 24 passed | `6ffb4f0`: 26 passed | Findet der Dialog im Neuentwurf eine harte Angabe, bleibt der alte Text; sichtbarer Texthinweis `apps.preview_draft_rejected` (DE/EN, nennt den Satz, AccessibleName), beim nächsten Ergebnis gelöscht. | Entwurf **ohne** jeden Dialog-Fund wird weiter still verworfen (nicht Teil des Auftrags) – UNSICHER, ob gewollt. |
| 3 „natürlich“ | `3956da8`: 9 failed, 230 passed | `9a07eff`: 239 passed | Fund bleibt (akzeptierter False Positive, fail-closed); Füllwörter (`natürlich`, `selbstverständlich`, …) werden in `screen_findings` nicht als Sprache gemeldet → Grund „Der Brief nennt eine Muttersprache, die dein Profil nicht als Muttersprache bestätigt.“ Gegenfall: `Kurmandschi` behält den Namen. Erkennung unverändert. | Füllwortliste ist eine Heuristik (UNSICHER). Bei „natürlich Deutsch“ nennt der Grund Deutsch nicht mehr namentlich. |
| 4 `_log_confirmation` | `8a276c7`: 4 failed, 27 passed | `0c1d4ed`: 31 passed | Schreiben gibt Erfolg zurück; OSError (oder kein Profil-Root) → Bestätigung zählt nicht: Checkbox springt sichtbar zurück, Hinweis direkt nach der Checkbox erhält den Tastaturfokus: DE „Bestätigung konnte nicht gespeichert werden. Der Satz ist noch nicht freigegeben. Bitte erneut versuchen.“ / EN „Confirmation could not be saved. This sentence is not approved yet. Please try again.“ (`desktop/i18n.py` `apps.preview_finding_save_failed`). Qt-Tests prüfen Text, AccessibleName, Position im Layout und Fokus; erneuter Versuch zählt; Entwurf-Übernahme bleibt gesperrt. | Kein Profil-Root zählt jetzt ebenfalls als „nicht gespeichert“ (fail-closed). |

Unverändert: Prüfung je Sprache, „muttersprachliches Niveau“ bei C2 ok, Geschlecht/Anrede/Muttersprache bestätigbar, andere Angaben harter Block, Log nur lokal (Schlüssel, Art, Job-ID, Zeit; kein Satztext, kein Netz).
Regression (Box): 23 Dateien (Apply/Cover/Preview/a11y/i18n-Nutzer) 714 passed. ruff auf den geänderten Dateien: keine neuen Befunde.
**FP-Lauf 81 Briefe** (Skript wie Runde 3, nur lesend gegen `/workspace/fp190_out/raw_new.json` und `/workspace/fp190_out_v2/raw_new.json`): beide Baselines `letters 81, baseline_hits 21, new_hits_apply 21, new_hits_rewrite 21, kept 21, lost 0, added 0, only_confirmable_findings 2, skipped 1` → keine Abweichung.

### B-Nachtrag) Windows-CI rot durch `test_license_evidence_pins.py` (Ursache: Data Engine)
- Head-CI `d498d40` (CI-Run 39166807270): `unit-tests-shard (1)` und `(4)` (Windows) rot u. a. mit `test_installed_license_file_matches_evidence[charset-normalizer|qh3|curl_cffi]`. Ursache geprüft (Box): die offiziellen `win_amd64`-Wheels (pip download, Python 3.12) liefern denselben LICENSE-Text mit CRLF; LF-normalisiert identisch mit dem Referenz-Hash, macOS-Wheels und reine Python-Wheels stimmen exakt. Damit hätte auch der SBOM-Abgleich (`scripts/distribution_license.py`) auf Windows für diese drei Pakete keinen Lizenznachweis gefunden.
- Test rot (`5f3ce8b`, 2 failed, 20 passed) → Fix (`07d85d7`): `platform_sha256: {"win_amd64": …}` in `packaging/license_evidence.json` für die drei Pakete (exakte Bytes-Hashes der Windows-Wheels); Matcher und Test akzeptieren nur Referenz- oder hinterlegten Plattform-Hash, **keine Normalisierung**; jede andere Byteänderung bleibt rot (Test). 22 passed; 83 Lizenz/SBOM-Tests grün (Box, nicht CI).
- Die übrigen roten Tests derselben Shards (`test_model_setup_lock_reason_visible.py::test_lock_reason_is_fully_painted_at_640[…-200-…]`, Breite 646 ≠ 640) und `linux-pytest` (dieselben 4 Fälle) gehören nicht zu Data-Engine-Änderungen (Designer-Datei), nicht angefasst.
- **UNSICHER:** macOS-arm64/x86_64-Wheels stimmen laut Download überein; Linux-manylinux-Wheel von cffi/curl_cffi/qh3 nur aus dem Box-venv geprüft.

### Windows Smoke `exe-smoke-worker` rot seit #190 (Ursache vermutlich Data Engine, OFFEN)
- Rot auf `52602b8` (39160933968), `aa52a2c` (#190, 39163373020), `753b52e` (39164379417), `d498d40` (39166807179); grün zuletzt auf `cd4bb8d` (39159592701). Auf `aa52a2c`/`753b52e`/`d498d40`: Schritt „Cover-Letter mit demselben Modell“ (`rewrite_cover_letter`, Qwen3.5-4B Q4_K_M) liefert `ok=false`, `error=needs_confirmation`, `validator_issues=[unsupported_personal_claim]` → „Offline CV import EXE acceptance FAILED — release blocked“. `needs_confirmation` gibt es erst seit #190 (`bec375c`): der Modellentwurf enthält einen bestätigbaren Fund (Muttersprache/Geschlecht/Anrede). Auf `52602b8` ist die Ursache im Log nicht als `needs_confirmation` sichtbar (UNSICHER).
- **Nicht gelockert:** Das Gate bleibt (`ok` muss true sein). Welcher Satz/welche Regel feuert, steht nicht im Log (nur Textlänge). Neu: `guard_findings` im Smoke-JSON (Art, Sprache, erwartete Anrede, bestätigbar; kein Satztext) – Test rot→grün in `tests/test_cv_import_exe_offline_metrics.py`. Nächster Schritt nach dem nächsten Windows-Smoke-Lauf: Fund beurteilen (echter Fund → Teamlead-Entscheidung, ob der Smoke `needs_confirmation` als „Entwurf vorhanden, Nutzer muss bestätigen“ werten darf; Falsch-Positiv → Guard-Fix). Bis dahin **UNSICHER/OFFEN**.
