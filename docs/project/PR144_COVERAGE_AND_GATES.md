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

Basis `adc297cf27039f806066597e02b4da21a7ff8926`, Branch `data-engine/pr144-schedule-service-linux-v2`, Code-Stand Commit `bfbf4f29dde705dbc6c2cc36928aa1bd32dce847` (on_login-Fix `99c4eb3be2c574044a5c79e1715bbff18bf5ea3c`, darauf nur dieser Doku-Commit). Nachweis: **VM ohne systemd, nicht i3 — kein Nachweis für echtes systemd; CI-Run: ausstehend.** Kein Punkt wird hier FERTIG gesetzt; T04.08 bleibt OFFEN.

| Item | Neuer Nachweis in diesem Patch | Plattform / Lauf | Ergebnis | Risiko / Status |
|---|---|---|---|---|
| ScheduleService Linux | `desktop/services/native_schedule.py`: fehlgeschlagene Aktivierung (kein `systemctl`/User-Bus, `launchctl bootstrap` scheitert, 20-s-Timeout) entlädt den Job zuerst per Name und räumt danach geschriebene Unit-/Plist-Dateien weg; `remove()` entlädt auch ohne vorhandene Dateien per Name und entfernt verwaiste Dateien auch ohne `systemctl`-Binary (`ok=True`). **Neu (Commit `99c4eb3`, Kritiker-Fund on_login):** statt eines gemeinsamen `systemctl --user disable --now <timer> <service>` jetzt `systemctl --user stop <unit>` je Unit einzeln per Name (funktioniert ohne Dateien, Fehler ignoriert) und `systemctl --user disable <unit>` nur für Units, deren Datei existiert (on_login schreibt keinen Timer). `remove()` mit nur der Service-Datei liefert `ok=True`; der Rollback deaktiviert die vorhandene Service-Unit vor dem Löschen (kein `default.target.wants`-Symlink). Regressionen in `tests/test_schedule_service_linux.py` (on_login Install→Timeout→Rollback→Pause, on_login `remove()`, geladener Timer ohne Dateien, Timer-Modus `remove()`, jeweils exakte Kommandolisten; Gegenprobe: 5 davon rot mit altem Code) und `tests/test_adversarial_final_fix.py` | VM Linux x86_64 **ohne systemd** (PID 1 `tini`, kein `systemctl`, kein User-Bus), Python 3.12.14, lokal, nur gezielte Testdateien; jeder neue Commit per `git rebase -x` mit Zeitplaner-Stubs geprüft | alle gezielten Tests grün, `calls.log` leer, keine echten `systemctl`/`launchctl`/`schtasks`-Aufrufe | Risiko gering (nur Nicht-Windows-Pfad). Verhalten auf echtem systemd (`stop` eines nicht geladenen Timers, `disable` nach Timeout) nur gemockt — **UNSICHER**, Nachweis über Job `linux-real-systemd` ausstehend; CI-Run: ausstehend; Status OFFEN bis Kritiker |
| ScheduleService auf echtem systemd (Kandidat für T04.08) | Neuer, separater CI-Job `linux-real-systemd` (ubuntu-latest, 10 min, `contents: read`; `linux-pytest` und alle anderen Jobs unverändert): `sudo loginctl enable-linger`, `XDG_RUNTIME_DIR=/run/user/<uid>`, bis zu 30 s Warten auf `systemctl --user` (sonst Job rot mit Meldung). `scripts/ci_real_systemd_schedule_check.py` installiert und entfernt per `ScheduleService` mit dem Runner-HOME in `on_login` und `once_daily`, nur `karrierekrake-autorun.*`; ExecStart ist `/bin/true` (CI-Unterklasse überschreibt `_python_command`, der App-Lauf startet nie). Gibt `list-unit-files`/`list-units --all` für `karrierekrake*` vor/nach aus, prüft `remove()` `ok=True` und dass keine Unit-Datei, kein `default.target.wants`/`timers.target.wants`-Symlink und keine geladene Unit bleibt. Offline-Tests `tests/test_ci_real_systemd_schedule_check.py` (systemctl-Modell in `tmp_path`, u. a. Gegenprobe mit altem `disable --now` → rot) | CI ubuntu-latest (geplant); lokal nur Offline-Tests mit Modell | offline 7 passed; **CI-Run: ausstehend** | **UNSICHER** bis der CI-Lauf es zeigt; ob das für T04.08 reicht, entscheidet der Kritiker (prüft u. a. `WorkingDirectory="..."` nicht per `systemd-analyze verify`). T04.08 bleibt OFFEN |
