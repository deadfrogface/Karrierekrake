# Personaler-Abnahme — Checkliste Blind Review

Stand der Prüfanweisung: 2026-09-24.  
Geltungsbereich: drei getrennte Lieferstücke — **CV-Extrakt**, **Matching-Ausgabe**, **Anschreiben**.

Diese Checkliste ist die Abnahme durch eine Personalerin oder einen Personaler. Ein Modell-Score, `ready_as_is`, F1 oder ein automatisches `PASS` ersetzt das Urteil nicht.

## 1. Getrennte Urteile

Jedes Lieferstück bekommt ein eigenes Urteil. Ein sauberes Anschreiben heilt einen fehlerhaften Extrakt nicht. Ein passender Score heilt ein Anschreiben mit einer unbelegten Behauptung nicht.

| Urteil | Bedeutung |
|---|---|
| **Interview-ready** | Alle Pflichtpunkte dieser Kategorie sind erfüllt. Versand an eine echte Stelle ist aus Personaler-Sicht vertretbar, beim Anschreiben erst nach ausdrücklicher Nutzerfreigabe der Endfassung. |
| **Papierkorb** | Mindestens ein harter Fehler aus der Papierkorb-Liste. Nicht automatisch versenden. |
| **Blockiert** | Die Prüfung ist nicht möglich, weil die Probe, das Gold oder der lesbare Output fehlt. Blockiert ist kein stilles Bestehen. |

Unbeaufsichtigter Versand ist erst zulässig, wenn **alle drei** Kategorien auf dem vereinbarten Abnahme-Set **Interview-ready** sind und kein Blocker offen ist.

## 2. Was die prüfende Person sieht

Für jedes Sample liegen nebeneinander:

1. die Quelle (Lebenslauf bzw. Stellenanzeige),
2. der tatsächliche Output (Extrakt, Matching, Anschreiben),
3. das bestätigte Profil, gegen das konkrete Personenbehauptungen geprüft werden.

Fehlt eines der drei, lautet das Urteil für dieses Sample **Blockiert**. Fehlende Inhalte werden nicht ergänzt und nicht aus dem Gedächtnis nachgeschrieben.

Bekannte CV-Gold-Namen, sofern sie im Stand vorhanden sind: `SMOKE_DE_EN_10`, `MINI_HOLDOUT_30`, `NV3_001`–`NV3_050`.  
Ein Personaler-Gold für Anschreiben ist in dieser Abnahme **nicht spezifiziert**. Ein Trainings- oder Modell-Gold zählt erst nach gesonderter Benennung.

## 3. CV-Extrakt

### Interview-ready

- Name und Kontakt (E-Mail, Telefon, ladungsfähige Anschrift, soweit die Quelle sie enthält) stimmen.
- Alle stellenrelevanten Beschäftigungen sind da, mit korrektem Zeitraum.
- Abschlüsse und Knock-out-Qualifikationen (Ausbildung, Lizenz, Pflichtzertifikat, Pflichtsoftware) sind vorhanden und durch die Quelle belegt oder vom Nutzer bestätigt.
- Erfundene Fakten: keine. Eine Überschrift, ein Sprachlevel oder ein Werkzeug, das als Zertifikat, Führerschein oder Arbeitgeber ausgegeben wird, ist ein erfundenes Faktum.

### Papierkorb

- Eine relevante Qualifikation fehlt oder ist falsch.
- Eine beendete Beschäftigung ist als aktuell markiert.
- Eine unbelegte Behauptung kann in Matching oder Anschreiben weiterlaufen.

Ein Extrakt mit erfundener Lizenz, erfundenem Zertifikat oder falschem Kontakt ist nicht interview-ready. Fehlende Samples oder nur Zähler ohne Stellen, Zeiträume und Abschlüsse sind **Blockiert**.

### Muttersprache ist ein eigenes Sollfeld (`SMOKE_DE_EN_10`, Personaler 19.10.2026)

- C2 allein ist keine Muttersprache. Muttersprache gilt nur, wo die Quelle es ausdrücklich sagt (Muttersprache / native / mother tongue).
- `tests/fixtures/cv_corpus/expected_results.json` führt je CV `native_languages` (leere Liste = keine Muttersprache). Die Stufen in `languages` bleiben, wie sie sind (DE_01: `["Deutsch", "C2"]` plus `native_languages: ["Deutsch"]`).
- `CV_Parser_Sollwerte_Vollstaendig.txt` bleibt unverändert; dort steht die Muttersprache schon in den `SPRACHE_n`-Zeilen (`native`, `Originalwert: …` bzw. „zusätzlich ausdrücklich: Muttersprache“). Beide Sollquellen müssen übereinstimmen (`tests/test_cv_gold_native.py`).
- Abweichung im Abschnitt Sprachen: ein Extrakt, der die Muttersprache verliert (`C2`, leer, „near-native“, „muttersprachliches Niveau“), oder eine Muttersprache für eine andere Sprache behauptet. „Muttersprache“ wird so gelesen, wie der Anschreiben-Guard ein bestätigtes Profil liest (`core/cover_guard._entry_level_class`).

## 4. Matching-Ausgabe

### Interview-ready

- Stelle und Firma stimmen mit der Anzeige überein.
- Jede Anforderung ist entweder aus dem bestätigten Profil belegt oder ausdrücklich als Lücke genannt.
- Treffergründe widersprechen den Lücken nicht.
- Keine erfundene Qualifikation erscheint als erfüllte Anforderung.

### Papierkorb

- Falsche Stelle oder falsche Firma.
- Eine Anforderung ist als erfüllt markiert, obwohl sie im bestätigten Profil fehlt.
- Score und Begründung widersprechen sich.
- Platzhalter (`Stelle 0`, `skill-0`) stehen anstelle einer belegten Begründung.

Ohne anzeigenbezogene Anforderungsliste und ohne Profilbezug ist das Sample **Blockiert**. Ein Schema-Fixture ohne diesen Bezug ist kein Abnahme-Gold.

## 5. Anschreiben

### Interview-ready

- Stelle und Firma stimmen.
- Jede konkrete Personenbehauptung (Arbeitgeber, Rolle, Abschluss, Zertifikat, Zeitraum, Kennzahl, Werkzeug) ist durch das bestätigte Profil gedeckt.
- Anforderungen aus der Anzeige sind sachlich wiedergegeben.
- Erfundene Abschlüsse, Erfahrung, Daten oder Erfolge: keine.
- Die Endfassung ist vom Nutzer freigegeben.

### Papierkorb

- Falsche Anrede, falsche Firma oder falsche Stelle.
- Schon **eine** konkrete Personenbehauptung ohne Deckung im bestätigten Profil.

Floskeln ohne Fakt (`ich freue mich`) sind kein Treffer und kein Fehler. `ready_as_is` und ein Safety-`PASS` des Modells sind keine Nutzerfreigabe.

Ein Modell-Gold, das nie als Personaler-Gold benannt wurde, wird als vorhandenes Sample gelesen und im Bericht so gekennzeichnet. Es wird nicht nachträglich zum Abnahme-Gold erklärt.

## 6. Ablauf einer Blind-Runde

1. Gold-Namen und Dateipfade notieren. Fehlende Namen als Blocker führen.
2. Extrakt, Matching und Anschreiben in getrennten Tabellen urteilen.
3. Pro Papierkorb-Fall Quelle, Output und die eine entscheidende Abweichung zitieren.
4. Pro Blocker schreiben, welche Datei fehlt und warum daraus kein Interview-Urteil wird.
5. Gesamturteil je Kategorie und die Folge für unbeaufsichtigten Versand festhalten.

## 7. Abnahmeprotokoll (leer)

| Kategorie | Sample-Satz | Urteil | Entscheidende Beobachtung | Versand frei |
|---|---|---|---|---|
| CV-Extrakt | | | | |
| Matching | | | | |
| Anschreiben | | | | |

## 8. T01.10 – Antwortentwürfe auf Recruiter-Mails und Kalender (ICS)

Stand der Prüfanweisung: 2026-10-18.  
Geltungsbereich: zwei getrennte Lieferstücke — **Antwortentwurf** auf eine eingehende Recruiter-Mail und **Kalendereintrag (ICS)** zu einem zugesagten Termin.

Diese Kriterien sind **vor** dem Implementierungslauf zu T01.10 festgelegt. Sie werden nach dem Lauf nicht an den Output angepasst. Das Gold (`expected.json`) schreibt die Personalerin oder der Personaler, nicht die implementierende Seite. Ein Gold, das die implementierende Seite geschrieben oder nachträglich geändert hat, ist kein Abnahme-Gold; das Sample lautet dann **Blockiert**.

Jeder Entwurf und jede ICS-Datei bekommt ein eigenes Urteil **Interview-ready**, **Papierkorb** oder **Blockiert** (Bedeutung wie in Abschnitt 1). Grüne Tests allein sind keine HR-Abnahme. Verwendet werden ausschließlich synthetische Daten: keine echten Postfächer, keine echten Kalender, keine echten Personen.

### 8.1 Antwortentwurf

- [ ] **Anrede:** Name und Anrede stehen wörtlich so im Entwurf, wie sie in der Recruiter-Mail stehen. „Frau“ oder „Herr“ nur, wenn Mail oder Signatur es ausdrücklich nennt; sonst „Guten Tag Vorname Nachname“. Das Geschlecht wird nie aus dem Vornamen abgeleitet. Falsche Anrede = **Papierkorb**.
- [ ] **Zuordnung:** Firma, Stelle und Referenznummer stimmen mit dem zugeordneten Fall. Falsche Zuordnung = **Papierkorb**.
- [ ] **Termin:** Zugesagt wird nur ein Slot, den die Einladung anbietet und der laut Kalender frei ist. Datum, Uhrzeit, Zeitzone und Ort bzw. Link werden unverändert übernommen. Sind alle angebotenen Slots belegt, ist ein Gegenvorschlag klar als solcher markiert und nie als Zusage formuliert.
- [ ] **Keine unbelegte Aussage:** Verfügbarkeit, Kündigungsfrist, Gehalt und Unterlagen nur, wenn das bestätigte Profil sie belegt. Ein genannter Anhang, der nicht existiert = **Papierkorb**.
- [ ] **Absage:** höchstens ein kurzer Dank, keine Diskussion.
- [ ] **Mehrdeutige Mail:** kein verbindlicher Entwurf, nur ein Hinweis an die Nutzerin.
- [ ] **Ausgeschlossener Absender:** kein Entwurf.
- [ ] **Fallstatus:** Eine eingehende Mail ändert den Fallstatus nicht automatisch (`auto_status=False`, vom Teamlead bestätigt).

### 8.2 Kalendereintrag (ICS)

- [ ] `SUMMARY` enthält Firma und Stelle.
- [ ] `DTSTART` und `DTEND` entsprechen exakt dem zugesagten Slot, mit `TZID=Europe/Berlin`.
- [ ] `LOCATION` steht so wie in der Einladung.
- [ ] Keine erfundenen Teilnehmer.
- [ ] Stabile `UID`; ein zweiter Lauf erzeugt kein Duplikat.
- [ ] Ein abgesagter Termin wird nicht neu angelegt.

### 8.3 Für Entwurf und ICS gemeinsam

- [ ] Standard ist **„Versand frei: nein“** und **„Kalender schreiben frei: nein“**.
- [ ] Versand und Kalender-Schreiben erst nach ausdrücklicher Nutzerfreigabe.
- [ ] Im Test nur In-Memory-Transport, **0 Netzversuche**.

### 8.4 Gold je Mail (`expected.json`)

Je Mail hält das Personaler-Gold fest:

| Feld | Inhalt |
|---|---|
| Kategorie | z. B. Einladung, Absage, Rückfrage, mehrdeutig, ausgeschlossener Absender |
| Fall | zugeordneter Fall (Firma, Stelle, Referenznummer) |
| Erlaubter Slot | der zulässige Slot oder ausdrücklich keiner |
| Erwartete Anrede | wörtlich |
| Entwurf erlaubt | ja / nein |
| Versand frei | nein |

Fehlt für eine Mail der Gold-Eintrag, lautet das Urteil für diese Mail **Blockiert**.

### 8.5 Abnahmeprotokoll T01.10 (leer)

| Mail / Sample | Lieferstück | Urteil | Entscheidende Beobachtung | Versand frei | Kalender schreiben frei |
|---|---|---|---|---|---|
| | Antwortentwurf | | | nein | – |
| | ICS | | | – | nein |
