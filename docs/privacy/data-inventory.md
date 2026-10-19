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

## Netzziele Jobsuche auf Host-Ebene (T07.06, PR144, Stand 18.10.2026)

Bisher nannte dieses Dokument nur Datenklassen (`jobs`, `cloud_transfer`), keine Hosts. Die Tabelle unten führt jeden Host auf, der in `search/` oder im gepinnten `python-jobspy==1.3.0` (Code im venv, `jobspy/*/__init__.py`) als Netzziel vorkommt. Methode: statische Suche (`rg 'https?://'`) plus Lesen der Aufrufpfade, **kein Laufzeit-Mitschnitt**. Ausgehend sind bei allen Jobquellen Suchbegriff, Ort/Umkreis und IP-Adresse, keine Profil- oder CV-Daten.

Einordnung „Standard“/„optional“ nach Produktvorgabe: Standard sind nur Bundesagentur und Indeed, alles andere ist optional. **Abweichung im Code:** `core/config.py:374–376` aktiviert `company_sites` (Websuche + Arbeitgeberseiten + Greenhouse/Lever) ebenfalls standardmäßig, und `core/config.py:1029–1032` schaltet es für bestehende Installationen einmalig zu. Das ist als Befund offen und hier nicht geändert.

### Laufzeit-Requests aus `search/`

| Host | Zweck | Quelle (Code) | Einordnung | Limits / ToS-Hinweis |
|---|---|---|---|---|
| `rest.arbeitsagentur.de` | BA-Jobsuche: Liste `pc/v6/jobs`, Details `pc/v4/jobdetails` | `search/bundesagentur.py:32–34` | Standard | Seitengröße 25, bis 8 parallele Detailabrufe (`:36–37`), öffentlicher Client-Key `jobboerse-jobsuche`; offizielles Rate-Limit/Nutzungsbedingungen **UNSICHER** (nicht im Code) |
| `apis.indeed.com` | Indeed GraphQL-Suche über JobSpy, `country_indeed="germany"` | `search/indeed.py:87–90` → `jobspy/indeed/__init__.py:34` | Standard | requests-Session (`is_tls=False`, `:43–44`), seitenweise bis `results_wanted`, keine Pause in JobSpy; Indeed-ToS zu automatisierten Abfragen **UNSICHER** |
| `www.linkedin.com` | LinkedIn-Gastsuche `jobs-guest/jobs/api/seeMoreJobPostings/search` | `search/linkedin.py` → `jobspy/linkedin/__init__.py:40,75` | optional | JobSpy wartet 3–7 s je Seite (`:41–42,71`); Karrierekrake: max. 2 Anfragen × 15 Treffer, `linkedin_fetch_description=False` (keine `/jobs/view/`-Abrufe, `search/linkedin.py:16–17,36`). LinkedIn-ToS untersagen Scraping grundsätzlich: **UNSICHER**, rechtliche Bewertung offen |
| `www.stepstone.de` | Öffentliche Suchseiten `/jobs/…`, `/work/…`, Healthcheck `/` | `search/stepstone.py:40,74,78` | optional | bis 2 Seiten (`:83–89`); sendet Browser-User-Agent (`:24–28`); ToS **UNSICHER** |
| `www.xing.com` | Öffentliche Suchseiten `/jobs/search`, Healthcheck `/jobs` | `search/xing.py:39,72` | optional | bis 2 Seiten (`:76–82`); Browser-User-Agent; ToS **UNSICHER** |
| `boards-api.greenhouse.io` | Öffentliche Board-API, 5 kuratierte Boards + entdeckte Boards | `search/company_sites.py:21,70`; `search/public_ats.py:24` | optional (Code-Default aktiv, s. o.) | 20 s Timeout, 8 Worker, ein Abruf je Board und Suche |
| `api.lever.co` | Öffentliche Postings-API, 3 kuratierte Boards + entdeckte | `search/company_sites.py:22,106`; `search/public_ats.py:28` | optional (Code-Default aktiv) | wie Greenhouse |
| `api.eu.lever.co` | Lever EU, nur für entdeckte `jobs.eu.lever.co`-Links | `search/public_ats.py:28` | optional (Code-Default aktiv) | über `PublicPages`-Budget |
| `api.ashbyhq.com` | Ashby Job-Board-API, nur für entdeckte `jobs.ashbyhq.com`-Links | `search/public_ats.py:31` | optional (Code-Default aktiv) | über `PublicPages`-Budget |
| `html.duckduckgo.com` | Websuche nach Karriereseiten (Suchbegriff + Ort) | `search/company_web.py:23,94–96` | optional (Code-Default aktiv) | `WebSearchGuard`: 24 h Cache (Begriffe nur gehasht), min. 30 s Abstand, 6/h, 30/Tag, 30 min Pause nach Fehler, 24 h nach Sperre (`search/web_search_guard.py:14–19`); CAPTCHA wird nicht umgangen (`company_web.py:98–99`) |
| `search.brave.com` | **Neu, bisher nirgends inventarisiert.** Fallback-Websuche, wenn DuckDuckGo scheitert: `ddgs.DDGS().text(…, backend="brave")` | `search/company_web.py:121–134` → `ddgs/engines/brave.py:17` (ddgs 9.16.0 im venv) | optional (Code-Default aktiv) | eigener Guard-Eintrag `brave` mit denselben Limits; Transport `primp` (nativ). ddgs/primp-Version im Release **UNSICHER** (nicht in `constraints-runtime.txt`) |
| beliebige Arbeitgeber-Hosts | Abruf von Karriereseiten aus Suchtreffern, `robots.txt` je Origin, Folge-Links bis Tiefe 2 | `search/company_web.py:51–87,200–235` | optional (Code-Default aktiv) | nur öffentliche IPs, Port 80/443, ohne Zugangsdaten (`:26–35`); `robots.txt` wird beachtet; max. 20 Seiten, 2 MB je Seite, 75 s bzw. 20 s Budget, 6 Weiterleitungen. Hosts dynamisch, nicht abschließend aufzählbar: **UNSICHER** |

### Nur Links (kein Request durch die App)

| Host | Zweck | Quelle |
|---|---|---|
| `www.arbeitsagentur.de` | Detail-Link `jobsuche/jobdetail/{ref}` | `search/bundesagentur.py:210` |
| `de.indeed.com` | `job_url`/`company_url` (`https://{domain}.indeed.com`, Domain `de` aus `Country.GERMANY`) | `jobspy/indeed/__init__.py:51,192,202`; `jobspy/model.py:89,147–151` |
| `www.linkedin.com/jobs/view/…` | `job_url` | `jobspy/linkedin/__init__.py:159` |

### Hosts in python-jobspy 1.3.0, von Karrierekrake nicht aufgerufen

Karrierekrake übergibt nur `site_name=["indeed"]` bzw. `["linkedin"]` (`search/indeed.py:87`, `search/linkedin.py:21`). Die übrigen Scraper werden mitgepackt (`collect_all jobspy`), aber nicht angesprochen: `www.glassdoor.*` (Domain aus `Country`, `jobspy/model.py:154–162`), `www.google.com/search` und `www.google.com/async/callback:550` (Google-Jobs-Suche, `jobspy/google/__init__.py:36–37`), `www.ziprecruiter.com`, `www.bayt.com`, `www.naukri.com`, `www.hellowork.com`, `bdjobs.com`/`api.bdjobs.com`/`gateway.bdjobs.com`. `http://localhost` in `jobspy/util.py:50` ist nur ein Proxy-Format-Beispiel.

### Geocoding

Google Maps, die Nominatim-HTTP-API oder geopy kommen in `search/` und in python-jobspy 1.3.0 **nicht** vor (Suche nach `maps`, `nominatim`, `geocod`, `openstreetmap`: 0 Treffer). In `core/geo_resolve.py` steht `Nominatim` nur für die Offline-Klasse `pgeocode.Nominatim` über lokale GeoNames-Dateien; Netz-Geocoding ist deaktiviert (`:13,1166,1201`).

### Außerhalb von `search/` (nicht neu bewertet, Stand #177-Register)

Weiter ohne Host-Dokumentation hier: `brouter.de`, `download.geonames.org`, `symerio.github.io`, `graph.microsoft.com`, `login.microsoftonline.com`, `outlook.office.com`, `outlook.office365.com`, `imap.gmx.net`, `imap.web.de`, `imap.mail.me.com`, `caldav.icloud.com`. **UNSICHER** bleiben, mit Grund aus dem Register: `api.github.com` (Updater, keine Klasse im `DATA_INVENTORY`), `github.com` (Release-/Modell-Assets und BRouter-JAR als Fremdbinary), `imap.gmail.com` (IMAP-Passwortweg nicht inventarisiert), `smtp-mail.outlook.com`/`smtp.mail.me.com`/`smtp.web.de` (nur Konstanten, kein Versandpfad gefunden), `chatgpt.com`/`claude.ai`/`gemini.google.com`/`www.kimi.com` (Browser-Links der KI-Chat-Bridge, Datenübergabe durch Nutzer). Die Datenschutzabnahme bleibt beim Menschen.

### Ergänzung 2026-10-19 (T07.06, Code-Stand #144)

Neue Klassen in `DATA_INVENTORY`: `route_data` (`brouter.de`, BRouter-ZIP von `github.com`, SHA-256 gepinnt), `geo_dataset` (`download.geonames.org`, `symerio.github.io`, nur optional), `web_search` (`html.duckduckgo.com`, `search.brave.com`: Suchbegriff und Ort), `app_updates` (`api.github.com`, Release-Assets). `mail_content`, `oauth_tokens` und `calendar_freebusy` nennen jetzt auch Microsoft, GMX, WEB.DE, iCloud (IMAP/CalDAV/PKCE/Graph-Probe).

Weiter **UNSICHER** bzw. **OFFEN**: automatische Downloads ohne Einwilligung (`brouter.de`, `api.github.com`; Teamlead), Suchmaschinen als Empfänger (rechtliche Prüfung), Speicherweg der IMAP-Passwörter (`fallback_dir`), Minimalität der Microsoft-Scopes, `delete_all` entfernt weder das BRouter-Verzeichnis noch `web-search-guard.sqlite3`. Die Datenschutzabnahme bleibt beim Menschen.
