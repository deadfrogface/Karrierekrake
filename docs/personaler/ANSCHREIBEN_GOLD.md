# Personaler-Gold — Anschreiben

Stand: 2026-09-25.  
Geltungsbereich: Abnahmedaten für Anschreiben. Dokumentation und synthetische Fälle, kein Anwendungscode.

Dieses Gold ist die Personaler-Abnahme für Anschreiben. `docs/personaler/ABNAHME_CHECKLISTE.md` und `docs/personaler/BLIND_REVIEW_BERICHT.md` hatten dafür noch keinen benannten Satz. CV-Extrakt und Matching bleiben eigene Urteile. Ein sauberer Brief heilt keinen fehlerhaften Extrakt.

Personen, Firmen, Straßen, Telefonnummern und Mailadressen sind erfunden. Mails liegen nur auf `example.com`. Es sind keine realen Personen.

## 1. Zweck

Die Fälle sind feste Eingaben mit einem bekannten Soll-Ausgang. Der Anschreiben-PR prüft seinen Generator dagegen. Dieser Stand erzeugt keine Briefe und ändert `core/cover_letter.py` nicht.

Zwei Sätze aus einem Brief auf die leere Anzeige „Dispatcher bei HafenLogistik“ sind in jedem Ausgang verboten:

- `Gern bringe ich meine bisherigen beruflichen Erfahrungen in Ihr Team ein.`
- `Zu meinen relevanten Kenntnissen zählen insbesondere: meine bisherigen beruflichen Erfahrungen.`

Sie stehen in `core/cover_letter.py` als Füllung, wenn die Anzeige keinen Treffer auf Station oder Skill hergibt. Erscheinen sie in einem Brief, ist das Papierkorb, auch wenn sie die einzige Begründung sind. Der Soll-Ausgang der leeren Anzeige selbst ist `job_incomplete`: kein Brief.

## 2. Fünf Kriterien für `interview`

Ein Brief ist nur dann `interview`, wenn alle fünf Punkte gelten.

1. Stellentitel, Firma und die Ansprechperson, sofern die Anzeige eine nennt, stimmen.
2. Mindestens zwei konkrete Sätze verbinden eine Anforderung der Anzeige mit einer Station oder einem Skill, der im Profil steht.
3. Keine Aussage ohne Deckung in Anzeige oder Profil: kein Jahr, kein Werkzeug, keine Dauer, kein Zertifikat und kein Arbeitgeber, der nicht im Profil steht.
4. Keine Platzhalter- oder Allgemeinformel, die in jedem Brief als einzige Begründung stehen könnte. Die beiden Sätze aus Abschnitt 1 gehören dazu.
5. Das Profil selbst ist korrekt. Eine Ausbildungszeile, die als Berufserfahrung gezählt wird, genügt für Papierkorb.

Eine unbelegte konkrete Behauptung, eine falsche Anrede oder Firma, oder eine leere Schablonenfüllung (`Ihr Unternehmen`, `die ausgeschriebene Position`, `[Ihr Name]`) ist Papierkorb.

## 3. Vokabular

| Code | Bedeutung | Brief |
|---|---|---|
| `interview` | Alle fünf Kriterien sind erfüllt. | ja |
| `papierkorb` | Harter Fehler nach Abschnitt 2. Kein Versand. | kein Interview-Brief |
| `job_incomplete` | Die Stellenbeschreibung ist leer. | nein |
| `no_evidence` | Keine belegte Station und kein belegter Skill treffen die Anzeige. | nein |
| `blocked_demo` | `source` ist `demo`. | nein |

`blocked_demo` ist keine fehlende Probe im Sinn von „Blockiert“ in der Checkliste. Es ist die Sperre für Demo-Stellen.

Vereinbartes Verhalten, das die Fälle festschreiben:

- Leere Beschreibung, auch nach Trim nur Leerzeichen: `job_incomplete`, kein Brief.
- Beschreibung vorhanden, aber keine belegte Station und kein belegter Skill: `no_evidence`, kein Brief.
- `source == demo` bekommt nie einen Brief, auch wenn der Inhalt sonst tragen würde.
- `source == fixture` darf einen Brief bekommen, wenn die fünf Kriterien erfüllt sind.
- Eingefügte Beschreibungen laufen durch dieselbe Bereinigung und dasselbe Gate wie abgegriffene Anzeigen. HTML-Reste gehören nicht in den Brief. Ist der Text nach der Bereinigung leer, gilt `job_incomplete`.

`papierkorb` ist das Urteil über den Inhalt. Ein erzeugter Text mit einem harten Fehler ist Papierkorb. Ein Interview-Urteil auf diesen Eingaben ist falsch.

## 4. Form der Fälle

Eine Datei pro Fall unter `tests/fixtures/anschreiben_gold/`. Der Dateiname ist die `id`.

| Feld | Inhalt |
|---|---|
| `schema_version` | `1.0` |
| `id` | Stabile Fall-Id |
| `tags` | Genau ein Szenario aus der Tabelle in Abschnitt 6 |
| `profile` | Synthetisches Profil, siehe unten |
| `job` | Synthetische Anzeige in der Form von `Job` in `core/models.py` |
| `expected_outcome` | Ein Code aus Abschnitt 3 |
| `must_mention` | Teilstrings, die ein Interview-Brief enthalten muss. Sonst leer. |
| `must_not_contain` | Teilstrings, die in keinem Brief stehen dürfen. Enthält immer die beiden Platzhalter aus Abschnitt 1. |
| `rationale` | Kurze Begründung des Soll-Ausgangs |

`must_mention` und `must_not_contain` gelten für den Brieftext. Wörter, die nur in der Anzeige stehen (etwa ein geforderter ADR-Schein), dürfen im Brief fehlen und müssen fehlen, wenn sie im Profil nicht belegt sind.

Bei `interview` nennt `must_mention` mindestens zwei Fakten aus dem Profil (Station, Skill, Software) und dazu Titel, Firma und, wenn vorhanden, die Ansprechperson. Die Anforderungen sitzen in der Beschreibung in der unteren Hälfte, nach Betrieb und Angebot.

### Profil

Minimales Profil, das der Anschreiben-Pfad liest. Suche, Filter, Settings und `search_intent` fehlen, weil `render_cover_letter()` sie nicht verwendet.

| Gold | Karte in der Oberfläche | Typ |
|---|---|---|
| `profile.application` | Name und Kontakt | `ApplicationProfile` (`first_name`, `last_name`, Mail, Anschrift) |
| `profile.qualifications.work_experience` | Berufserfahrung | `ExperienceEntry` |
| `profile.qualifications.education` | Ausbildung | `EducationEntry` |
| `profile.qualifications.skills` | Skills | `SourcedText` mit `value` und `source` |
| `profile.qualifications.software` | Software | `SourcedText` |
| `profile.qualifications.languages` | Sprachen | `LanguageEntry` |
| `profile.qualifications.certificates` | Zertifikate / Weiterbildungen | `CertificateEntry` |
| `profile.qualifications.driving_license` | Führerschein | `SourcedText` |

### Stelle

`job` nutzt Felder von `Job`: `id`, `source`, `source_job_id`, `title`, `company`, `description`, `city`, `postal_code`, `country_code`, `remote_type`, `employment_type`, `url`, `status`. Die Ansprechperson steht im Beschreibungstext (`Ansprechpartnerin`), nicht in einem eigenen Job-Feld.

## 5. Umgang mit den Fällen

1. Die JSON-Datei lesen. Profil und Stelle nicht anreichern und nicht aus anderen Fällen mischen.
2. `profile.qualifications` und `profile.application` in die Strukturen legen, die der Anschreiben-Pfad erwartet. `job` als `Job` lesen.
3. Den Generator des Anschreiben-PR ausführen. Diesen Lauf macht der Gold-Stand nicht.
4. Bei `interview`: es entsteht ein Brief. Jeder Eintrag aus `must_mention` kommt darin vor, keiner aus `must_not_contain`. Die fünf Kriterien gelten zusätzlich zur Teilstring-Liste.
5. Bei `job_incomplete`, `no_evidence` und `blocked_demo`: kein Brief. Der Grundcode ist `expected_outcome`.
6. Bei `papierkorb`: das Ergebnis ist kein `interview`. Entsteht Text, ist er Papierkorb. Die Einträge in `must_not_contain` sind die harten Fehler, zusätzlich zu den beiden Platzhaltern.

`tests/test_anschreiben_gold.py` prüft nur diese Dateien (Schlüssel, Vokabular, Platzhalter, mindestens zwei `must_mention` bei `interview`). Kein Modell, keine Oberfläche. Den Generator-Vergleich gegen das Gold legt der Anschreiben-PR an.

## 6. Fälle

| Fall | Ausgang | Kurzbegründung |
|---|---|---|
| `cl-01-dispatch-hafenlogistik` | `interview` | Disponent bei der Nordkai Spedition, Tourenplanung und SAP TM treffen die Anzeige der HafenLogistik GmbH. |
| `cl-02-dispatch-empty-description` | `job_incomplete` | Dispatcher bei HafenLogistik, Beschreibung leer; die beiden Platzhalter wären Papierkorb. |
| `cl-03-zero-overlap-konditor` | `no_evidence` | Konditor-Anzeige, keine Station und kein Skill aus dem Profil. |
| `cl-04-source-demo` | `blocked_demo` | Inhaltlich tragfähig, `source` ist `demo`, deshalb kein Brief. |
| `cl-05-source-fixture` | `interview` | Tragfähiger Disponenten-Treffer, `source` ist `fixture`, Brief erlaubt. |
| `cl-06-education-as-experience` | `papierkorb` | Die einzige Station ist eine Ausbildung und liegt unter Berufserfahrung. |
| `cl-07-adr-schein-trap` | `interview` | ADR-Schein und Gefahrgut stehen in der Anzeige, nicht im Profil, und dürfen nicht behauptet werden. |
| `cl-08-company-missing` | `papierkorb` | Firmenfeld leer, im Text nur der Platzhalter Firma 0. |
| `cl-09-named-contact` | `interview` | Die Anzeige nennt Frau Lotte Quendel; der Brief muss sie ansprechen. |
| `cl-10-english-ad` | `interview` | Englische Anzeige; dispatcher, route planning und SAP TM sind über das Profil belegt. |
| `cl-11-long-ad-requirements-end` | `interview` | Lange Anzeige; Disponent, Tourenplanung und SAP TM stehen erst am Ende. |
| `cl-12-html-remnants` | `interview` | Eingefügte Beschreibung mit HTML; nach der Bereinigung ein Treffer, ohne Markup im Brief. |

Zählung: `interview` 7, `papierkorb` 2, `job_incomplete` 1, `no_evidence` 1, `blocked_demo` 1. Zusammen 12 Fälle.

## 7. Nicht Gegenstand dieses Stands

Keine Änderung an Parser, Scrapern, Qt-Oberfläche, `i18n.py`, CI oder `core/`. Kein Aufruf von `render_cover_letter()` und kein gespeicherter Musterbrief. `save_cover_letter()` bleibt unberührt.
