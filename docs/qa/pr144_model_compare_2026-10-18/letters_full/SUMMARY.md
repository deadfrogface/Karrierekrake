# Anschreiben-QA letters_full_2026-10-18 – SUMMARY (nur Fakten)

## Lauf

- `RUN_START 2026-10-18T18:38:49+02:00 home=/tmp/kk-letters-home.m6f9 commit=ffa483c34bfc212a86c40ff9392960ed74195ecf`
- `MODEL_START q4_k_m 2026-10-18T18:38:49+02:00 sha=00fe7986ff5f6b46`
- `MODEL_END q4_k_m 2026-10-18T19:25:32+02:00`
- `MODEL_START q2_k_xl_4b_gsq 2026-10-18T19:25:32+02:00 sha=b7d9ec51fb4d726d`
- `MODEL_END q2_k_xl_4b_gsq 2026-10-18T20:23:36+02:00`
- `RUN_END 2026-10-18T20:23:36+02:00`
- Driver: `tools/run_all.sh` (pid 359289), nach RUN_END beendet; nicht verändert. Writer: `core.cover_quality.rewrite_cover_letter`, 2 Versuche je Fall, T=0.2. 16 Gold-Fälle, alle `expected_outcome=interview`.
- Peak RSS = `peak_tree_rss_mib` aus RUN.log (Prozessbaum, MiB). wall_s aus RUN.log (Watchdog).
- Kein vorheriges SUMMARY.md/SHA256SUMS vorgefunden; FACTS.json (Stand 19:25, nur q4_k_m) wurde mit `tools/facts.py` über beide Modelle neu erzeugt.

## Zählung Outcome

- q4_k_m: letter_returned=1, review_required=15 (n=16)
- q2_k_xl_4b_gsq: letter_returned=2, review_required=14 (n=16)

## Tabelle je Fall

Spalten: Firma/Stelle = Zielfirma bzw. Stellentitel wörtlich im Text (je Versuch, FINAL = zurückgegebener Brief). Anrede = erste Zeile vs. Erwartung laut Gold (`must_mention`). Erfundene Nachweise und weitere unbelegte Aussagen: manuelle Prüfung gegen das synthetische Profil, Zitate wörtlich.

### q4_k_m

| Fall | Outcome | Guard-Flags (letzter Versuch) | wall_s | Peak RSS MiB | Firma / Stelle (FINAL / att0 / att1) | Anrede (Ist → Soll) | Erfundene Zertifikate/Lizenzen/Arbeitgeber/Abschlüsse | Weitere unbelegte Aussagen |
|---|---|---|---|---|---|---|---|---|
| cl-01-dispatch-hafenlogistik | review_required | unsupported_personal_claim | 211 | 4566 | a0: ja/nein; a1: ja/nein | Sehr geehrte Damen und Herren, → Sehr geehrte Damen und Herren, (keine Ansprechperson in Anzeige) (korrekt) | keine | att0: "den Umgang mit SAP TM im Tagesgeschäft sicher beherrscht" (Niveau nicht im Profil); att1: "Planung von Zustellgebieten, die wöchentlich im Team besprochen werden" (Anzeigeninhalt als eigene Tätigkeit) |
| cl-05-source-fixture | review_required | unsupported_personal_claim | 196 | 4559 | a0: ja/nein; a1: ja/nein | Sehr geehrte Damen und Herren, → Sehr geehrte Damen und Herren, (keine Ansprechperson in Anzeige) (korrekt) | keine | att0: "als fiktiver Familienbetrieb" (Anzeigentext übernommen); att1: "habe diese Aufgabe seit 2019 bis 2024 erfolgreich umgesetzt", "die Schichtkoordination zwischen Halle und Büro geleistet" (Profil: "Schichtkoordination im Lager") |
| cl-07-adr-schein-trap | review_required | unsupported_personal_claim | 205 | 4558 | a0: ja/ja; a1: ja/nein | Sehr geehrte Damen und Herren, → Sehr geehrte Damen und Herren, (keine Ansprechperson in Anzeige) (korrekt) | att0: "Ich verfüge über einen gültigen ADR-Schein und bin bereit, Gefahrgut-Sendungen selbst zu disponieren" (ADR-Schein NICHT im Profil); att1: "sofern mir der ADR-Schein vorliegt, den ich nur nennen werde, wenn ich ihn wirklich besitze" (bedingt, keine Besitzbehauptung; must_not_contain-Treffer) | att0: "seit 2019" (Station endete 2024-08), "die Daten in Echtzeit zu erfassen" |
| cl-09-named-contact | review_required | unsupported_personal_claim | 188 | 4561 | a0: ja/nein; a1: ja/nein | Sehr geehrte Damen und Herren, → Sehr geehrte Frau Quendel, (FALSCH) | keine | att0: "seit 2019" (Station endete 2024-08), "Ich kann sicherstellen, dass Zusagen gegenüber Verladern eingehalten werden"; att1: "Kommunikation mit Transportunternehmen" |
| cl-10-english-ad | letter_returned | – | 198 | 4562 | F: ja/ja; a0: ja/ja; a1: ja/ja | Sehr geehrte Damen und Herren, → Sehr geehrte Damen und Herren, (keine Ansprechperson in Anzeige) (korrekt) | keine | FINAL(=att1): "Meine Muttersprache ist Deutsch" (Profil: Deutsch C2, keine Muttersprachangabe); "SAP TM ..., um Bestände zu kontrollieren" (Bestandskontrolle gehört zur Station Fachlagerist, SAP TM ist keiner Station zugeordnet); "da beide Unternehmen auf effiziente Logistikabläufe im Hafenbereich setzen" (UNSICHER, Profil nennt nur Ort Musterhafen); Defekt "Die Kombination aus SAP TM und SAP TM"; Brief deutsch bei englischer Anzeige |
| cl-11-long-ad-requirements-end | review_required | unsupported_personal_claim | 214 | 4584 | a0: ja/nein; a1: ja/nein | Sehr geehrte Damen und Herren, → Sehr geehrte Damen und Herren, (keine Ansprechperson in Anzeige) (korrekt) | keine | att1: "habe ich in meinem Team umgesetzt" (keine Teamleitung im Profil); SAP TM fehlt in att1 |
| cl-12-html-remnants | review_required | unsupported_personal_claim | 178 | 4561 | a0: ja/ja; a1: ja/ja | Sehr geehrte Damen und Herren, → Sehr geehrte Damen und Herren, (keine Ansprechperson in Anzeige) (korrekt) | keine | att0: "praktische Erfahrung in der Schichtkoordination zwischen Halle und Büro gesammelt" (Profil: "im Lager"); kein Markup in Entwürfen |
| cl-14-two-stations | review_required | unsupported_personal_claim | 157 | 4537 | a0: ja/ja; a1: ja/nein | Sehr geehrte Damen und Herren, → Sehr geehrte Damen und Herren, (keine Ansprechperson in Anzeige) (korrekt) | keine | Profil ohne Tätigkeiten; att0: "mit der Steuerung von Stückgut", "stationären Lagerabwicklung"; att1: "Lagerbestände präzise zu erfassen und die Materialflussprozesse zu optimieren" |
| cl-15-station-and-skill | review_required | unsupported_personal_claim | 138 | 4537 | a0: ja/nein; a1: ja/nein | Sehr geehrte Damen und Herren, → Sehr geehrte Damen und Herren, (keine Ansprechperson in Anzeige) (korrekt) | keine | att1: "Koordination von Transportabläufen und der Optimierung von Routen" (Station ohne Tätigkeiten) |
| cl-18-sap-business-one-covers-sap | review_required | missing_profile_references, unsupported_personal_claim | 152 | 4537 | a0: ja/ja; a1: ja/ja | Sehr geehrte Damen und Herren, → Sehr geehrte Damen und Herren, (keine Ansprechperson in Anzeige) (korrekt) | keine | att0/att1: "In meiner Rolle als Rechnungsprüfung" (must_not_contain); att1: "Erfassung und Prüfung von Belegen" (Profil: nur "Belege erfassen"); "Belege erfassen" wörtlich fehlt (missing_profile_references); SAP-Business-One-Falle: SAP Business One korrekt genannt, keine weitere SAP-Variante behauptet |
| cl-20-nordmole-dispatcher | review_required | unsupported_personal_claim | 185 | 4565 | a0: ja/nein; a1: ja/nein | Sehr geehrte Damen und Herren, → Guten Tag Robin Beispiel, (FALSCH) | att0: "Ich verfüge über die erforderliche Ausbildung in Spedition und Logistik" (keine Ausbildung im Profil) | att1: "in den letzten fünf Jahren" (Station 2019-03 bis 2024-08), "Sendungsdaten zu analysieren und Abstimmungen zwischen Disposition und Wareneingang durchzuführen", "Abweichungen im Lauf des Tages nachzusteuern und Ersatzfahrzeuge einzusetzen" (Anzeigenaufgaben als eigene Erfahrung) |
| cl-24-two-requirements-in-title | review_required | unsupported_personal_claim | 136 | 4534 | a0: ja/ja; a1: ja/nein | Sehr geehrte Damen und Herren, → Sehr geehrte Damen und Herren, (keine Ansprechperson in Anzeige) (korrekt) | keine | Profil ohne Tätigkeiten; att0: "mit der Logistik und dem Warenfluss beschäftigt"; att1: "komplexe Lagerprozesse effizient zu steuern" |
| cl-27-gender-title | review_required | unsupported_personal_claim | 141 | 4538 | a0: ja/ja; a1: ja/ja | Sehr geehrte Damen und Herren, → Sehr geehrte Damen und Herren, (keine Ansprechperson in Anzeige) (korrekt) | keine | att0: "Excel intensiv genutzt, um Datenanalysen durchzuführen und Berichte zu erstellen", "operativen Verwaltung und Prozessoptimierung"; att1: "Excel systematisch weiterentwickelt" |
| cl-28-titled-contact | review_required | unsupported_personal_claim | 178 | 4535 | a0: ja/ja; a1: ja/nein | Sehr geehrte Damen und Herren, → Sehr geehrte Frau Dr. Quendel, (FALSCH) | keine | att1: "die Tourenplanung für Stückgut geleitet" |
| cl-29-two-contacts | review_required | unsupported_personal_claim | 165 | 4534 | a0: ja/nein; a1: ja/nein | Sehr geehrte Damen und Herren, → Sehr geehrte Damen und Herren, (korrekt) | keine | att0: "arbeite täglich mit SAP TM" (Präsens; Station beendet); att1: "die Durchlaufzeiten optimieren" |
| cl-30-html-contact | review_required | unsupported_personal_claim | 157 | 4535 | a0: ja/ja; a1: ja/nein | Sehr geehrte Damen und Herren, → Sehr geehrte Frau Quendel, (FALSCH) | keine | att0: "die Auslastung der Fahrzeuge zu optimieren" |

### q2_k_xl_4b_gsq

| Fall | Outcome | Guard-Flags (letzter Versuch) | wall_s | Peak RSS MiB | Firma / Stelle (FINAL / att0 / att1) | Anrede (Ist → Soll) | Erfundene Zertifikate/Lizenzen/Arbeitgeber/Abschlüsse | Weitere unbelegte Aussagen |
|---|---|---|---|---|---|---|---|---|
| cl-01-dispatch-hafenlogistik | review_required | unsupported_personal_claim | 243 | 2508 | a0: NEIN/nein; a1: ja/ja | Sehr geehrte Damen und Herren, → Sehr geehrte Damen und Herren, (keine Ansprechperson in Anzeige) (korrekt) | keine | att0: Firma nicht genannt ("Ihrem Betrieb"); att1: Absatz 1 und 3 nahezu identisch wiederholt |
| cl-05-source-fixture | review_required | WRONG_COMPANY, too_short_or_list_like, unsupported_personal_claim | 190 | 2506 | a0: ja/nein; a1: NEIN/nein | Sehr geehrte Damen und Herren, → Sehr geehrte Damen und Herren, (keine Ansprechperson in Anzeige) (korrekt) | keine | att0: "die Abläufe zwischen Halle und Büro zu steuern"; letzter Satz doppelt; att1: Firma nicht genannt ("Ihrem Unternehmen"), "Schichtkoordination zwischen Halle und Büro" (Profil: "im Lager") |
| cl-07-adr-schein-trap | review_required | unsupported_personal_claim | 227 | 2502 | a0: ja/nein; a1: ja/nein | Sehr geehrte Damen und Herren, → Sehr geehrte Damen und Herren, (keine Ansprechperson in Anzeige) (korrekt) | att0: keine; att1: "Ich bin bereit, Gefahrgut-Sendungen selbst zu disponieren, wenn der ADR-Schein vorhanden ist." (bedingt, keine Besitzbehauptung; must_not_contain-Treffer) | att0: Sätze mehrfach wiederholt; att1: "Als Fachlagerist ... ermöglicht es mir, ... Tourenplanung im Tagesgeschäft sicherstelle und den Umgang mit SAP TM sicherstelle" (Floskel 4x) |
| cl-09-named-contact | review_required | unsupported_personal_claim | 202 | 2504 | a0: ja/nein; a1: ja/nein | Sehr geehrte Damen und Herren, → Sehr geehrte Frau Quendel, (FALSCH) | keine | att0: "über viele Jahre", "Störungen gegenüber Verladern einzuhalten" (unverständlich) |
| cl-10-english-ad | letter_returned | – | 97 | 2485 | F: ja/ja; a0: ja/ja | Sehr geehrte Damen und Herren, → Sehr geehrte Damen und Herren, (keine Ansprechperson in Anzeige) (korrekt) | keine | FINAL(=att0): "machen mich eine ideale Kandidatin" (weibliche Form, Bewerber Nils; Profil ohne Geschlechtsangabe – UNSICHER); "habe ich die Anforderungen der Anzeige erfüllt"; Brief deutsch bei englischer Anzeige |
| cl-11-long-ad-requirements-end | review_required | unsupported_personal_claim | 284 | 2531 | a0: ja/ja; a1: ja/nein | Sehr geehrte Damen und Herren, → Sehr geehrte Damen und Herren, (keine Ansprechperson in Anzeige) (korrekt) | keine | att0: "meine Fähigkeit, Wege und Namen auf dem Hof zu kennen"; att1: SAP TM fehlt |
| cl-12-html-remnants | review_required | unsupported_personal_claim | 211 | 2504 | a0: ja/ja; a1: ja/nein | Sehr geehrte Damen und Herren, → Sehr geehrte Damen und Herren, (keine Ansprechperson in Anzeige) (korrekt) | keine | att0: "Dispatcher (m/w/d)" im Text (must_not_contain), "über viele Jahre"; att1: "habe ich mich auch mit SAP TM intensiv beschäftigt" |
| cl-14-two-stations | review_required | missing_profile_references, unsupported_personal_claim | 188 | 2497 | a0: NEIN/ja; a1: ja/ja | Sehr geehrte Damen und Herren, → Sehr geehrte Damen und Herren, (keine Ansprechperson in Anzeige) (korrekt) | keine | Profil ohne Tätigkeiten; att0: Firma nicht genannt, "Lagermanagement und die Organisation der Warenbewegung", Absatz 1 in Absatz 2 wiederholt; att1: "Organisation von Lagerflächen und der Verwaltung von Warenbewegungen"; Zeiträume fehlen |
| cl-15-station-and-skill | review_required | missing_profile_references | 172 | 2477 | a0: ja/ja; a1: ja/nein | Sehr geehrte Damen und Herren, → Sehr geehrte Damen und Herren, (keine Ansprechperson in Anzeige) (korrekt) | keine | att0: "Effizienz der Fahrzeugflotte"; att1: Wiederholungen; Zeitraum fehlt |
| cl-18-sap-business-one-covers-sap | review_required | unsupported_personal_claim | 181 | 2476 | a0: ja/ja; a1: ja/ja | Sehr geehrte Damen und Herren, → Sehr geehrte Damen und Herren, (keine Ansprechperson in Anzeige) (korrekt) | keine | att0/att1: "In meiner Rolle als Rechnungsprüfung" (must_not_contain), "Erfassung und Prüfung von Belegen"; att0: "Analyse der finanziellen Daten"; SAP Business One korrekt, keine weitere SAP-Variante behauptet |
| cl-20-nordmole-dispatcher | review_required | unsupported_personal_claim | 230 | 2505 | a0: ja/nein; a1: ja/nein | Sehr geehrte Damen und Herren, → Guten Tag Robin Beispiel, (FALSCH) | keine | att1: "Ersatzfahrzeuge zu setzen", "Abstimmung zwischen Disposition und Wareneingang" (Anzeigenaufgaben), "Fahrerverbund zuordnungen" (entstellt), "Disponent / Dispatcher (m/w/d) Nahverkehr" (must_not_contain) |
| cl-24-two-requirements-in-title | review_required | missing_profile_references, unsupported_personal_claim | 165 | 2481 | a0: ja/ja; a1: ja/nein | Sehr geehrte Damen und Herren, → Sehr geehrte Damen und Herren, (keine Ansprechperson in Anzeige) (korrekt) | keine | att0: "in den letzten Jahren" (Station 2016-2019), "Lagerorganisation und Prozessoptimierung"; att1: "die Datenintegrität sicherstellen"; Zeitraum fehlt |
| cl-27-gender-title | review_required | WRONG_COMPANY, missing_profile_references, too_short_or_list_like, unsupported_personal_claim | 173 | 2479 | a0: ja/nein; a1: NEIN/ja | Sehr geehrte Damen und Herren, → Sehr geehrte Damen und Herren, (keine Ansprechperson in Anzeige) (korrekt) | keine | att0: "über mehrere Jahre", "mit verschiedenen Softwarelösungen beschäftigt"; att1: Firma nicht genannt ("Ihrem Unternehmen"), "Industriekaufmann (m/w/d)" im Text |
| cl-28-titled-contact | review_required | unsupported_personal_claim | 180 | 2478 | a0: ja/nein; a1: ja/nein | Sehr geehrte Damen und Herren, → Sehr geehrte Frau Dr. Quendel, (FALSCH) | keine | att0: SAP TM fehlt; sonst nur Wiederholungen |
| cl-29-two-contacts | review_required | unsupported_personal_claim | 547 | 2470 | a0: kein Text; a1: ja/ja | Sehr geehrte Damen und Herren, → Sehr geehrte Damen und Herren, (korrekt) | keine | att0: kein Text (Exception CvImportError llm_output_truncated, 464,4 s); att1: keine auffälligen Zusatzbehauptungen |
| cl-30-html-contact | letter_returned | – | 192 | 2480 | F: ja/ja; a0: ja/nein; a1: ja/ja | Sehr geehrte Damen und Herren, → Sehr geehrte Frau Quendel, (FALSCH) | keine | FINAL(=att1): "Ich bringe mich mit" (ungrammatisch), "die Schichtkoordination im Lager zu optimieren"/"um die Logistikprozesse zu verbessern" (Ausschmückung), SAP TM nicht erwähnt; att0: "über einen Zeitraum von fünf Jahren", "flüssigen Fuhrpark-Abbau" (entstellt) |

Hinweis Stelle: `nein` heißt nur, dass der Stellentitel ohne Genderzusatz nicht wörtlich vorkommt (z. B. "Disposition" statt "Dispatcher"); kein Fall nennt eine falsche andere Stelle. Firma: alle Texte, die eine Firma nennen, nennen die richtige; `NEIN` = Firma gar nicht genannt (nur "Ihr Betrieb/Unternehmen").

## Zurückgegebene Briefe (Volltext)

### q4_k_m / cl-10-english-ad

```text
Sehr geehrte Damen und Herren,

Als Disponent bei der Nordkai Spedition GmbH habe ich von 2019 bis 2024 die Verantwortung für Tourenplanung für Stückgut und Schichtkoordination im Lager übernommen. Diese Erfahrung ist direkt auf die Anforderungen der Dispatcher-Position bei Northquay Freight GmbH übertragbar, da beide Unternehmen auf effiziente Logistikabläufe im Hafenbereich setzen.

Die tägliche Abstimmung mit dem Fuhrpark bei Nordkai Spedition GmbH hat mir ermöglicht, komplexe Tourenpläne zu erstellen und Engpässe frühzeitig zu erkennen. Genau diese Fähigkeit zur Tourenplanung und täglichen Koordination mit dem Fuhrpark ist für Northquay Freight GmbH essenziell, um versprochene Tage einzuhalten und die Logistik am Musterhafen reibungslos zu gestalten.

Neben der operativen Planung bringe ich fundierte Kenntnisse in SAP TM mit, die ich in meiner bisherigen Tätigkeit genutzt habe, um Bestände zu kontrollieren und Prozesse zu optimieren. Die Kombination aus SAP TM und SAP TM ermöglicht es mir, die Anforderungen an die systemgestützte Tourenplanung und die tägliche Koordination mit dem Fuhrpark schnell zu meistern.

Meine Muttersprache ist Deutsch, und ich verfüge über Englischkenntnisse auf B2-Niveau, was die Kommunikation im internationalen Umfeld unterstützt. Ich freue mich darauf, meine Erfahrung in der Tourenplanung und Schichtkoordination bei Northquay Freight GmbH einzubringen.
```

### q2_k_xl_4b_gsq / cl-10-english-ad

```text
Sehr geehrte Damen und Herren,

Als Disponent bei Nordkai Spedition GmbH habe ich mich intensiv mit Tourenplanung für Stückgut beschäftigt. Diese Erfahrung ermöglichte es mir, Touren effizient zu planen und Schichtkoordination im Lager sowie Abstimmung mit dem Fuhrpark zu gewährleisten. Genau diese Aufgaben sind zentral für die Rolle als Dispatcher bei Northquay Freight GmbH.

In meiner bisherigen Rolle als Disponent habe ich die Anforderungen der Anzeige erfüllt, indem ich Tourenplanung für Stückgut durchgeführt und Schichtkoordination im Lager sowie Abstimmung mit dem Fuhrpark organisiert. Diese Fähigkeiten sind essenziell für die täglichen Aufgaben an Northquay Freight GmbH, insbesondere bei der Planung und Koordination.

Mit meiner Erfahrung in Tourenplanung und SAP TM kann ich direkt auf die Anforderungen der Stelle eingehen. Die Nutzung von SAP TM ermöglicht eine effiziente Dokumentation und Planung, was für die täglichen Aufgaben an Northquay Freight GmbH von großer Bedeutung ist.

Ich bringe die notwendigen Fähigkeiten mit, um als Dispatcher bei Northquay Freight GmbH erfolgreich zu arbeiten. Meine Erfahrung als Disponent bei Nordkai Spedition GmbH und meine Kenntnisse in Tourenplanung und SAP TM machen mich eine ideale Kandidatin für diese Position.

Mit freundlichen Grüßen,
Nils Quendel
```

### q2_k_xl_4b_gsq / cl-30-html-contact

```text
Sehr geehrte Damen und Herren,

Als Disponent bei Nordkai Spedition GmbH habe ich mich intensiv mit Tourenplanung für Stückgut beschäftigt. Diese Erfahrung ermöglichte mir, effiziente Touren zu planen und die Schichtkoordination im Lager zu optimieren. Zudem habe ich mich mit dem Fuhrpark abgestimmt, um die Logistikprozesse zu verbessern.

In der HafenLogistik GmbH möchte ich meine Erfahrung als Disponent für Stückgut einbringen. Ich bringe mich mit, um Tourenplanung für Stückgut zu optimieren und die Schichtkoordination im Lager zu verbessern. Zudem werde ich mich mit dem Fuhrpark abstimmen, um die Logistikprozesse zu verbessern.

Mit meinen Erfahrungen als Disponent bei Nordkai Spedition GmbH und meiner Fähigkeit zur Tourenplanung für Stückgut bin ich ideal für die Position als Dispatcher bei HafenLogistik GmbH.

Ich freue mich auf Ihre Rückmeldung.

Mit freundlichen Grüßen,
Nils Quendel
```

## Guard-Replay (welche Sätze den Screen auslösten)

`tools/replay_guard.py` führt die deterministischen Prüfungen aus `rewrite_cover_letter` (validate_writing_grounded, cover_letter_reference_hits, Qualitätsregel, screen_prepared_letter) ohne LLM auf die aufgezeichneten Rohantworten aus (km_main nur gelesen, PYTHONDONTWRITEBYTECODE=1). Die so berechneten Flags des letzten Versuchs stimmen bei allen 32 Fällen mit den aufgezeichneten `issues` überein. Ergebnis je Versuch inkl. beanstandeter Sätze: `GUARD_REPLAY.json`. Befund: `unsupported_personal_claim` beanstandet in den meisten Entwürfen viele allgemeine Sätze, nicht nur erfundene Nachweise; der ADR-Satz in q4_k_m cl-07 att0 ist unter den beanstandeten Sätzen.

Weitere Fakten: q2_k_xl_4b_gsq cl-29 att0 brach mit `CvImportError llm_output_truncated` ab (stdout: `n_ctx=4096 n_prompt=1311 max_tokens=2777 n_answer=2777`), wall 547 s. Alle Exit-Codes 0, killed=0.

Helfer: `../tools/{summarize.py,grounding.py,diff.py}` gehören zum CV-Parser-Vergleich (junit/FIELD_DIFF/source_text) und sind auf Anschreiben-JSONs nicht anwendbar; nicht verwendet. Verwendet: `tools/facts.py` (→ FACTS.json), `tools/claims_scan.py` (→ CLAIMS_SCAN_<modell>.txt).

## Redaction

Gesucht (rg, case-insensitive) in allen Dateien dieses Ordners: GITHUB_TOKEN, HF_TOKEN, ghp_, hf_, github_pat_, /home/, Box-Hostname, .local/.internal. Ergebnis: keine Treffer für Tokens/Env-Variablen, Hostname oder /home/-Pfade. Nur Fehltreffer auf das Wort "token" (Feldname `cap_tokens_not_in_profile_or_job` in FACTS.json/facts.py, "max_tokens" im stdout-Log). Nichts redigiert. Nicht redigiert, nur vermerkt: temporäres HOME `/tmp/kk-letters-home.m6f9` in RUN.log, /workspace-Pfade (Modelle, Repo) in JSONs und Skripten.

## Integrität

`SHA256SUMS` über alle Dateien dieses Ordners außer SHA256SUMS selbst; Prüfung mit `sha256sum -c SHA256SUMS`.
