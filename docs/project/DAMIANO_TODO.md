# Was Damiano selbst erledigen muss (Stand 13.11.2026)

Diese Liste sammelt alles, was nur der Anbieter liefern oder entscheiden kann. Sie ist zum Abhaken gedacht, sobald
das Programm fertig ist. Die Reihenfolge ist die empfohlene: jeder Block braucht die Blöcke davor.

Quellen: `docs/project/PR144_P_NICHT_MACHBAR.md` (P01–P32), `docs/project/PR144_ENTSCHEIDUNGSVORLAGEN_2026-10-20.md`,
`docs/legal/RECHTSTEXTE_ENTWURF_2026-11-13.md` und `docs/legal/EINSTUFUNG_CRA_BFSG_2026-11-13.md` (beide aus PR #214).

## 1. Anbieter und Kontakt (Grundlage für alles Weitere)

- [ ] Rechtsform klären: Einzelunternehmen oder Gesellschaft; Gewerbe anmelden, falls noch nicht geschehen (P24)
- [ ] Steuerberatung: Kleinunternehmerregelung, Umsatzsteuer bei Verkauf über Paddle, Geschäftskonto (P22, P24)
- [ ] Anbietername und ladungsfähige Anschrift festlegen (P13)
- [ ] E-Mail und Telefon für das Impressum
- [ ] Supportadresse, Antwortzeit (Vorschlag: 5 Werktage) und Vertretung (P25)
- [ ] Meldeadresse für Sicherheitslücken einrichten, z. B. `security@<domain>`, und in `SECURITY.md` eintragen (P06)

## 2. Name, Marke, Domain

- [ ] Name „Karrierekrake“ gegen die älteren „KRAKE“-Marken von einer Fachperson prüfen lassen (P26)
- [ ] Domain sichern, zuerst `karrierekrake.de`
- [ ] Markenanmeldung entscheiden: Schutzgebiet (DE oder EU) und Klassen (Vorschlag 9, 42, ggf. 35) (P27)
- [ ] Rechte am Logo und an den Bildern bestätigen (P11)

## 3. Angebot und Preis

- [ ] Preise je Stufe und Grenzen der kostenlosen Basis festlegen (P18)
- [ ] Vertragsmodell wählen: Jahreslizenz ohne Verlängerung (empfohlen) oder Abo (P14)
- [ ] Zahl der Geräte je Lizenz festlegen
- [ ] Weg der Lizenzauslieferung festlegen (P23)
- [ ] Partner oder Banner: ja oder nein (P18)

## 4. Zahlung

- [ ] Paddle-Konto anlegen, Identitätsprüfung abschließen, Produkte und Schlüssel einrichten (P21)
- [ ] Gebühren, Vertrag und Rechnungsprozess freigeben (P22)
- [ ] Testkauf in der Paddle-Sandbox mit Widerruf und Erstattung durchführen und protokollieren (P15, P20)
- [ ] Dabei prüfen: zeigt Paddle die deutsche Widerrufsbelehrung, die Zustimmung zum sofortigen Beginn und die
      Widerrufsschaltfläche?

## 5. Rechtstexte

- [ ] Platzhalter in `docs/legal/RECHTSTEXTE_ENTWURF_2026-11-13.md` Abschnitt 0 füllen
- [ ] Impressum, Nutzungsbedingungen, Widerruf und Datenschutzhinweis anwaltlich prüfen lassen (P14)
- [ ] Datenschutz: Verantwortlichen, Empfänger, Rechtsgrundlagen und Löschfristen festlegen (P08, P09)
- [ ] Entscheiden: automatische Update-Prüfung und Kartendaten-Download ohne Nachfrage oder mit Opt-in (P32)
- [ ] Freigegebene Texte auf die Website stellen; erst danach den Verkauf einschalten

## 6. Sicherheit und Einstufung

- [ ] Hersteller für den Cyber Resilience Act benennen (derselbe wie im Impressum) (P06)
- [ ] Unterstützungszeitraum für Sicherheitsupdates festlegen (mindestens fünf Jahre, außer kürzere Nutzung ist begründet)
- [ ] Person benennen, die eine ausgenutzte Lücke binnen 24 Stunden meldet, plus Vertretung
- [ ] Einstufung „Standardprodukt“ aus `EINSTUFUNG_CRA_BFSG_2026-11-13.md` bestätigen lassen (P07)
- [ ] Schriftlich festhalten, dass die Alpha nicht verkauft wird, solange das so ist

## 7. Barrierefreiheit

- [ ] Zahl der Beschäftigten und Jahresumsatz festhalten (Ausnahme für Kleinstunternehmen) (P17)
- [ ] Einmal mit NVDA (Windows) durch Einrichtung, Import, Suche und Bestellseite gehen, Protokoll ablegen (P16)
- [ ] Dasselbe mit VoiceOver (macOS), falls macOS verkauft wird

## 8. Signatur der Programme

- [ ] Windows: Code-Signing-Zertifikat kaufen oder Azure Trusted Signing einrichten (P02, P05)
- [ ] macOS: Apple-Developer-Konto, Developer ID und Notarisierung (P05)
- [ ] Schlüssel sicher verwahren; danach kann die Signatur in die CI eingebaut werden (P10)

## 9. Tests auf echten Geräten

- [ ] Geschwindigkeit auf ThinkPad und Fujitsu messen: Gerätename, CPU, RAM, Dauer des Imports (P01)
- [ ] Alte Version → neue Version auf einem echten Windows-Rechner aktualisieren (P03)
- [ ] Installation, Deinstallation, Standardbrowser und Schlüsselbund je zugesagtem Gerät prüfen (P04)
- [ ] Urteil als Personaler zu Anschreiben und Matching nach `docs/personaler/ABNAHME_CHECKLISTE.md`

## 10. Konten bei Dritten

- [ ] Google-OAuth-Verifizierung für Gmail und Kalender beantragen; früh starten, das dauert (P19)
- [ ] Microsoft-Publisher-Verifizierung, falls Outlook angeboten wird (P19)

## 11. Veröffentlichung und Geschäft

- [ ] Veröffentlichungsfreigabe erteilen (bisher gilt „Veröffentlichen verboten“) (P28)
- [ ] Reale Kosten und Finanzierungsgrenzen aufschreiben (P29)
- [ ] Gespräche mit Partnern und Investoren führen (P30)

## Nicht von dir lösbar

- P31: Lücke in der Linux-Systembibliothek libstdc++ (CVE-2026-95619). Es gibt noch keine korrigierte Version; das
  hängt am Hersteller der Bibliothek.
