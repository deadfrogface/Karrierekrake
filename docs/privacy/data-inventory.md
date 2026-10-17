# Datenschutz — Dateninventar & Lifecycle (PR42)

**Status:** technisches Privacy Engineering.  
**Kein** Rechtsgutachten. Lokale KI ist ein **Datenschutzvorteil**, macht Karrierekrake
**nicht** automatisch DSGVO-konform.

Rechtsgrundlagen, die vom finalen Businessmodell abhängen:

> **UNSPECIFIED / LEGAL REVIEW**

Keine Art.-6-Erfindung durch dieses Dokument oder durch Code.

Offizielle Referenzen:

- [DSGVO / Regulation (EU) 2016/679](https://eur-lex.europa.eu/eli/reg/2016/679/oj)
- [BDSG](https://www.gesetze-im-internet.de/bdsg_2018/)

Maschinenlesbar: `core/privacy/inventory.py` (`DATA_INVENTORY`).

## Privacy by design (technisch)

| Regel | Umsetzung |
|-------|-----------|
| Data minimization | Lifecycle löscht granular; Export nur mit PII-Bestätigung |
| No unnecessary logs | `SecretRedactionFilter`; Günther event codes only |
| No undocumented cloud flow | Inventory muss jeden Transfer nennen — sonst STOP |
| No hidden telemetry | Kein Sentry/Analytics im Repo |
| User-visible delete/export | Settings → Datenschutz; Profil-Wipe mit Verifikation |

## Datenklassen (Kurz)

Für jede Klasse im Code-Inventar: source, data subjects, purpose, storage,
cloud transfer, retention, PII, special-category risk, deletion trigger,
security, processor, legal_basis.

Mindestumfang abgedeckt:

Profil · Adresse/Kontakt · Berufserfahrung · CV/DOCX/PDF · extrahierter CV-Text ·
Jobs · ApplicationCases · Mailinhalte · Calendar FreeBusy/Events · OAuth Tokens ·
HR-Kontakte · Logs · Exports · Backups · Payment/Account (**nicht vorhanden**) ·
Support/Crash (**kein Uploader**) · Browser-Profil · lokale Modelle

## Nutzeraktionen

| Aktion | API |
|--------|-----|
| Meine Daten exportieren | `PrivacyLifecycleService.export_my_data` |
| Profil löschen | `delete_profile` |
| Dokument löschen | `delete_document` / `delete_documents_all` |
| ApplicationCase löschen | `delete_application_case` |
| Mailcache löschen | `delete_mail_cache` |
| Calendarcache löschen | `delete_calendar_cache` |
| Google trennen | `disconnect_google` |
| OAuth Token löschen | `delete_oauth_tokens` |
| Logs löschen | `delete_logs` |
| ALLE Daten löschen | `delete_all` (verified; default **kein** PII-Backup) |

## Verifikation / Rollback

- Delete ist **idempotent**.
- UI darf „gelöscht“ nur anzeigen, wenn `ok` und `verified`.
- `VerificationFailed` / `residuals` bei Fehlschlag.
- Externer deutscher IT-/Datenschutzanwalt prüft final (Commercial Gate).

## Unerklärter Datenfluss

Wenn ein neuer Persistenzpfad oder Cloud-Call nicht im Inventar steht: **STOP** —
PR nicht mergen, bis Inventory + Löschweg ergänzt sind
(`PrivacyLifecycleService.unexplained_flows()` muss leer bleiben; neue Klassen
müssen `storage` und `purpose` gesetzt haben).


## Ergänzungen PR144, 14.10.2026

- Credential-Wipe umfasst Google OAuth, Microsoft Mail/Kalender, IMAP und CalDAV; unlesbarer Keyring ist kein erfolgreicher Löschbeleg.
- Nutzergewählte lokale Backups sind vollständige, unverschlüsselte Datenkopien, keine Supportberichte. Separat gespeicherte Backups/Exporte werden nicht durch App-Datenlöschung entfernt.
- Zahlungs-Sandbox: optionales lokales SQLite-Journal mit synthetischen Event-/Account-IDs und Aktionen. Keine Anbieterübertragung und keine produktive Berechtigung. Nicht mit echten Personendaten befüllen.
- Nativer Updater lädt ausschließlich das validierte plattformspezifische Releasepaket von GitHub. Zwischenordner und vorheriges Programmpaket liegen neben der Installation; Nutzerprofile werden nicht mitgetauscht.

## Ergänzung PR144: Lizenz, Zahlungen, Sponsoren

Die ausführbare Inventarliste `core/privacy/inventory.py` enthält jetzt `payment_account` und `sponsor_consent`. Lokal liegen nur signierte Lizenzinformationen (pseudonyme ID, Revision, Ablauf, Funktionen) und eine kampagnengebundene Zustimmung. Beide werden im Metadatenexport berücksichtigt und durch „Alle Daten löschen“ entfernt. Der Wiederanlaufcheck prüft den Commerce-Ordner auf Reste.

Die Desktop-App sendet keine Karten-/Rechnungsdaten und enthält keinen Händler-API-Key. Erst ein bestätigter Browserwechsel öffnet konfigurierte Anbieterwege. Separate Betreiberwerkzeuge verarbeiten Paddle-IDs und signieren Lizenzdateien; ihre Daten gehören nicht zum Nutzer-App-Verzeichnis. Rollen, Aufbewahrung und Betroffenenanfragen beim Anbieter bleiben Teil der externen Vertrags-/Datenschutzentscheidung.

Sponsoren sind lokal gebündelte, als Anzeige beschriftete Texte ohne SDK, Pixel oder ferngeladene Bilder. Zustimmung ist abwählbar und gilt nur für die konkrete Kampagnenversion. Neue Kampagne erfordert neue Zustimmung. Der externe Partnerlink wird erst nach Bestätigung geöffnet.

Export enthält alle vorhandenen Fälle (keine 5.000er-Begrenzung), Fall-/Lebenszyklusereignisse, Aufgaben, Wiedervorlagen und alte Bewerbungsdatensätze. Es bleibt ein redigierter Metadatenexport: Mailtexte, Originaldokumentbytes, Logs, Zugangsdaten und ICS-Inhalte sind standardmäßig nicht enthalten. Für eine vollständige lokale Wiederherstellung dient das separat bestätigte Backup. Fehlende Lesbarkeit meldet einen Fehler; unvollständige ZIPs werden entfernt.
