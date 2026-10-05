# Kostenlose Kommunikation und spätere Premium-Funktionen

Der kostenlose Ablauf nutzt den vorhandenen lokalen Recruiting-Klassifizierer
und die Zuordnung zu Bewerbungen. E-Mails und Kalender werden nicht an eine
Cloud-KI geschickt. IMAP liest mit `BODY.PEEK[]`; Nachrichten werden dabei weder
verschoben noch gelöscht oder als gelesen markiert. Kategorien im Posteingang
sind lokale Ansichten, keine Ordner beim Anbieter. Unsichere Zuordnungen bleiben
zur Prüfung; der Import ändert Bewerbungsstatus nicht automatisch.

## E-Mail

| Anbieter | Kostenloser Weg | Einrichtung |
| --- | --- | --- |
| Gmail | IMAP über TLS | Zweistufige Bestätigung und Google-App-Passwort; falls nicht verfügbar: Dateiimport |
| WEB.DE | IMAP über TLS | POP3/IMAP im Konto freigeben; ggf. App-Passwort |
| T-Online | IMAP über TLS | Separates Passwort für E-Mail-Programme |
| Outlook.com | IMAP mit OAuth/PKCE | Microsoft-Desktop-App registrieren, persönliche Microsoft-Konten zulassen, delegierte IMAP-Berechtigung und Redirect `http://localhost:8765/oauth/callback`; Client-ID im Dialog eingeben |
| Alle genannten | EML/MBOX-Dateiimport | Aus dem Mailprogramm exportieren; funktioniert offline |

`Verbindungen` und `EML / MBOX importieren` sind direkt im Posteingang erreichbar.
Ein Postfach ist gleichzeitig aktiv. Ein Abruf verarbeitet bis zu 50 Nachrichten;
bei weiteren Nachrichten erneut aktualisieren. Ein Cursor mit Konto-Namespace,
UIDVALIDITY und UID verhindert das Überspringen weiterer Batches. Erst nach
vollständiger lokaler Verarbeitung wird er gespeichert. Doppelte Imports werden
erkannt. Die Ansicht zeigt bis zu 200 passende Nachrichten je Kategorie/Suche.

Outlook-OAuth ist kein Premium-Merkmal und nutzt keine Graph-Mail-API.
Eine Microsoft-App-Registrierung ist trotzdem erforderlich; eine produktweit
bereitgestellte Client-ID fehlt derzeit. Passwörter und OAuth-Tokens werden im
OS-Schlüsselspeicher gespeichert, niemals im Repository oder Klartext-YAML.
Provider können IMAP-Zugriff einschränken und eigene Zugriffslimits haben.

## Kalender

| Kalender | Kostenlos verfügbar | Grenze |
| --- | --- | --- |
| Google Kalender | ICS-Datei importieren; Terminvorschlag als ICS exportieren | Lokale Kopie, keine Live-Synchronisierung |
| Samsung Kalender | Export des zugrunde liegenden Kontokalenders importieren; ICS-Datei für unterstützenden Kalenderclient | Nur auf dem Telefon gespeicherte Termine werden nicht automatisch gelesen; Import hängt vom Kalenderclient ab |
| Apple Kalender / iCloud | CalDAV mit Apple-ID und anwendungsspezifischem Passwort; alternativ ICS | Echte Kontokompatibilität muss mit einem Konto geprüft werden |

Serientermine, Ausnahmezeiten und ganztägige Ereignisse werden mit `icalendar`
und `recurring-ical-events` verarbeitet, CalDAV mit `python-caldav`. ICS-Import
speichert eine eigene Kopie unter `cache/calendar-snapshot.ics`; der Originalexport
bleibt unangetastet. Importdatum entspricht dem Stand dieser Kopie, nicht einer
Garantie für die Vollständigkeit des Exports. Nach Kalenderänderungen neu
importieren. Kopien über sieben Tage werden für Terminvorschläge abgelehnt.
Floating-Zeiten/ganztägige Termine verwenden die konfigurierte Zeitzone (standardmäßig Europe/Berlin); explizite Zeitzonen
werden berücksichtigt. Fehler werden niemals als leerer/freier Kalender behandelt.

Vorschläge erscheinen in der Kalender-Vorschau. Bei ICS wird nach Freigabe eine
Datei gespeichert, die man selbst in den Kalender importiert. Das markiert keinen
remote erstellten Termin und versendet keine Einladung. iCloud-Schreiben bleibt
zusätzlich an die bestehende Schreibfreigabe und Konfliktprüfung gebunden.
Kalenderdaten löschen entfernt auch die importierte Kopie.

## Wird später integriert

Automatisches Antwortsenden, direkte Google-OAuth-Verbindungen, Google Maps und
Cloud-Modelle (ChatGPT/Gemini) sind sichtbar, aber gesperrt. Klicks zeigen:
**Bald verfügbar mit Premium-Abo – noch in Arbeit.** Es gibt keine Buchung und
keine kostenpflichtigen Aufrufe. Die zentrale Release-Sperre wird nicht durch
Entwickler-Lizenzflags aufgehoben. Bestehender Google-OAuth-/Kalender-Code bleibt
erhalten; Live-Adapter werden vor dem Laden von Zugangsdaten gesperrt.

Antwortentwürfe bleiben kostenlos. Premium ist noch kein fertiges Produkt:
Abrechnung, Lizenzerteilung und produktive Maps-/Cloud-Modell-Anbindungen sind
nicht umgesetzt. Sie gehören nicht zum normalen kostenlosen Ablauf.

## Verwendete Standards und Bibliotheken

- Python `imaplib` / `email` / `mailbox`: https://docs.python.org/3/library/imaplib.html
- Kalender-Serien: https://recurring-ical-events.readthedocs.io/en/stable/user-guide/examples.html
- CalDAV: https://github.com/python-caldav/caldav
- Outlook IMAP OAuth: https://learn.microsoft.com/en-us/exchange/client-developer/legacy-protocols/how-to-authenticate-an-imap-pop-smtp-application-by-using-oauth
- Gmail App-Passwörter: https://support.google.com/accounts/answer/185833

Tests verwenden synthetische Postfächer und Kalenderdateien. Echte Logins und
Provider-Kompatibilität sind ohne Zugang zu den jeweiligen Testkonten unbestätigt.
