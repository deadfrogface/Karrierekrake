# Testversion: Bewerbung → synthetische Antwort → normale Zuordnung

Nur PR #110 / `KARRIEREKRAKE_FAKE_MAIL_DEMO=1`. Kein Merge nach main.

1. Über `Start-Fake-Mail-Testversion.cmd` starten; eine gefundene Stelle auswählen.
2. Bewerbung vorbereiten, Anschreiben prüfen und den Entwurf bestätigen.
3. **Bewerbung simulieren (kein Versand)** klicken.
4. Im Postfach die dynamische Eingangsbestätigung und Einladung prüfen.

Die lokale Simulation speichert einen Bewerbungsfall und eine als `simulated`
markierte Versandhistorie. Firma und Position stammen aus der ausgewählten
Stelle. Ein synthetischer Recruiter-Kontakt und eine Testreferenz gehören zum
lokalen Vorgang. Es werden keine Portale geöffnet oder Unterlagen hochgeladen.

Die Antworten laufen über Fake-Provider-Registry → Sync → `process_parsed_email`.
Ihr Eingabepayload enthält weder `case_id` noch bestätigte Zuordnungsflags oder
bekannte Thread-IDs. Erst die unveränderte normale Zuordnung schreibt die
Verbindung. Der vorhandene Bewerbungsfall wird nicht als Zuordnungsresultat
in die Mail übertragen. Die Testreferenz ist Anzeigeinformation; aktuell nutzt
die Zuordnung den gespeicherten Recruiter-Kontakt und den Stellentitel.

Mehrere Rollen derselben Firma und eine Rückfrage ohne Rollenangabe sind
Kontrasttests: eindeutige Antworten werden erkannt, mehrdeutige Antworten bleiben
zur Prüfung offen. Wiederholter Simulationsklick erzeugt keine Duplikate.
Terminvorschläge liegen relativ zum Simulationsdatum in der Zukunft.

Die normalen Betriebswege werden außerhalb des Fake-Modus nicht umgestellt.
Windows-EXE-Nachweis für diesen neuen Klickablauf steht bis zum CI-Lauf aus.
