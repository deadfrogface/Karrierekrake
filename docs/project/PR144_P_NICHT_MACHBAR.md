# PR 144 – P-Liste: für Claude Code nicht machbare Punkte

Stand 20.10.2026. Auftrag Damiano: alle 58 offenen und 27 blockierten Kriterien bearbeiten; nur was für Claude Code
tatsächlich nicht machbar ist, wird hier als P-Eintrag notiert, danach geht es mit dem nächsten Punkt weiter.

„Nicht machbar“ heißt: Es braucht etwas, das Claude Code weder hat noch erzeugen darf – ein physisches Gerät, ein
echtes Konto oder Zahlungsmittel, einen Signaturschlüssel, eine verbindliche Rechts-/Geschäftsentscheidung oder ein
persönliches Gespräch. Vorbereitende Unterlagen liegen in `docs/project/PR144_ENTSCHEIDUNGSVORLAGEN_2026-10-20.md`.
Teilarbeit, die doch machbar war, steht beim jeweiligen Eintrag unter „Erledigt“.

| P | T | Was fehlt | Von wem | Erledigt |
|---|---|---|---|---|
| P01 | T02.08 | Messung auf den physischen Geräten Fujitsu und ThinkPad (Geschwindigkeit mit Gerätename/CPU/RAM, Qualitätsurteil HR) | Damiano (Gerät), Team als HR | – |
| P02 | T03.07 | Code-Signing-Zertifikate/Signaturschlüssel kaufen und verwahren | Damiano | Versionssprünge bereits entschieden (letzte und vorletzte Version) |
| P03 | T03.08 | Windows-Altversionsablauf auf einem echten Endnutzergerät durchführen und abnehmen | Damiano | – |
| P04 | T04.06 | Installation/Deinstallation/Browser/Keyring auf jedem zugesagten realen Gerät | Damiano | – |
| P05 | T04.07 | Apple Developer ID/Notarisierung und Windows-Codesignatur (Konto, Zertifikat) | Damiano | Supportmatrix = CI-Matrix bereits entschieden |
| P06 | T06.08 | Hersteller, Sicherheitskontakt und Supportzeitraum verbindlich benennen | Damiano | – |
| P07 | T06.09 | CRA-Einstufung qualifiziert bestätigen, Konformitätsunterlagen verantworten | Damiano / Rechtsberatung | Einstufung vorbereitet (keine geschäftliche Bereitstellung der Alpha) |
| P08 | T07.07 | Verantwortlichen, externe Empfänger und Rechtsgrundlagen festlegen | Damiano / Datenschutz | – |
| P09 | T07.08 | Externe Löschfristen/Verträge (AV-Verträge) und freigegebene Datenschutzhinweise | Damiano / Datenschutz | – |
| P10 | T08.06 | Abgleich der Paketbibliotheken **nach** Signierung – setzt P02/P05 voraus | – (folgt aus P02/P05) | Abgleich vor Signierung läuft je Plattform in CI |
| P11 | T08.07 | Eigene Assetrechte, restriktive Lizenzentscheidungen, Restrisiken freigeben | Damiano | – |
| P12 | T09.03 | Anbieterwege Client ↔ Checkout vergleichen – Checkout existiert erst mit T12 | – (folgt aus P16–P19) | – |
| P13 | T09.04 | Anbieter, Anschrift, Kontakt, Preis, Laufzeit, Leistungsversprechen verbindlich liefern | Damiano | – |
| P14 | T09.05 | Vertragstyp und Verbraucherabläufe final freigeben | Damiano / Rechtsberatung | – |
| P15 | T09.06 | Reale Vertragsbestätigung/Widerruf/Kündigung beim gewählten Anbieter abnehmen | Damiano | – |
| P16 | T10.05 | NVDA/VoiceOver mit echter assistiver Technik am Bildschirm und echter Checkout | Tester:in mit AT | – |
| P17 | T10.06 | Unternehmensdaten, BFSG-Anwendungsbereich, Informationspflichten freigeben | Damiano | Bewertung Kleinstunternehmen-Ausnahme vorbereitet |
| P18 | T11.06 | Preise, Leistungsgrenzen, Partner, Banner, freigegebene Dienste festlegen | Damiano | – |
| P19 | T11.07 | OAuth-/Anbieterprüfungen (z. B. Google-Verifizierung) mit dem echten Konto abschließen | Damiano | – |
| P20 | T12.05 | Echter Sandbox-Rundlauf beim Zahlungsanbieter – braucht Konto/Schlüssel aus P21 | Damiano | lokale Adapter-Regressionen vorhanden |
| P21 | T12.06 | Zahlungskonto, Identitätsprüfung, Produkte, Schlüssel bereitstellen | Damiano | – |
| P22 | T12.07 | Gebühren, Vertrag, Steuer- und Rechnungsprozess freigeben | Damiano / Steuerberatung | – |
| P23 | T12.08 | Realen Lizenzbereitstellungs- und Kundenannahmeweg festlegen | Damiano | – |
| P24 | T13.05 | Selbstständigkeit, Steuer, Konto, Softwaretätigkeit verantwortlich klären | Damiano / Steuerberatung | – |
| P25 | T13.06 | Supportadresse, Zuständigkeit, Bearbeitungszeit, Vertretung festlegen | Damiano | – |
| P26 | T14.04 | Name, Logo, Rechteinhaber, Schutzgebiet, Domain und Budget bestimmen | Damiano | Recherche T14.03 als Grundlage |
| P27 | T14.05 | Anbieterangaben, Rechtefreigabe, Markenanmeldung und Veröffentlichung freigeben | Damiano | – |
| P28 | T15.05 | Veröffentlichungsfreigabe (Vorgabe „Veröffentlichen verboten“) und reale Durchläufe | Damiano | – |
| P29 | T16.05 | Reale Kosten, Nachfrage, Nutzungsbelege und Finanzierungsgrenzen | Damiano | – |
| P30 | T16.06 | Jörg/Partner/Investoren persönlich ansprechen, Vereinbarungen freigeben | Damiano | – |
| P31 | T06.05.04.03.50 | CVE-2026-95619: Überlauf im ausgerichteten `operator new` von libstdc++ – in allen GCC-Releases bis 15.1 enthalten, erst auf master behoben; es gibt keine korrigierte Bibliothek zum Bündeln | Upstream GCC / Ubuntu | Analyse, Auslösebereich und Importeure dokumentiert (Disposition) |
| P32 | T07.06 | Verbindliche Entscheidung: automatische Update-Prüfung (api.github.com) und BRouter-Kacheldownload (brouter.de) ohne Einwilligung oder Opt-in; DuckDuckGo/Brave und die KI-Chat-Anbieter als eigenständige Empfänger | Damiano / Datenschutz | Alle übrigen Netzwerkziele technisch geprüft und dokumentiert (Register, DATA_INVENTORY) |
