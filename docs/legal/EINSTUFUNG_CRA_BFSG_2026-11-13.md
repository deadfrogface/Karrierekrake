# Einstufung nach Cyber Resilience Act und BFSG (Stand 13.11.2026)

**Vorbereitete Einstufung, keine Rechtsberatung und keine Freigabe.** Erstellt von Claude Code im Auftrag von
Damiano. Das Dokument begründet eine Einstufung aus den Produktfakten im Repository, damit eine qualifizierte Person
sie bestätigen oder korrigieren kann. Offene Tatsachen sind als `[OFFEN]` markiert. Die Rechtsstände wurden am
13.11.2026 gegen Sekundärquellen geprüft, nicht gegen den amtlichen Text.

Die Punkte T06.08, T06.09 und T10.06 in `docs/project/PR144_WORK_ITEMS.json` bleiben `BLOCKIERT – EXTERN`, bis der
Anbieter die Einstufung verantwortet.

## Teil 1 – Cyber Resilience Act (Verordnung (EU) 2024/2847)

### 1.1 Ergebnis in Kürze

| Frage | Einstufung | Sicherheit der Einstufung |
|---|---|---|
| Fällt Karrierekrake unter den CRA? | Ja, sobald es im Rahmen einer Geschäftstätigkeit bereitgestellt wird (Verkauf, auch kostenlose Basis mit Bezahlstufe) | hoch |
| Gilt das schon für die Alpha? | Nein, solange sie nicht verkauft und nur an bekannte Tester gegeben wird | mittel, hängt an der tatsächlichen Verteilung |
| Welche Klasse? | Standardprodukt („default“), keine wichtige oder kritische Klasse | mittel bis hoch, siehe 1.3 |
| Welches Konformitätsverfahren? | Interne Kontrolle durch den Hersteller (Selbstbewertung, Modul A) | folgt aus der Klasse |
| Wer ist Hersteller? | `[OFFEN]` – der Anbieter, der das Produkt unter eigenem Namen bereitstellt | – |

### 1.2 Anwendbarkeit

Karrierekrake ist Software, die bestimmungsgemäß Datenverbindungen aufbaut (Stellenportale, Update-Prüfung,
Modell-Download, optionale E-Mail- und Kalenderkonten). Das ist ein „Produkt mit digitalen Elementen“.

Der CRA knüpft an die Bereitstellung auf dem Markt im Rahmen einer Geschäftstätigkeit an. Geplant sind Bezahlstufen
über Paddle (`docs/commercial/pricing-decision.md`). Damit ist auch die kostenlose Basis Teil eines geschäftlichen
Angebots. Die Ausnahme für freie und quelloffene Software ohne Gewinnerzielung greift nicht.

### 1.3 Klasse

Wichtige Produkte (Anhang III) und kritische Produkte (Anhang IV) sind solche, deren **Kernfunktion** einer dort
genannten Kategorie entspricht. Kernfunktion von Karrierekrake ist die Unterstützung bei Stellensuche und
Bewerbung. Das steht in keiner der Kategorien.

Drei Bestandteile verdienen eine ausdrückliche Prüfung, weil sie an Kategorien aus Anhang III erinnern:

| Bestandteil | Kategorie in Anhang III | Warum es die Klasse voraussichtlich nicht ändert |
|---|---|---|
| Eingebetteter Browser (Playwright/Chromium für Bewerbungsportale) | Browser, Klasse I | Der Browser ist Hilfsmittel, nicht Kernfunktion. Der Einbau eines wichtigen Produkts macht das Gesamtprodukt nicht selbst wichtig. Die Sicherheitspflichten für die Komponente (aktuelle Version, Updates) bleiben |
| Zugangsdaten im Schlüsselbund des Betriebssystems | Passwortmanager, Klasse I | Karrierekrake speichert eigene Tokens im System-Schlüsselbund und verwaltet keine Passwörter als Produktzweck |
| Anmeldung bei E-Mail und Kalender (OAuth) | Identitätsmanagement, Klasse I | Die App ist Client eines fremden Identitätsdienstes und betreibt selbst keinen |

Bestätigt die Prüfung das, gilt die Standardklasse mit Selbstbewertung. Kommt sie zu einem anderen Ergebnis, ist für
Klasse I eine harmonisierte Norm oder eine Stelle von außen nötig.

### 1.4 Fristen

| Datum | Pflicht |
|---|---|
| seit 11.09.2026 | Meldepflichten für aktiv ausgenutzte Schwachstellen und schwere Sicherheitsvorfälle: Frühwarnung binnen 24 Stunden, Meldung binnen 72 Stunden, Abschlussbericht (14 Tage nach verfügbarem Fix bzw. ein Monat bei Vorfällen). Meldung über die ENISA-Plattform, in Deutschland an das BSI |
| ab 11.12.2027 | Alle übrigen Pflichten: Sicherheitsanforderungen, technische Dokumentation, Konformitätserklärung, CE-Kennzeichnung |

Die Meldepflicht gilt also schon vor den übrigen Pflichten, sobald das Produkt bereitgestellt ist.

### 1.5 Pflichten des Herstellers und Stand im Repository

| Pflicht | Stand | Beleg oder Lücke |
|---|---|---|
| Risikobewertung | vorhanden, zu aktualisieren | `docs/security/PR144_PRODUCT_RISK_REGISTER.md`, `docs/security/local-data-threat-model.md` |
| Keine bekannten ausnutzbaren Schwachstellen bei Auslieferung | läuft in CI | Job `security` (pip-audit, OSV, Bandit, Gitleaks). Offen: T06.05.04.03.50 (libstdc++, kein Upstream-Fix) und die nativen Inventare T06.05.05/T06.05.06 |
| Sichere Standardeinstellungen | vorhanden | Dry-Run und Bestätigung vor dem Versand, `apply_safe_defaults` |
| Sicherheitsupdates, getrennt von Funktionsupdates soweit möglich | vorhanden | In-App-Updater; jede Datei wird gegen die SHA-256-Prüfsumme im Manifest geprüft (`core/app_updates.py`). Das Manifest selbst ist nicht signiert; das hängt an der Code-Signatur (P02/P05) |
| Stückliste der Software (SBOM) | vorhanden je Release | `release-sbom.json` je Plattform im Release |
| Meldeweg für Schwachstellen, koordinierte Offenlegung | Text vorhanden, Adresse fehlt | `SECURITY.md` – Meldeadresse und Hersteller `[OFFEN]` |
| Unterstützungszeitraum festlegen und nennen | `[OFFEN]` | Mindestens fünf Jahre, außer das Produkt wird erwartbar kürzer genutzt; dann die erwartete Nutzungsdauer. Die Begründung gehört in die technische Dokumentation |
| Ablauf für Vorfälle | geübt, Verantwortliche fehlen | `docs/operations/SUPPORT_BACKUP_INCIDENT.md`, `docs/security/INCIDENT_EXERCISE_2026-10-20.json` – Name der meldenden Person `[OFFEN]` |
| Technische Dokumentation, EU-Konformitätserklärung, CE | nicht begonnen | fällig zum 11.12.2027 |
| Angaben für Nutzer (Hersteller, Kontakt, Supportende, sichere Einrichtung) | teilweise | Hilfe in der App; Herstellerangaben `[OFFEN]` |

### 1.6 Was der Anbieter entscheiden muss

1. Hersteller mit Name und Anschrift benennen (derselbe wie im Impressum).
2. Meldeadresse für Sicherheitslücken einrichten und in `SECURITY.md` eintragen.
3. Unterstützungszeitraum je Version festlegen. Vorschlag zur Diskussion: Sicherheitsupdates für die jeweils
   aktuelle Hauptversion, mindestens fünf Jahre ab Verkaufsstart des Produkts.
4. Person benennen, die im Ernstfall binnen 24 Stunden meldet, und eine Vertretung.
5. Die Einstufung aus 1.3 von einer qualifizierten Person bestätigen lassen.
6. Schriftlich festhalten, dass die Alpha nicht geschäftlich bereitgestellt wird, solange das so ist.

## Teil 2 – Barrierefreiheitsstärkungsgesetz (BFSG)

### 2.1 Ergebnis in Kürze

| Gegenstand | Einstufung | Sicherheit der Einstufung |
|---|---|---|
| Die Desktop-Anwendung selbst | Voraussichtlich kein Produkt und keine Dienstleistung im Sinne des BFSG | mittel – bitte bestätigen lassen |
| Website mit Bestellmöglichkeit für Verbraucher | Dienstleistung im elektronischen Geschäftsverkehr, grundsätzlich erfasst | hoch |
| Ausnahme für Kleinstunternehmen | Greift für die Dienstleistung, wenn die Voraussetzungen vorliegen | hängt an `[OFFEN]` Unternehmensdaten |
| Bestellstrecke bei Paddle | Liegt in der Verantwortung von Paddle als Verkäufer | mittel |

### 2.2 Begründung

Das BFSG gilt seit dem 28.06.2025 für bestimmte Produkte und Dienstleistungen für Verbraucher.

**Produkte** sind im Gesetz abschließend aufgezählt: unter anderem Computer, Tablets und Smartphones samt
Betriebssystem, Selbstbedienungsterminals, Fernseher mit Internetzugang und E-Book-Lesegeräte. Anwendungssoftware
für Bewerbungen steht nicht in dieser Liste.

**Dienstleistungen** sind ebenfalls aufgezählt: Telekommunikation, Bankdienstleistungen, E-Books mit zugehöriger
Software, Teile der Personenbeförderung und Dienstleistungen im elektronischen Geschäftsverkehr. Letzteres meint
Angebote über Websites oder Apps, die auf den Abschluss eines Verbrauchervertrags gerichtet sind. Eine Website, auf
der man Karrierekrake bestellen kann, fällt darunter. Die lokal laufende Anwendung dient nicht dem Vertragsschluss.

**Kleinstunternehmen**, die Dienstleistungen erbringen, sind von den Anforderungen ausgenommen. Kleinstunternehmen
ist, wer weniger als zehn Personen beschäftigt und höchstens 2 Mio. € Jahresumsatz oder höchstens 2 Mio. €
Jahresbilanzsumme hat. Die Ausnahme gilt nicht für Produkte.

### 2.3 Tatsachen, die der Anbieter bestätigen muss

| Tatsache | Stand |
|---|---|
| Zahl der Beschäftigten | `[OFFEN]` |
| Jahresumsatz oder Bilanzsumme | `[OFFEN]` |
| Verkauf an Verbraucher | Ja, laut Preisentscheidung |
| Wo wird bestellt | Paddle-Bestellseite, Einstieg über die eigene Website |

Sind die ersten beiden Zeilen unter den Schwellen, ist die eigene Website nach heutigem Stand ausgenommen. Die
Ausnahme entfällt, sobald eine Schwelle überschritten wird. Dann muss die Bestellstrecke barrierefrei sein und eine
Erklärung zur Barrierefreiheit veröffentlicht werden.

### 2.4 Was unabhängig von der Pflicht schon getan ist

Die Anwendung wird auf Barrierefreiheit geprüft, auch ohne gesetzliche Pflicht:

- Tastaturbedienung, Fokus und zugängliche Namen: `tests/test_a11y_*`.
- 200 % Skalierung im gebauten Paket: Selbsttests `scaling_200` und `new_user_journey` (Einrichtung, Lebenslauf-Import,
  Suche) in `desktop/package_selfcheck.py`, in CI auf Windows, macOS und Linux.
- Website-Vorschau ohne Skripte mit Sprunglink und sichtbarem Fokus: `website/index.html`.
- Technischer Bericht: `docs/accessibility/bfsg-engineering-report.md`.

Offen bleibt die Prüfung mit echter Vorlesesoftware (NVDA unter Windows, VoiceOver unter macOS) einschließlich der
Bestellseite. Das ist T10.05 und braucht eine Person am Gerät.

### 2.5 Was der Anbieter entscheiden muss

1. Unternehmensdaten aus 2.3 schriftlich festhalten und einmal im Jahr prüfen.
2. Die Einstufung der Anwendung aus 2.1 bestätigen lassen.
3. Keine öffentliche Aussage „BFSG-konform“ oder „ausgenommen“ vor dieser Bestätigung.
4. Einmal mit NVDA durch Einrichtung, Import, Suche und Bestellung gehen und das Protokoll ablegen.

## Quellen (abgerufen 13.11.2026, Sekundärquellen)

- CRA Klassen und Verfahren: [CMS](https://cms.law/en/int/legal-updates/does-the-eu-cyber-resilience-act-apply-to-your-product-scope-definitions-and-the-product-classification-system-explained), [cyberresilienceact.eu](https://www.cyberresilienceact.eu/faq.html)
- CRA Art. 13 und Unterstützungszeitraum: [Springlex, Art. 13](https://www.springlex.eu/en/packages/cra/cra-regulation/article-13/), [eucybersecurity.org](https://www.eucybersecurity.org/glossary/support-period)
- CRA Meldepflichten ab 11.09.2026: [IHK Nürnberg](https://www.ihk-nuernberg.de/meldungen/details/cyber-resilience-act-cra-meldepflichten-ab-11-september-2026)
- BFSG Anwendungsbereich und Kleinstunternehmen: [IHK Cottbus](https://www.ihk.de/cottbus/innovation-und-nachhaltigkeit/innovation-und-digitalisierung/bfsg-6492896), [SRD Rechtsanwälte](https://www.srd-rechtsanwaelte.de/blog/barrierefreiheitsstaerkungsgesetz-bfsg-neue-pflichten-fuer-unternehmen-ab-28-juni-2025), [Gesetzestext](https://www.gesetze-im-internet.de/bfsg/)
