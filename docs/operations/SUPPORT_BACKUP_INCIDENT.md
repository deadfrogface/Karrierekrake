# Karrierekrake — Betriebshandbuch (T06/T13)

**Status:** Entwurf für lokale Desktop-Distribution; kein aktiver Supportdienst oder zugesagtes SLA.

## Support ohne private Daten
Nutzer nennt App-Version, Betriebssystem, betroffene Funktion, anonymisierte Fehlermeldung und Reproduktionsschritte. Keine Lebensläufe, Mailinhalte, Tokens, Cookies, Browserprofile, privaten Dateipfade oder vollständigen Logs anfordern. Log-Export nur nach Vorschau und Redaktionsprüfung.

## Backup / Wiederherstellung
1. App schließen und laufende Downloads/Schreibvorgänge beenden.
2. Vom Nutzer ausdrücklich gewählte Profildaten in ein vom Nutzer kontrolliertes Ziel sichern; keine automatischen Cloud-Uploads.
3. Sicherung vor Updates getrennt von Installationsdateien aufbewahren; verschlüsselte Datenträger empfehlen.
4. Wiederherstellung ausschließlich in einer Testkopie prüfen, bevor Originaldaten überschrieben werden.
5. Fehlende oder beschädigte Backups als **nicht wiederherstellbar** behandeln; keine Erfolgsmeldung ohne Lese-/Integritätstest.

**Implementiert, noch nicht in dieser Fortsetzung getestet:** Einstellungen → Datenschutz bietet Backup erstellen, prüfen und in einen leeren Ordner wiederherstellen. Diese Aktionen laufen im Hintergrund. SQLite wird über die Backup-API inklusive bestätigter WAL-Daten gesichert; andere Dateien sollten während der Sicherung nicht geändert werden. Restore prüft Größen und SHA256 beim Extrahieren in einen Zwischenordner und übergibt erst danach den vollständigen Zielordner. Aktive App-Daten werden nicht automatisch überschrieben. CLI: `python -m scripts.local_backup_cli create|verify|restore`.

Ein vollständiges lokales Backup enthält personenbezogene Daten und gegebenenfalls vom Nutzer gewählte Konfigurationsdateien. Es ist kein redigierter Supportexport und nicht automatisch verschlüsselt. Keyring-Zugangsdaten werden nicht aus dem Betriebssystem exportiert; Konten nach Wiederherstellung bei Bedarf neu verbinden. Getrennte Backups bleiben bei „alle App-Daten löschen“ nutzerverwaltet.

## Sicherheitsvorfall
- Eingang mit Datum, Version, betroffener Komponente und reproduzierbarem Sachverhalt dokumentieren.
- Betroffene Releases/Abhängigkeiten und Datenflüsse abgrenzen.
- Geheimnisse nie in öffentlichen Issues teilen; falls kompromittiert, über jeweiligen Anbieter widerrufen.
- Fix auf separatem Branch, Tests und reproduzierbare Build-Artefakte erstellen.
- Rechtliche Meldepflichten, Betroffenenkommunikation und Fristen durch verantwortliche Stelle prüfen.
- Veröffentlichung nur nach technischer Verifikation und Freigabe.

## Release-Rücknahme
Fehlerhaften Release als nicht empfohlen kennzeichnen, funktionierende Version bereitstellen und Datenmigration/Abwärtskompatibilität separat prüfen. Kein automatisches Downgrade, wenn Datenbankformat inkompatibel ist.

## Menschliche Entscheidungen
Anbieter-/Unternehmensdaten, Supportadresse, Erreichbarkeit, Backup-Produktversprechen, Incident-Verantwortliche und rechtliche Freigaben.
