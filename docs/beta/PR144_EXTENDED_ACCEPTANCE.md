# Ergänzende Abnahme PR144

Alle Ergebnisse stehen auf **nicht getestet**. Bestehende B01–B10 bleiben unverändert. Für diese Fortsetzung zusätzlich:

| ID | Durchführung | Erfolgskriterium |
|---|---|---|
| X01 | Backup bei laufender WAL-Datenbank; verifizieren; in leeren Ordner wiederherstellen | Alle bestätigten Datensätze vorhanden; App bleibt bedienbar |
| X02 | Backup/Restore während großer Datei abbrechen; beschädigte ZIP versuchen | Kein teilweise veröffentlichtes Archiv/Ziel; Originaldaten unverändert |
| X03 | >5.000 Fälle mit Ereignissen/Aufgaben exportieren; ZIP-Inhalt zählen | Kein stilles Limit; Secrets ausgeschlossen; Abbruch/Schreibfehler hinterlässt kein ZIP |
| X04 | Mail/IMAP/Microsoft/CalDAV nur mit eigenen Testkonten verbinden/trennen | Passende Statusanzeige; keine ungefragten Send-/Schreibaktionen; Keyring nach Trennung geprüft |
| X05 | ICS importieren; Termine als Entwurf; Freigabe ablehnen | Kein externes Schreiben ohne Zustimmung; Cachelöschung greift |
| X06 | Native Update-Hashes manipulieren, falsche Architektur, Neustart ohne Quittung | Alte Installation intakt oder Rücktausch; Daten bleiben erhalten |
| X07 | Hardwareempfehlung 4B/8B/27B und unzureichendes RAM; Download abbrechen/fortsetzen | Setup und nativer Weg wählen dieselbe ID; keine 100-%-Meldung vor Aktivierung |
| X08 | Lizenz manipulieren/ablaufen lassen; alte Revision nach Widerruf importieren | Keine Freischaltung; kostenlose Basis bleibt nutzbar |
| X09 | Paddle Sandbox: Erfolg, Abbruch, Doppel-ID, Timeout, Refund, Aboende | Aktueller Anbieterstatus entscheidet; keine doppelte Mutation |
| X10 | Sponsor zustimmen, widerrufen, Kampagnenversion ändern | Sichtbar als Anzeige; ohne Zustimmung unsichtbar; kein Netzwerk vor Linkbestätigung |
| X11 | Einstellungen/Update/Lizenz mit Tastatur, 200 % und Screenreader bedienen | Aktionen benannt, Fokus sichtbar, Dialoge erreichbar; Abbruch verständlich |
| X12 | Daten löschen, App neu starten, Lizenz-/Consentdateien und alle Credentials prüfen | Keine Restdaten als gelöscht bestätigt; unlesbare Bereiche melden Fehler |

Pro Lauf `App-Commit`, Paket-SHA256, OS-Version/Architektur, RAM, freier Speicher, CPU, Testdatum und pseudonyme Gerätekennung erfassen. Keine Seriennummern, Mailadressen oder echten Lebensläufe. Ein Befund enthält Test-ID, Soll/Ist, Schritte, Schwere (Blocker/Hoch/Mittel/Niedrig), bereinigte Evidenz und Retest-Commit.

Zielmatrix: Windows x86-64; macOS Apple Silicon; macOS Intel; Linux x86-64 mit grafischer Sitzung und Keyring. Paketbau allein ersetzt keine interaktive Geräteabnahme. Unverfügbare Geräte/Konten als blockiert erfassen. Keine Plattformfreigabe aus leeren Zeilen ableiten.

## Reproduzierbare Zeitmessung

Je Gerät kalten Start, warmen Start, CV-Import, Suche mit fester synthetischer Eingabe, Fensterreaktion während Download und Backup erfassen. Drei Wiederholungen; Median sowie langsamster Wert, RAM-Spitze und Zeitpunkt der Abbruchreaktion dokumentieren. Vorher/nachher nur mit gleicher Eingabe, gleichem Gerät und gleicher Betriebsart vergleichen. Langsame externe Anbieter getrennt vom lokalen Rechenanteil kennzeichnen. Keine Millisekunden- oder RAM-Zusagen ohne diese Messung.

Vorlage: `python scripts/beta_acceptance_report.py --template > session.json`. Metadaten ausfüllen, B01–B10 und X01–X12 bewerten, dann `python scripts/beta_acceptance_report.py session.json`. Fehlende Metadaten, doppelte IDs oder unbekannte Zustände werden abgewiesen; ungetestete/fehlende/gesperrte Fälle verhindern die Session-Freigabe. Jede Plattform benötigt eine eigene Session. Das alte `summarize(rows)` für B01–B10 bleibt kompatibel.
