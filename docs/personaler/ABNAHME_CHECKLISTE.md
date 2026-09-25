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
