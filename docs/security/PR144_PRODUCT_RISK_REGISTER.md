# Produktrisiken und Reaktion (T06/T08)

Arbeitsregister der Implementierung; keine bestandene Sicherheitsprüfung. Verantwortliche Person und zugesagter Supportzeitraum sind vor Veröffentlichung zu benennen.

| Risiko | Technische Begrenzung | Nachweis für Abnahme | Reaktion bei Befund |
|---|---|---|---|
| Datenverlust beim Update | Programm getrennt von Daten; native atomare Umschaltung/Startquittung; Backup/Restore | Upgrade, Startfehler, Strom-/Speicherabbruch mit synthetischem Profil | Verteilung stoppen, letzten funktionsfähigen Build anbieten, Datenkopie vor Reparatur |
| Unvollständiges Backup | SQLite Backup-API statt Rohkopie/WAL-Verlust; Hashmanifest; private Restore-Stufe | Laufende DB, beschädigte ZIP, Abbruch, leeres Ziel | Keine Erfolgsmeldung; Ursprungsdaten erhalten |
| Falsche/doppelte Bewerbung | Dry-Run, reale Aktion bestätigen, Lifecycle- und Versandzuordnung | Synthetischer Portal-/Mailablauf, doppelte Bestätigung, Neustart | Automatisierung pausieren; keine weiteren Versuche ohne Prüfung |
| KI erfindet Qualifikationen | Import-/Entwurfsprüfung; lokale Modellprobe; keine Erfolgs-/Richtigkeitsgarantie | DE/EN-Korpus und manuelle Feldkontrolle | Modell/Prompt zurücknehmen; Entwurf nicht versenden |
| Kompromittiertes Update | HTTPS-Vertrauenspfad, Repository-/Tag-/Architekturbindung, Hash/Größe, Archivgrenzen | Manipuliertes Manifest/Paket, Traversal, falsche Architektur | Release sperren, Zugangsdaten rotieren, Benutzer über freigegebenen Kanal informieren |
| Gestohlene Zugangsdaten | OS-Keyring, kein Klartextfallback; Löschung muss verifiziert sein | Gesperrter Keyring, alle verwalteten Provider, Neustart | Providerzugriff widerrufen, bereinigten Incident erfassen |
| Unbeabsichtigte Datenübertragung | Explizite Integrations-/Browseraktionen; lokaler Sponsor ohne SDK | Offline-Modus, Netzwerkbeobachtung, Einwilligung widerrufen | Betroffenen Pfad deaktivieren; tatsächliche Daten/Empfänger ermitteln |
| Falsche Premiumberechtigung | Ed25519, Umgebung/Zeitraum/Revision, frischer Zahlungsabgleich | Tamper/Replay/Refund/Timeout/Verlängerung | Verkauf/Signierung pausieren, Schlüsselwechsel, ablaufende Lizenzen berücksichtigen |
| Doppelte Zahlung/Erstattung | Operatorjournal schreibt Versuch vor Request; keine blinden Retries | Timeout nach möglicher Annahme, Wiederholung gleicher ID | Im Anbieterportal abgleichen, erst danach weitere Aktion |
| Lizenzverstoß | Build-SBOM, Notices, Hashinventar, offene Rechtezuordnung | Tatsächlich ausgelieferte Abhängigkeiten/Modelle/Assets prüfen | Ungeklärte Komponente nicht freigeben; Quelle/Erlaubnis beschaffen |
| Unzugängliche Bedienung | Tastatur, Fokus, Textfehler, DPI/Scroll, beschriftete Aktionen | NVDA/VoiceOver, 200 %, Tastatur inkl. Checkout | Betroffene Kernaktion bis Korrektur nicht als barrierefrei bewerben |

## Vertrauensgrenzen

SHA-256 beweist die Übereinstimmung mit dem Manifest, nicht die Unabhängigkeit vom kompromittierten Releasekonto. Der bestehende Updatevertrauensanker ist der kontrollierte HTTPS/GitHub-Releasepfad; eine zusätzliche unabhängige Signaturinfrastruktur ist nicht eingerichtet. Keine Aussage „kryptografisch unabhängig signierte Releases“ verwenden. Code-Signing/Notarisierung und die dafür benötigten Konten/Schlüssel sind externe Voraussetzungen.

## Incidentablauf

Eingang mit Zeit, Build, Plattform, Kategorie und minimalen reproduzierbaren Schritten erfassen. Keine Roh-CVs/Tokens in öffentliche Issues. Schwere nach Datenabfluss, Ausführbarkeit, Datenverlust und Reichweite festlegen; betroffene Versionen eingrenzen. Release/Feature bei reproduzierbarem hohem Risiko stoppen. Korrektur auf isoliertem Branch, gezielte Regression und SBOM/Scan neu erstellen, anschließend kontrollierte Verteilung. Kommunikation, gegebenenfalls Meldungen und Fristen mit dem benannten Verantwortlichen anhand des tatsächlichen Falls klären. Nachbereitung dokumentiert Ursache, betroffene Daten, Behebung und Vorbeugung. Keine fiktiven Meldungen oder gesetzlichen Fristen aus dem Repository ableiten.
