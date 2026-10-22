# Datenschutzhinweis – Entwurf (Stand 2026-10-22)

**Status: Entwurf. Keine Rechtsberatung, nicht freigegeben.** Felder in **[eckigen Klammern]** kann nur der Verantwortliche
ausfüllen. Rechtsgrundlagen und Fristen sind Vorschläge, die vor der Veröffentlichung eine fachkundige Person prüfen muss
(`docs/privacy/data-inventory.md` nennt dafür „UNSPECIFIED / LEGAL REVIEW“). Grundlage der Aussagen sind
`core/privacy/inventory.py` und `docs/privacy/NETWORK_TARGETS_PR144.json`. Die Aussagen gelten für die Alpha und sind
schon auf den späteren Verkauf ausgelegt.

---

## 1. Wer ist verantwortlich?

**[Name / Firma]**, **[ladungsfähige Anschrift]**, E-Mail: **[Datenschutz-Adresse]**.
Datenschutzbeauftragte(r), falls bestellt: **[Name und Kontakt oder „nicht erforderlich“]**.

Karrierekrake ist ein Programm, das auf deinem Gerät läuft. Deine Bewerbungsdaten verarbeitet das Programm dort.
**Wir als Hersteller erhalten sie nicht.** Verantwortlicher für die Dinge, die wir selbst betreiben (Website, Support,
Lizenz und Zahlung), ist der oben genannte Hersteller.

## 2. Was bleibt auf deinem Gerät (keine Übermittlung an uns)

Lebenslauf, Profil, Berufserfahrung, Bewerbungen und Notizen, gefundene Jobs, E-Mail- und Kalenderinhalte, lokale
Modelle und ihre Antworten, Zugangsdaten, Protokolle. (Wo genau Mail-Passwörter liegen, wenn kein Betriebssystem-Schlüsselbund verfügbar ist, ist noch nicht abschließend geprüft.)
Die lokale KI läuft auf deinem Gerät und sendet keine Texte an einen KI-Dienst. Wir bauen keine Nutzungsstatistik
und keinen Absturzbericht ein, der Daten an uns schickt.

## 3. Was beim Benutzen an Dritte geht

Das Programm verbindet sich nur dann mit einem Dienst, wenn du die Funktion nutzt. Es sendet dabei **keine Profil- oder
Lebenslaufdaten**, sondern nur, was für die jeweilige Anfrage nötig ist (IP-Adresse inklusive, wie bei jedem Aufruf).

| Funktion | Empfänger | Was geht hin | Vorgeschlagene Rechtsgrundlage |
|---|---|---|---|
| Jobsuche | Bundesagentur für Arbeit (`rest.arbeitsagentur.de`), Indeed (`apis.indeed.com`), optional LinkedIn, StepStone, XING | Suchbegriff, Ort, Umkreis | Vertragserfüllung (Art. 6 Abs. 1 lit. b), deine Anfrage |
| Arbeitgeber-Suche im Web (aktuell vorbelegt, siehe Offene Punkte) | DuckDuckGo, Brave, Karriereseiten der Arbeitgeber, Greenhouse, Lever, Ashby | Suchbegriff, Ort | Vertragserfüllung / berechtigtes Interesse |
| Wegstrecke | BRouter (`brouter.de`, Kartenkacheln von GitHub), GeoNames | Kachel- bzw. Datei-Anforderung, daraus ergibt sich grob die Region | Vertragserfüllung (deine Funktion); Einwilligung prüfen |
| E-Mail (optional) | dein Mailanbieter (z. B. Gmail, WEB.DE, T-Online) | Anmeldung per IMAP, nur Lesen | deine Einrichtung, Vertragserfüllung |
| Kalender (optional) | dein Kalenderanbieter (Link oder Datei) | Abruf deines Kalenders, nur Lesen | deine Einrichtung, Vertragserfüllung |
| Programm-Updates | GitHub (`api.github.com`, `github.com`) | Versionsabfrage, Download des Pakets | berechtigtes Interesse (Sicherheit) / Einwilligung prüfen |
| Modell-Download | Hugging Face (`huggingface.co`) | Download der Modelldatei | Vertragserfüllung (deine Auswahl) |
| KI-Chat im Browser (optional) | ChatGPT, Claude, Gemini u. a., über deinen Browser | **Nur was du selbst einfügst** | deine Entscheidung |

Mit den genannten Diensten haben wir keinen Vertrag über die Verarbeitung deiner Daten, weil du sie selbst anfragst. Für
deren Verarbeitung gelten deren Datenschutzhinweise.

## 4. Lizenz und Zahlung (ab Verkauf)

Beim Kauf ist **Paddle** Händler (Merchant of Record) und verantwortlich für Zahlung, Rechnung und Steuer. Karrierekrake
bekommt von Paddle eine Kunden- und Bestell-ID und deine Rechnungs-E-Mail, aber **keine Kartendaten**.
Auf deinem Gerät liegt nur eine signierte Lizenzdatei (pseudonyme ID, Ablauf, Funktionen).
**[Vertrag mit Paddle und Rollen (eigenständig Verantwortlicher oder Auftragsverarbeitung) von der Verantwortlichen
Person abschließen und hier eintragen.]**

## 5. Support

Schreibst du uns, verarbeiten wir deine Nachricht, deine E-Mail-Adresse und was du uns freiwillig schickst, um zu
antworten (Art. 6 Abs. 1 lit. b oder f). Bitte schick uns keine Lebensläufe oder Zugangsdaten.
Die App sendet von sich aus keine Fehlerberichte; was in den Protokollen steht, entscheidest du beim Weitergeben.

## 6. Wie lange wir Daten aufbewahren (Vorschlag)

| Daten | Frist |
|---|---|
| Support-Mails | 6 Monate nach Abschluss der Anfrage |
| Lizenz- und Bestelldaten (Paddle-IDs) | Laufzeit des Vertrags plus 3 Jahre (Verjährung); Rechnungsunterlagen beim Händler nach dessen gesetzlicher Frist |
| Daten auf deinem Gerät | bis du sie löschst (Einstellungen → Datenschutz) |

## 7. Deine Rechte

Auskunft, Berichtigung, Löschung, Einschränkung, Datenübertragbarkeit und Widerspruch (Art. 15–21 DSGVO) sowie
Beschwerde bei einer Aufsichtsbehörde. **Für die Daten auf deinem Gerät** kannst du alles selbst tun:
Einstellungen → Datenschutz bietet Export und gezieltes oder vollständiges Löschen, auch von Mail- und Kalenderdaten
und Zugangsdaten. Für die bei uns gespeicherten Daten schreib an **[Datenschutz-Adresse]**.

---

## Offene Punkte für den Verantwortlichen (vor Veröffentlichung)

1. **Name, Anschrift, Kontakt** und die Frage, ob ein Datenschutzbeauftragter nötig ist.
2. **Rechtsgrundlagen und Fristen** durch eine fachkundige Person bestätigen lassen.
3. **Automatische Netzaufrufe prüfen:** Kartenkacheln (`brouter.de`) und Update-Abfrage (`api.github.com`) laufen ohne
   ausdrückliche Einwilligung (`docs/privacy/NETWORK_TARGETS_PR144.json`, Status UNSICHER). Entscheiden: entweder
   Einwilligung beim ersten Start abfragen oder Rechtsgrundlage (berechtigtes Interesse) dokumentieren.
4. **Websuche nach Arbeitgebern** ist im Code vorbelegt aktiv, obwohl sie als „optional“ gilt
   (`core/config.py`, siehe `data-inventory.md`). Entscheiden: standardmäßig aus oder ausdrücklich nennen.
5. **Portal-Bedingungen:** Die Nutzungsbedingungen von Indeed, LinkedIn, StepStone und XING zu automatisierten Abfragen
   sind rechtlich nicht geprüft.
6. **Paddle:** Vertrag und Rolle klären (siehe 4).
7. Nach der Freigabe als Text in die App (Einstellungen → Datenschutz) und auf die Website übernehmen.
