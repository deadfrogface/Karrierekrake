# Karrierekrake — Beta-Abnahme (T15)

**Status:** Vorbereitete Testanleitung, keine behaupteten Nutzerergebnisse. Testpersonen freiwillig; keine echten Bewerbungen versenden.

## Testmatrix
| Test | Ablauf | Bestehen | Befund |
|---|---|---|---|
| B01 Neuinstallation | Installieren, ohne bestehendes Profil starten, Setup öffnen | Kein Absturz, Fenster erreichbar | OFFEN |
| B02 Offline-Start | Internet trennen, App starten | Lokale Kernfunktionen erreichbar, kein Cloud-Zwang | OFFEN |
| B03 CV | Synthetischen Lebenslauf als PDF importieren | Felder überprüfbar, keine erfundenen Angaben | OFFEN |
| B04 Suche | Dry-Run aktivieren, Suchkriterien setzen, Suche ausführen | Kriterien sichtbar, keine Bewerbung versendet | OFFEN |
| B05 Löschen | Testprofil exportieren, löschen, neu starten | Gelöschte Testdaten bleiben entfernt | OFFEN |
| B06 Modell | Passendes Modell wählen, Download unterbrechen und fortsetzen | Hash/Ladetest erfolgreich, nach Neustart nutzbar | OFFEN |
| B07 Updater | Vorversion installieren, Testprofil erstellen, Update ausführen | Profil erhalten, neue Version startet | OFFEN |
| B08 Browser | Standardbrowser und alternativ installierten Browser auswählen | Keine ungefragte Browserinstallation, Schutzseiten respektiert | OFFEN |
| B09 UI | 125 % und 200 % Skalierung, nur Tastatur | Alle primären Aktionen erreichbar | OFFEN |
| B10 Protokoll | Simulierten Downloadfehler auslösen | Verständliche Fehlerkategorie, keine persönlichen Daten | OFFEN |

## Rückmeldung pro Test
- Test-ID, Datum, App-Version/Commit, Betriebssystem und Architektur
- Gerät: RAM/CPU und freier Speicher (keine Seriennummer)
- Erwartetes Ergebnis, tatsächliches Ergebnis, reproduzierbare Schritte
- Schwere: Blocker / Hoch / Mittel / Niedrig
- Screenshot nur nach Kontrolle auf personenbezogene Daten
- Einwilligung für freiwillige Rückmeldung; keine CVs, Zugangsdaten oder Tokens anhängen

## Release-Gate
B01–B07 auf Windows physisch, B01/B02/B05/B09 auf Linux und macOS physisch. Nicht getestete Plattformen als unbestätigt kennzeichnen. Fehler zuerst reproduzieren, dann Fix und Regressionstest, anschließend denselben Test wiederholen.
