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
