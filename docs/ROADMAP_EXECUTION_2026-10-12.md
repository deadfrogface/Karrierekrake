# Karrierekrake — Umsetzungsregister (12.10.2026)

Quelle: Karrierekrake_Aufgabenplan.docx (16 Arbeitspakete). Dieses Register ist keine Behauptung, dass die Funktionen bereits funktionieren.

## Regeln
- Vor jedem Fix aktuellen main-Stand und bestehenden Code prüfen. Keine bereits gemergten Branches wiederverwenden.
- Keine Tests entfernen, überspringen oder abschwächen, um CI grün zu bekommen.
- Keine echten Bewerbungen, E-Mails, Kalenderänderungen, Zahlungen oder Veröffentlichungen in automatisierten Tests.
- Externe CAPTCHA-Schutzmechanismen respektieren; keine Umgehung oder Garantie auf CAPTCHA-Freiheit.
- Keine Zugangsdaten, Lebensläufe oder Tokens in Diagnoseprotokollen.
- Pro Arbeitspaket: Ausgangs-SHA, Testbeleg, Plattform, Ergebnis, offene Risiken dokumentieren.
- Endnutzer-Installation ist erst nach echter Installation, Neustart und Wiederholung der Funktion nachgewiesen.

## Technische Arbeitspakete (Reihenfolge)
| ID | Paket | Automatisch bearbeitbar | Abschlussnachweis |
|---|---|---|---|
| T01 | Kernfunktionen und CI | Parser, Suche, Filter, Löschung, Dry-Run, UI-Freeze und CI-Laufzeit prüfen/fixen | Gleiche Testabdeckung, reproduzierbare Fehlerfälle, gemessene Laufzeiten |
| T02 | Modellinstallation | Hardwareauswahl, Quelle/Lizenz, Hash, Resume, Abbruch, Aktivierung, Neustart | Nutzbares Modell nach Neustart; Fehlerdiagnose ohne Datenlecks |
| T03 | Updater | Versionsvergleich, korrekte Assets, Hash, Rollback, Migration | Upgrade einer installierten Altversion mit erhaltenem Profil |
| T04 | Desktopplattformen | Windows/Linux/macOS Builds und automatisierte Smoke-Tests | Plattformmatrix; echte Hardwaretests separat |
| T05 | Einrichtung/UI | Setuphelfer, Browserwahl, Fokus, Skalierung, Performance | Neuer Nutzer kann Setup/CV/Suche abschließen |
| T06 | Sicherheit/CRA | Dependency-Scan, Security-Policy, Schwachstellenablauf | Risiko- und Nachweisregister; Rechtsprüfung offen |
| T07 | Datenschutz | Datenflusskarte, Lösch-/Exporttests, Log-Redaktion | Tests + dokumentierte Datenflüsse |
| T08 | Lizenzen/SBOM | Komponenten/Modelle/Datensätze erfassen, SBOM pro Release | Maschinenlesbare SBOM, Lizenzprüfung dokumentiert |
| T09 | Verbraucherinformationen | AGB/Impressum/Widerruf als nicht veröffentlichte Entwürfe | Anbieterfreigabe erforderlich |
| T10 | Barrierefreiheit | Keyboard/Fokus/Kontrast/Skalierung prüfen | Prüfprotokoll, BFSG-Einstufung offen |
| T11 | Free/Premium/Werbung | Kostenfreie Offline-Basis sichern, Architektur/Mockups | Geschäftsentscheidung offen |
| T12 | Zahlungen | Anbieterneutralen Sandbox-Entwurf und Testfälle erstellen | Konto/Vertrag/Preise offen |
| T13 | Betrieb | Support- und Backup-Prozesse entwerfen | Unternehmensdaten offen |
| T14 | Website/Marke | Website-Entwurf, Systemanforderungen, Rechercheprotokoll | Domain/Markenentscheidung offen |
| T15 | Beta-Tests | Anonymisierte Testskripte und Feedbackvorlage | Menschliche Tests offen |
| T16 | Wachstum | Demo-/Kostenmodell mit klaren Annahmen | Zahlen und Investorengespräche offen |

## Sofortige Bestandsaufnahme
- Main: Stand und CI-Runs erfassen; CI-Fehler nicht als Produktfehler oder umgekehrt verwechseln.
- Modell: 100 % Fortschritt darf nicht als Installationserfolg gelten; erst Hash, Dateipfad, Laufzeit und Neustart.
- Browser: Bereits installierte Browser bevorzugen, aber Browserautomation und Schutzseiten nicht als garantiert kompatibel behandeln.
- Plattformen: Ein grüner CI-Job ersetzt keinen Test auf realer Hardware.

## Menschliche Freigaben
Releaseumfang und Plattformversprechen, Qualitätsgrenzen, Preis-/Werbemodell, Anbieter-/Kontenwahl, gesetzliche Erklärungen, reale Tester und Veröffentlichung.

## Status
Dieses Register: vorbereitet. Technische Pakete: nicht durch dieses Dokument abgeschlossen. Fortschritt nur mit Commit-/CI-/Endnutzernachweisen markieren.
