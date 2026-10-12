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

**Noch zu implementieren/verifizieren:** UI-gestützter Backup-Export, Import, Integritätsprüfung und plattformübergreifender Restore-Test. Dieses Dokument behauptet keine vorhandene Backup-Funktion.

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
