# PR 144 – Entscheidungsvorlagen für blockierte und abnahmepflichtige Punkte (Stand 2026-10-20)

Erstellt von Claude Code (KI-Assistent) im Auftrag von Damiano. **Keine Rechts- oder Steuerberatung, keine Freigabe.**
Jeder Punkt unten bleibt im Status `BLOCKIERT – EXTERN` bzw. `OFFEN`, bis Damiano (oder eine von ihm benannte Person)
entscheidet. Die Vorlage sagt je Punkt: was zu entscheiden ist, was im Repo schon vorbereitet ist, eine Empfehlung,
und was ausdrücklich nicht automatisch erledigt werden kann.

Rechtliche Eckdaten wurden am 2026-10-20 per Websuche gegen Sekundärquellen (IHK, Fachpresse) geprüft, nicht gegen
den amtlichen Text; vor einer Entscheidung im Amtsblatt bzw. Gesetzestext nachlesen.

## Dringend: Cyber Resilience Act (T06.08, T06.09)

- **Fakt:** Verordnung (EU) 2024/2847. Meldepflichten für aktiv ausgenutzte Schwachstellen und schwere Sicherheitsvorfälle
  gelten **seit 11.09.2026** (Erstmeldung 24 h, Folgemeldung 72 h, Abschlussbericht 14 Tage/1 Monat; Meldung über die
  ENISA-Plattform, in Deutschland BSI/CERT-Bund). Die übrigen Pflichten gelten ab **11.12.2027**.
  Quellen: IHK Nürnberg (https://www.ihk-nuernberg.de/meldungen/details/cyber-resilience-act-cra-meldepflichten-ab-11-september-2026),
  Art. 71 (https://www.springlex.eu/de/packages/cra/cra-regulation/article-71/).
- **Zu entscheiden:** Wird Karrierekrake „im Rahmen einer Geschäftstätigkeit“ bereitgestellt (geplante Bezahlstufen T09/T12
  sprechen dafür)? Wer ist Hersteller (Name, Anschrift)? Sicherheitskontakt/Meldekanal? Supportzeitraum je Version?
- **Vorbereitet:** `docs/security/T06_VERIFICATION_AND_CRA_HANDOFF.md` (Checkliste), `docs/operations/SUPPORT_BACKUP_INCIDENT.md`
  (Incident-Ablauf), `docs/security/INCIDENT_EXERCISE_2026-10-16.json` (technische Übung), Native-Befunde inkl.
  `docs/security/NATIVE_LINUX_CANDIDATE_DISPOSITION_2026-10-20.json`.
- **Empfehlung:** Solange die Alpha nicht verkauft/vertrieben wird, das ausdrücklich festhalten (dann keine
  Bereitstellung im Sinne des CRA). Vor der ersten Bereitstellung: Hersteller und eine Meldeadresse benennen
  (z. B. `security@<domain>` plus `SECURITY.md` im Repo mit Meldeweg), Supportzeitraum mindestens bis zur nächsten
  Hauptversion festlegen, CRA-Einstufung (Standardprodukt, keine wichtige/kritische Klasse erwartet – **prüfen lassen**)
  durch eine qualifizierte Person bestätigen.
- **Nicht automatisch möglich:** Herstelleridentität, rechtliche Einstufung, Konformitätserklärung.

## Datenschutz (T07.07, T07.08)

- **Zu entscheiden:** Verantwortlicher nach DSGVO (bei lokaler App: vor allem für Website, Support, Lizenz/Zahlung und
  optionale Konten), externe Empfänger je Funktion, Rechtsgrundlagen, Löschfristen, Verträge (AVV mit Paddle o. a.).
- **Vorbereitet:** `docs/privacy/data-inventory.md` mit Host-Register (Bundesagentur, Indeed/JobSpy, LinkedIn, StepStone,
  Websuche, Modell-Downloads, BRouter/GitHub u. a.), Lösch-/Export-APIs; Netzziele in `docs/privacy/NETWORK_TARGETS_PR144.json`.
- **Empfehlung:** Für den lokalen Kern ist Karrierekrake überwiegend kein Empfänger der Bewerbungsdaten (sie bleiben auf
  dem Gerät). Datenschutzhinweis nach Funktionen gliedern: (1) lokal ohne Übermittlung, (2) Jobsuche an Portale
  (Suchbegriffe/Ort gehen an die jeweiligen Dienste), (3) optionale Mail/Kalender-Konten, (4) Lizenz/Zahlung über Paddle
  als Merchant of Record. Löschfristen für eigene Systeme (Support-Mails, Lizenzdaten) konkret beziffern.
- **Nicht automatisch möglich:** Festlegung des Verantwortlichen, Verträge, freigegebener Hinweistext.

## Anbieter, Vertrag, Verbraucherrecht (T09.04, T09.05, T09.06, T13.05, T13.06)

- **Zu entscheiden:** Anbietername und ladungsfähige Anschrift, Kontakt, Preis, Laufzeit, Leistungsversprechen,
  Vertragstyp (Einmalkauf vs. Abo), Widerrufsablauf, Kündigungsweg; bestehende Selbstständigkeit/Steuer/Geschäftskonto;
  Supportadresse, Bearbeitungszeit, Vertretung.
- **Vorbereitet:** `docs/commercial/pricing-decision.md` (Paddle als einziger Anbieter, Merchant of Record),
  `core/commercial/growth_scenarios.py` für Szenarien mit ausdrücklich eingegebenen Annahmen.
- **Fakten zum Nachlesen:** Kleinunternehmerregelung § 19 UStG seit 2025: Vorjahr ≤ 25.000 €, laufendes Jahr ≤ 100.000 €
  (Netto/Brutto in den Quellen widersprüchlich – mit Steuerberatung klären; https://www.ihk-muenchen.de/ratgeber/steuern/umsatzsteuer/kleinunternehmerregelung/).
  Bei Paddle als Merchant of Record verkauft Paddle an Endkunden; Karrierekrake verkauft an Paddle (Auswirkung auf USt mit
  Steuerberatung klären).
- **Empfehlung:** Abo nur mit Kündigungsbutton (§ 312k BGB; am 20.10.2026 nicht gesondert nachgeprüft) und klarer Widerrufsbelehrung für digitale Inhalte; für
  die erste Version einen Einmalkauf bzw. eine Jahreslizenz ohne automatische Verlängerung prüfen (weniger
  Verbraucherpflichten). Support: eine Adresse, Antwort binnen 5 Werktagen zusagen, keine SLA.
- **Nicht automatisch möglich:** Alle Angaben zur Person/Firma, Steuerstatus, Kontoeröffnung, Vertragsfreigabe, realer
  Widerrufs-/Kündigungstest beim Anbieter (T09.06).

## Barrierefreiheit (T10.05, T10.06)

- **Fakt:** BFSG gilt seit 28.06.2025. Kleinstunternehmen (< 10 Beschäftigte **und** Jahresumsatz oder Bilanzsumme
  ≤ 2 Mio. €), die **Dienstleistungen** erbringen, sind von den Dienstleistungsanforderungen ausgenommen; die Ausnahme
  gilt nicht für Produkte. Quelle: IHK (https://www.ihk.de/schwaben/produktmarken/recht-und-steuern/onlinerecht/barrierefreiheitsstaerkungsgesetz-6292836).
- **Zu entscheiden:** Fällt der Online-Verkauf (Dienstleistung im elektronischen Geschäftsverkehr) unter die Ausnahme?
  Wer testet mit NVDA (Windows) und VoiceOver (macOS) inklusive echtem Checkout?
- **Vorbereitet:** Tastatur-/Fokus-/DPI-Tests (`tests/test_a11y_*`), 640×560-Layouttests.
- **Empfehlung:** Ausnahme als Kleinstunternehmen dokumentiert prüfen; unabhängig davon den Checkout bei Paddle (deren
  Seite, nicht unsere) und die App mit NVDA einmal manuell durchgehen und das Protokoll ablegen.
- **Nicht automatisch möglich:** Test mit echter assistiver Technik, Rechtsfreigabe.

## Marke und Name (T14.04, T14.05)

- **Vorbereitet:** Recherche vom 20.10.2026 in `docs/commercial/BRAND_RESEARCH_PROTOCOL.md`: keine Marke „Karrierekrake“ in
  DPMA/EUIPO/WIPO/AT/CH; ähnliche Marken „Talent Krake“/„TALENTKRAKE“ (DPMA, Kl. 35) **beendet**; eingetragene ältere
  „KRAKE“-Marken mit Kl. 9/35 (Heide-Park Soltau GmbH, EUIPO 011065414/011065422) und „KRAKE Verlag“ (Kl. 9/35/42).
  Alle geprüften Domains frei (.de/.com/.net/.app/.ch/.at/.eu).
- **Zu entscheiden:** Hält der Name (Bewertung der „KRAKE“-Altrechte durch Fachperson)? Schutzgebiet (DE oder EU),
  Klassen (Vorschlag: 9 Software, 35 Personalvermittlung/Stellenvermittlung, 42 SaaS), Logo-Rechte, Budget,
  Domain(s) registrieren.
- **Empfehlung:** Zuerst `karrierekrake.de` sichern (geringe Kosten, Momentaufnahme „frei“). DPMA-Wortmarke in Kl. 9/42
  (ggf. 35) nach Kurzprüfung der Heide-Park-„KRAKE“-Marke durch eine Fachperson.
- **Nicht automatisch möglich:** Registrierung, Anmeldung, Zahlung, Rechtsbewertung.

## Signierung, Zertifikate, Supportmatrix (T03.07, T04.07)

- **Zu entscheiden:** Windows-Codesignatur (OV/EV-Zertifikat oder Azure Trusted Signing), Apple Developer ID +
  Notarisierung, unterstützte Versionssprünge für Updates, verbindliche Supportmatrix (Windows 10/11, macOS-Versionen
  ARM/Intel, Linux-Distributionen).
- **Empfehlung:** Supportmatrix an die CI anlehnen (Windows latest, macOS 14 ARM / 15 Intel, Ubuntu 22.04-kompatibel);
  Versionssprünge nur von der letzten und vorletzten Version garantieren.
- **Nicht automatisch möglich:** Zertifikatskauf, Apple-Konto, Schlüsselverwaltung.

## Echte Geräte und Endnutzerabläufe (T03.08, T04.06)

- **Zu entscheiden/tun:** Altversion → neue Version auf einem echten Windows-Endnutzergerät; Installation,
  Deinstallation, Standardbrowser, Keyring je zugesagtem Gerät.
- **Vorbereitet:** CI-Smokes (Windows Smoke, Desktop Platforms, linux-real-systemd) und Upgrade-Tests im Paket.
- **Nicht automatisch möglich:** Bedienung echter Geräte.

## Lizenzen und eigene Assets (T08.07)

- **Zu entscheiden:** Rechte an Logo/Bildern (Master-Artwork `assets/brand/…`), restriktive Lizenzentscheidungen,
  akzeptierte Restrisiken.
- **Nicht automatisch möglich:** Bestätigung der Urheberschaft/Rechtekette.

## Angebot, Partner, Zahlung, Lizenzen (T11.06, T11.07, T12.05–T12.08)

- **Zu entscheiden:** Preise, Leistungsgrenzen der Gratisstufe, Partner/Banner, freigegebene Dienste; OAuth-Prüfungen
  (Google-Verifizierung für Gmail/Kalender-Scopes, Microsoft-Publisher-Verifizierung); Paddle-Konto mit
  Identitätsprüfung, Produkte, Schlüssel; Gebühren/Steuer/Rechnung; Weg der Lizenzauslieferung.
- **Vorbereitet:** Paddle-Entscheidung, lokale Adapter-Regressionen (ersetzen die Sandbox nicht, siehe T12.05).
- **Empfehlung:** Google-OAuth-Verifizierung früh beantragen (Gmail-Scopes gelten als eingeschränkt und können ein
  Sicherheitsassessment erfordern – am 20.10.2026 nicht gesondert nachgeprüft, Aufwand vorab bei Google klären). Paddle-Sandbox-Konto anlegen, dann T12.05 als echter
  Rundlauf.
- **Nicht automatisch möglich:** Kontoeröffnungen, Identitätsprüfungen, Verträge.

## Finanzierung und Partner (T16.05, T16.06)

- **Zu entscheiden/tun:** reale Kosten, Nachfrage- und Nutzungsbelege, Finanzierungsgrenzen; persönliche Ansprache von
  Jörg/Partnern/Investoren.
- **Vorbereitet:** `core/commercial/growth_scenarios.py` (Szenarien nur mit eingegebenen Annahmen).
- **Nicht automatisch möglich:** reale Zahlen, persönliche Gespräche, Vereinbarungen.

## Abnahmen durch das Team als HR (T01.10, T02.08, T02.09, T05.07, T15.04, T15.05)

Entscheidung Damiano 2026-10-18: synthetische Konten/Daten; das Team urteilt als HR nach
`docs/personaler/ABNAHME_CHECKLISTE.md` (Personaler urteilt, Kritiker prüft Belege, keine gesenkten Sollwerte).
Diese Urteile kann der Assistent, der die Änderungen selbst vorgenommen hat, nicht unabhängig abgeben. Offen sind je
Punkt das Personaler-Urteil und die Kritiker-Prüfung; für T02.08 zusätzlich die ThinkPad-/Fujitsu-Messung (Gerät nötig),
für T15.05 die Veröffentlichungsfreigabe durch Damiano.
