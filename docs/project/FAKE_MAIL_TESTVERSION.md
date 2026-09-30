# Fake-Mail-Testversion (separater Branch)

Branch: `codex/fake-mail-demo-20260930`. Diese Version ist ausdrücklich zum Testen gedacht. `main` und das normale Benutzerprofil bleiben unangetastet.

## Start auf Windows

1. Nach grünem Windows-Smoke das vollständige Artefakt `Karrierekrake-Windows-Smoke` dieses Branches entpacken.
2. `Start-Fake-Mail-Testversion.cmd` doppelklicken. Alternativ `Karrierekrake.exe --fake-mail-demo` starten.
3. Die Titelzeile zeigt `TESTVERSION: fiktives Postfach`; im Postfach erscheint `FAKE-POSTFACH · TEST`.

Die Testdaten liegen ausschließlich unter `%LOCALAPPDATA%\Karrierekrake-FakeMailDemo\Karrierekrake`. Die normale App nutzt weiterhin `%LOCALAPPDATA%\Karrierekrake`. Test- und Produktinstanz haben getrennte Single-Instance-IDs. Zum Zurücksetzen nur den Demoordner löschen, während die Testversion geschlossen ist.

## Testablauf

Beim Start werden drei fiktive Bewerbungen angelegt und fünf Mails über `FakeInProcessMailAdapter.sync()` und `process_parsed_email()` verarbeitet. Wiederholtes Starten erzeugt keine doppelten Mails oder Ereignisse. Im Postfach prüfen:

- Eingangsbestätigung, Einladung, Absage, Newsletter und mehrdeutige Rückfrage: Kategorie und Bewerbungszuordnung.
- Mehrdeutige Rückfrage manuell prüfen; keine automatische Zuordnung erzwingen.
- Einladung öffnen → `Kalender-Vorschlag`: 06.10.2026 10:00 Uhr ist im Fake-Kalender belegt; 07.10.2026 14:00 Uhr bleibt übrig.
- `Antwort entwerfen`: nur der freie, belegte Termin darf in den Vorschlag. Entwurf und Freigabeoberfläche testen. Der Demo-Modus setzt den Versand-Guard fest auf `false`.
- Über `Test-Mail hinzufügen` eigene fiktive Absender, Betreffe und Texte eingeben und Klassifizierung/Zuordnung direkt im Postfach prüfen. Diese Mails gehen ebenfalls durch Fake-Provider, Sync und Lifecycle-Pipeline; sie werden nicht direkt in die UI oder Datenbank geschoben.

`--fake-mail-demo-check <pfad.json>` prüft denselben Durchlauf ohne UI aus der gepackten EXE. Der Windows-Smoke führt diesen Check in einem frischen, isolierten Profil aus. Das ersetzt keinen Test der angezeigten Windows-Oberfläche.

## Grenzen

Die fünf Startmails und alle selbst hinzugefügten Mails sind synthetisch. Der Fake-Kalender liefert nur Verfügbarkeit; es wird **kein** Termin in einen echten Kalender geschrieben und **keine** echte Mail verschickt. Im Demo-Modus verweigern Mail-/Kalender-Registries echte Provider. Der Test beweist weder echte Gmail-/Outlook-Anmeldung noch deren Synchronisierung. Der konkrete Termin liegt im Testkorpus; für spätere Tests nach diesem Datum muss die Einladung aktualisiert werden. Der normale App-Start ohne Test-Flag aktiviert die Fake-Provider nicht.
