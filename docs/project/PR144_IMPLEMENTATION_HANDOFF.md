# PR #144 – Implementierungsübergabe T01–T16

Stand: 14.10.2026. Referenz vor dieser Fortsetzung: `0343232`.

Auftrag: alle ohne Nutzer-/Anbieterzugang ausführbaren Implementierungen vorbereiten. **Keine Tests ausgeführt, kein CI-Ergebnis abgewartet, kein Merge und keine Veröffentlichung.** Vorhandene grüne Ergebnisse gelten nicht für diese Fortsetzung. Syntaxprüfung ist keine Funktionsprüfung.

## Paketübersicht

| Paket | Implementierung / nachvollziehbare Übergabe | Verbleibende Abnahme oder externe Voraussetzung |
|---|---|---|
| T01 Kernfunktionen/CI | Bestehende Parser-, Such-, Filter- und Dry-Run-Pfade; sechs CI-Shards samt Vollständigkeitsprüfung; zusätzliche Löschkorrekturen und Backup-I/O außerhalb des UI-Threads | Tests und Laufzeitvergleich; `T01_CI_BASELINE_AND_ACCEPTANCE.md` enthält die historische Baseline |
| T02 Modell | Bestehende Hardwareauswahl, Resume, Hashprüfung, Abbruch, isolierte Modellprobe und atomare Aktivierung; nativer Updatebereich verwendet jetzt denselben Installer wie Setup | Echter Transfer, Abbruch/Resume, RAM-Grenzen und Nutzung nach Neustart |
| T03 Updates | Windows-Komponentenupdater bereits vorhanden; neue native SHA256-/Größen-/Identitätsprüfung, sichere Extraktion, atomarer Ordneraustausch, Startquittung und Rücktausch bei Startfehler | Upgrade/Rollback auf jeder Plattform; Dateisystem muss atomaren Austausch unterstützen; beschreibbarer Installationsordner erforderlich |
| T04 Plattformen | Bestehende Windows-/Linux-/macOS-Matrix; Compliance-Dateien an native Pakete und Windows-Release angehängt | CI, reale Installationen; Signierung/Notarisierung erfordert Entwicklerkonto und Schlüssel |
| T05 Einrichtung/UI | Bestehender Setuphelfer, Browserwahl und Dialog-Begrenzung; Backup/Prüfung/Restore ohne blockierenden UI-Aufruf | Wizard, Browser, Fokus und DPI auf echten Geräten |
| T06 Sicherheit | Bestehende Dependency-/SAST-/Secret-Scans und Incident-Triage; native Archive begrenzt und gefiltert; Löschung bestätigt keine unlesbaren Daten als leer | Aktueller Scanlauf; reale Befunde danach beheben; CRA-Bewertung und Verantwortliche extern |
| T07 Datenschutz | Keyring-Löschung umfasst Google, Microsoft Mail/Kalender, IMAP und CalDAV; unzugänglicher Keyring ist kein Löschbeleg; DB-Seitendateien und weitere Profilfelder geprüft; Dataclass-Profil wird exportiert | Lösch-/Export-/Neustarttests; Rechtsgrundlagen und Verantwortlicher extern |
| T08 Lizenzen/SBOM | PyInstaller-Hook erfasst aufgelöste Python-Komponenten, native Eingabedateien mit Hashes, GeoNames-Daten und optionalen Modellkatalog; Lizenztexte und offene Zuordnungen werden veröffentlichten Paketen beigelegt | Build muss Inventar erzeugen; ungeklärte native/OS-Lizenzen bleiben explizit im Reviewbericht, kein Konformitätsversprechen |
| T09 Verbraucherinformationen | Nicht veröffentlichte Themen-/Textentwürfe in `docs/legal/UNPUBLISHED_CONSUMER_DRAFTS.md` | Echter Anbieter, Anschrift, Vertrieb und rechtliche Formulierungen/Freigabe; keine fertigen AGB behauptet |
| T10 Barrierefreiheit | Bestehende Tastatur-/Fokus-/Kontrast-/DPI-Bausteine; Website mit Sprunglink, semantischen Tabellen, Fokusmarkierung und umbruchfähigem Layout | NVDA/VoiceOver, Kontrast-/DPI-Abnahme und BFSG-Einstufung |
| T11 Free/Premium/Werbung | Bestehende Offline-Free-Richtlinie; Premium nicht käuflich freigeschaltet; keine Werbe-SDKs oder Trackingaktivierung | Endgültige Leistungsgrenzen, Preise, Werbepartner und Einwilligungskonzept vor produktiver Anbindung |
| T12 Zahlungen | Lokaler Sandbox-Reducer jetzt optional mit SQLite-Journal, Replay-Schutz über Neustarts, Konflikterkennung, Refund/Cancel und Offline-Abfrage | Keine Paddle-API-Anbindung behauptet; Sandbox-Konto/Produkte/Anbieterzugang für echte Integration fehlen; Live-Vertrag/Freigabe extern |
| T13 Betrieb | UI für Erstellen/Prüfen/Restore; konsistente SQLite-Snapshots inklusive WAL; Restore prüft und extrahiert in privatem Zwischenordner vor Übergabe | Wiederherstellung auf Realgeräten; Supportadresse und Zuständigkeiten fehlen |
| T14 Website/Marke | Trackingfreie Website-Vorschau mit Funktionen, Einrichtung, OS-Paketen, Datenhinweisen und Fehlermeldungsanleitung | Domain, Markenprüfung, Anbieterkennzeichnung, Freigabe und Veröffentlichung |
| T15 Beta | Bestehende Testskripte, Ergebnisvalidator und Feedbackvorlage; zusätzliche Prüffälle unten | Nutzer führt Tests aus; keine erfundenen Testergebnisse |
| T16 Wachstum | Bestehende Szenarien ergänzt um explizite Kosten-/Gebühren-/Erstattungs-/Fixkostenrechnung ohne vorausgesetzte Maps-Kosten | Tatsächliche Kosten, Preise, Nachfrage und Kontakte; Annahmen sind keine Umsätze |

## Gezielte Prüffälle für diese Fortsetzung

1. Laufendes SQLite im WAL-Modus sichern; nur bestätigte Einträge müssen nach Restore erhalten sein. Beschädigtes Archiv darf keinen teilweise wiederhergestellten Zielordner hinterlassen.
2. Backup/Prüfung/Restore bedienen, während das Fenster bewegt wird. Bestehende Zielordner mit Inhalt werden abgewiesen.
3. Alle sechs Credential-Schlüssel mit synthetischen Werten belegen; „alle Daten löschen“ muss alle entfernen. Gesperrten Keyring und beschädigte DB als Fehler melden.
4. Native Altversion mit synthetischem Profil aktualisieren; korrektes OS-Paket, Hashprüfung, Profil unverändert, Startquittung. Fehlerhafte Prüfsumme darf keine Installation verändern.
5. Native neue Version absichtlich vor Startquittung beenden; vorheriges Paket muss zurückgetauscht werden. Vorherige Version liegt nach erfolgreichem Upgrade im jeweiligen `.kk-native-update-*/payload/`-Ordner neben der Installation. Nicht blind entfernen, solange Rückfall benötigt wird.
6. Auf einem Dateisystem ohne `RENAME_EXCHANGE`/`RENAME_SWAP` muss der Austausch scheitern, ohne die alte Installation zu entfernen. Bei Stromausfall verbleibt dank atomarem Austausch ein vollständiger Programmordner. Profile werden nicht rückwärts migriert.
7. Modellinstallation aus nativem Updatebereich: Transfer bleibt vor Aktivierung unter 100 %, Modellprobe erfolgreich, Neustart nutzt ausgewähltes Modell.
8. Sandbox-Journal öffnen, Grant zweimal zustellen, neu starten, Refund/Cancel zustellen. Produktionsevents und widersprüchliche Event-IDs müssen scheitern.
9. Build-Artefakte müssen SBOM, Lizenztexte und Reviewbericht enthalten; Veröffentlichung ohne die drei Dateien wird abgewiesen.

## Grenzen der Fertigstellung

Implementierung und Entwurf sind keine Produktabnahme. T09/T11/T12/T14/T16 enthalten absichtlich keine erfundenen Anbieterangaben, keine Live-Zahlungen, keine Werbung und keine Veröffentlichung. Offene externe Punkte stehen oben; der Sandbox-Reducer ist insbesondere **kein angebundener Paddle-Zahlungsdienst**. Änderungen nach Nutzer-/CI-Tests bleiben möglich.
