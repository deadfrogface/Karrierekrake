# HR-Urteil (Entwurf) – CV-Extrakt Q4_K_M, SMOKE_DE_EN_10 (ThinkPad-Lauf 2026-10-18/19)

**Status: ENTWURF.** Nur synthetische Daten. Dieses Dokument bewertet nur das Lieferstück **CV-Extrakt**. Matching und Anschreiben werden hier nicht bewertet. **Unbeaufsichtigter Versand bleibt AUS.**

## 0. Grundlagen

| Punkt | Wert |
|---|---|
| Prüfmaßstab | `docs/personaler/ABNAHME_CHECKLISTE.md` (Abschnitt 1, 3), `docs/personaler/BLIND_REVIEW_BERICHT.md` (Präzedenz, Abschnitt 6) |
| Gold | `tests/fixtures/cv_corpus/CV_Parser_Sollwerte_Vollstaendig.txt` (laut eigener Angabe „verbindliches Lösungsblatt“, Regel 4: „Inhalt, Zuordnung, Anzahl und Bedeutung müssen jedoch exakt stimmen“). Ergänzend `expected_results.json` (laut Audit-Notiz nur Teil-Lösungsblatt) und `artifacts/cv_parser_replacement/SMOKE_DE_EN_10_MANIFEST.json` (ordnet die 10 PDFs dem Namen `SMOKE_DE_EN_10_V1` zu). |
| Quelle | `tests/fixtures/cv_corpus/<CV>.pdf`, Text per `pdftotext -layout` und `pdftotext` (DE_05: 2 Seiten, alle anderen 1 Seite) |
| Code-Stand | `47e8f83b08a1925579891abbc861b68a284a66a8` (PR #144). Quelle: `_harness/kk144_src_47e8f83b.zip` (git-archive, Kommentar im ZIP = dieser Commit). Alle 10 Extrakte tragen `product_commit` = dieser Commit. |
| Modell | Qwen3.5-4B-Q4_K_M.gguf, SHA256 `00fe7986…ef11a4`, gepinnt = ja (`RUN.log`, `run_meta.json`), temperature 0.0 |
| Extrakte | 10 × `<CV>.child_raw.json` + `<CV>.json`. In allen 10 Fällen ist `<CV>.json.extract` identisch mit `<CV>.child_raw.json.parsed` (maschinell geprüft). `ok=true`, `kind=ok`, Exit-Code 0. |
| Herkunft der Dateien | Der Ordner lag **nicht** unter `/workspace/thinkpad_extracts_2026-10-18/`, sondern auf dem ThinkPad (<ThinkPad-Host>) unter `%USERPROFILE%\kk_extracts_2026-10-18\q4_k_m\`. Kopiert über `q4_k_m_pack.zip`; SHA256 aller 21 JSON-Dateien auf ThinkPad und Box identisch. |

Bewertungsregeln (unverändert aus der Checkliste übernommen, nichts gesenkt):

- **Interview-ready**: Name und Kontakt (E-Mail, Telefon, ladungsfähige Anschrift, soweit in der Quelle) stimmen; alle Beschäftigungen mit korrektem Zeitraum; Abschlüsse und Knock-out-Qualifikationen vorhanden und belegt; keine erfundenen Fakten.
- **Papierkorb**: erfundener Arbeitgeber, erfundenes Zertifikat, erfundener Führerschein oder erfundene Sprache (sofort); relevante Qualifikation fehlt/falsch; beendete Stelle als aktuell; falscher Kontakt („Ein Extrakt mit … falschem Kontakt ist nicht interview-ready“). Die Checkliste kennt nur drei Urteile; ein nicht interview-reifer Extrakt ohne Blocker wird hier als Papierkorb geführt (= nicht automatisch versenden).
- **Blockiert**: Quelle, Gold oder lesbarer Output fehlt.
- Zulässige Normalisierung laut Sollwerte-Regel 4/5: Groß-/Kleinschreibung, Leerzeichen, Bindestriche, rein technisches Datumsformat (`03.2021` → `03/2021`), `heute`/`Present`/`current` → laufend.
- Scores, Gate-Ergebnisse (`test_sollwerte_corpus_production_path_all_pass`) und `extract_confirmation.invented_count=0` ersetzen das Urteil nicht. Hinweis: Das Repo-Gate prüft weder Beschäftigungsdaten noch Zertifikatsjahre und akzeptiert die Hausnummer irgendwo im Straßenfeld; dieses Urteil ist daher strenger als das Gate.

Maschinelle Zusatzprüfung: Jeder extrahierte Titel, Arbeitgeber, Abschluss, jede Institution, jedes Zertifikat, jede Sprache und jedes Level, jeder Skill und jede Software kommt wörtlich (Groß-/Kleinschreibung und Leerzeichen normalisiert) im Quelltext vor. **Kein einziger nicht belegter Wert in allen 10 Extrakten.**

## 1. Übersicht

| CV | Urteil | Entscheidende Beobachtung |
|---|---|---|
| DE_01_Klassisch | **Interview-ready** | Alle Pflichtfelder korrekt. Mangel: Zertifikatsjahre fehlen (3×). UNSICHER, ob das Jahr Pflicht ist. |
| DE_02_Zweispaltig_Trap | **Interview-ready** | Zweispalten-Falle bestanden, keine Spaltenvermischung, kein „WEITERE KENNTNISSE“ als Sprache, C1/B1/A2 nicht als Führerschein. |
| DE_03_C1_Kontextfalle | **Interview-ready** | C1-Falle bestanden: C1 als Sprachniveau (Englisch, Türkisch) und als Führerscheinklasse (Abschnitt „Fahrerlaubnis“). |
| DE_04_Unvollstaendige_Kontaktdaten | **Interview-ready** | Telefon, Straße, Hausnummer, PLZ, Geburtsdatum bleiben leer, nichts erfunden. |
| DE_05_Zweiseitig | **Interview-ready** | Seite 1 vollständig korrekt, kein zweites Profil. Mangel: „Projekt- und Sonderaufgaben“ (einziger Inhalt auf Seite 2) fehlen im strukturierten Extrakt. UNSICHER (Falle teilweise). |
| EN_01_Classic_Resume | **Papierkorb** (UNSICHER in der Schwere) | Kontakt: `house_number` leer, Hausnummer „18“ steht in `street`. Kein erfundener Wert. |
| EN_02_Two_Column_Trap | **Papierkorb** (UNSICHER in der Schwere) | Kontakt: `house_number` leer, „42“ steht in `street`. Zweispalten-Falle sonst bestanden. |
| EN_03_Missing_Address_Fields | **Interview-ready** | Fehlende Felder bleiben leer, nichts erfunden. |
| EN_04_German_Address_English_CV | **Interview-ready** | Deutsche Adresse korrekt zerlegt (Seestraße / 31 / 78462 / Konstanz / Germany). |
| EN_05_Skills_Heavy | **Papierkorb** (UNSICHER in der Schwere) | Kontakt: `house_number` leer, „7“ steht in `street`. Zusätzlich fehlen Zertifikatsjahre (3×). |

Blockiert: **kein** CV. Quelle, Gold und lesbarer Extrakt liegen für alle 10 vor.

**Erfundene Arbeitgeber / Zertifikate / Führerscheine / Sprachen: keine.** Nicht-Sprachwörter (z. B. „microsoft“, „WEITERE KENNTNISSE“, „Power BI“) im Feld `languages`: **keine.**

### Zur Schwere des Hausnummer-Befunds (EN_01, EN_02, EN_05) – UNSICHER

Die Anschrift ist inhaltlich vollständig und wörtlich belegt (z. B. `street`=„18 Willow Street“, `postal_code`=„BS1 4QF“, `city`=„Bristol“, `country`=„United Kingdom“). Abweichend vom verbindlichen Gold sind die Felder `STRASSE` und `HAUSNUMMER` zugeordnet; `HAUSNUMMER` ist leer, obwohl die Quelle eine Hausnummer enthält. Nach Sollwerte-Regel 4 („Zuordnung … exakt“) und Checkliste („Kontakt … stimmt“) ist das kein korrekter Kontakt, daher hier nicht interview-ready → Papierkorb. Der frühere VM-Bericht (`docs/qa/PR144_MODEL_COMPARE_GSQ4B_Q4KM_2026-10-18.md`, BLIND_REVIEW_BERICHT Abschnitt 6) hat denselben Befund nur als „Hinweis“ gewertet und Q4_K_M als interview-ready geführt. **Diese Abweichung muss die abnehmende Personalerin oder der Personaler entscheiden.** Falls die Zuordnung „Nr. + Straße“ in einem Feld für UK/IE-Adressen akzeptiert wird, wären EN_01 und EN_02 interview-ready und EN_05 hinge nur noch an den Zertifikatsjahren (siehe unten). Ein Schwellenwert wird hier nicht gesenkt.

## 2. Befunde je CV

Format: **Feld** | extrahierter Wert | Quelle (Zitat aus pdftotext) | Gold | Bewertung.

### DE_01_Klassisch – Interview-ready

Korrekt (Kontakt): Vorname „Mara“, Nachname „König“, street „Buchenweg“, house_number „14“, postal_code „48143“, city „Münster“, E-Mail „mara.koenig@example.com“, Telefon „+49 151 20003000“, Geburtsdatum „07.11.1994“. Quelle: „Buchenweg 14, 48143 Münster“ / „mara.koenig@example.com | +49 151 20003000“ / „Geboren: 07.11.1994“.
Korrekt (Stellen, 3/3): 05/2022–heute Teamkoordinatorin Kundenservice, Westfalen Service GmbH; 01/2019–04/2022 Sachbearbeiterin Auftragsmanagement, HanseKontor Handel KG; 08/2016–12/2018 Kaufmännische Mitarbeiterin, Rheinblick Versand GmbH.
Korrekt: Ausbildung 08/2013–06/2016 „Kauffrau für Büromanagement (IHK)“, „Berufskolleg Münster / BüroPartner West GmbH“; Sprachen Deutsch „Muttersprache (C2)“, Englisch C1, Französisch B1; Führerschein B; Software 6/6; Skills 5/5; Zertifikatsnamen 3/3.

| Feld | Extrahiert | Quelle | Gold | Bewertung |
|---|---|---|---|---|
| certificates[0].year | „“ (leer) | „IHK Beschwerdemanagement, 2024“ | `ZERTIFIKAT_1: IHK Beschwerdemanagement \| 2024` | **Mangel: Datum fehlt.** Kein Papierkorb-Kriterium der Checkliste. UNSICHER, ob die Abnahme das Zertifikatsjahr als Pflicht wertet. |
| certificates[1].year | „“ | „Power BI Grundlagen, 2023“ | `… \| 2023` | wie oben |
| certificates[2].year | „“ | „Ersthelferin, 2025“ | `… \| 2025` | wie oben |
| work_experience[*].company | „Westfalen Service GmbH“ (ebenso „HanseKontor Handel KG“, „Rheinblick Versand GmbH“) | „Westfalen Service GmbH, Münster“ / „…, Dortmund“ / „…, Essen“ | `Westfalen Service GmbH, Münster` | Hinweis: Ortszusatz des Arbeitgebers nicht übernommen; Arbeitgebername korrekt. Kein Fehler. |

### DE_02_Zweispaltig_Trap – Interview-ready

Korrekt (Kontakt): Jonas Falkenberg, „Hafenweg“ / „87“ / „28195“ / „Bremen“, „jonas.falkenberg@example.com“, „+49 151 11112222“, Geburtsdatum „19.02.1991“. Quelle: „Hafenweg 87 · 28195 Bremen“, „jonas.falkenberg@example.com · +49 151 11112222“, „Geburtsdatum: 19.02.1991“. „FIKTIVER TEST-LEBENSLAUF“ nicht als Name.
Korrekt (Stellen, 4/4, Titel–Arbeitgeber–Zeitraum richtig gepaart, keine Spaltenvermischung): 04/2023–heute Projektkoordinator Operations & Customer Solutions, WeserTech Anlagenservice GmbH; 01/2020–03/2023 Sachbearbeiter Einkauf & Disposition, Nordstern Komponentenhandel KG; 08/2016–12/2019 Kundenservice / Auftragsmanagement, Elbkontor Bürobedarf GmbH; 07/2013–07/2016 Kaufmännischer Mitarbeiter, Moorland Versandservice GmbH.
Korrekt: Ausbildung 2/2 (09/2010–06/2013 „Kaufmann für Groß- und Außenhandelsmanagement (IHK)“, „Nordwest Handelsakademie / Friesen Import GmbH“; 08/2008–06/2010 „Fachhochschulreife Wirtschaft und Verwaltung“, „BBS Ammerland“); Sprachen Deutsch C2, Englisch C1, Niederländisch B1, Polnisch A2; Führerschein B, BE (keine C1/B1/A2); Software 12/12 (aus „WEITERE KENNTNISSE“, Überschrift selbst nicht als Wert); Zertifikate 5/5; Skills 12/12.

| Feld | Extrahiert | Quelle | Gold | Bewertung |
|---|---|---|---|---|
| education[0] (Note) | nicht vorhanden (Schema ohne Notenfeld) | „Nordwest Handelsakademie / Friesen Import GmbH \| Note 2,1“ | `… \| Note 2,1` | Hinweis: Abschlussnote nicht erfasst; Schema hat kein Feld. Kein Papierkorb-Kriterium. |
| certificates[*].year | leer | Quelle nennt keine Jahre | keine Jahre | korrekt leer |
| Lauf-Herkunft | – | `RUN.log`: „RESTART after agent disconnect killed driver during DE_02 (~00:44-00:47)“; danach „SKIP DE_02“, eine Zeile „CV DE_02 …“ fehlt | – | Hinweis: Der Kindprozess lief laut `logs/DE_02_Zweispaltig_Trap.log` bis 00:50:56 (MESZ) durch, `process_exit_code` 0, `finished` 00:50:57 (MESZ), Commit und Modell-Hash korrekt. Zweiter LLM-Aufruf (n_prompt=132) = Zertifikats-Vervollständigung `_complete_explicit_lists`; „Power BI“ und „Lean / 5S“ stammen wörtlich aus dem Abschnitt „WEITERBILDUNGEN & ZERTIFIKATE“. Kein Einfluss auf das Urteil. |

### DE_03_C1_Kontextfalle – Interview-ready

Korrekt (Kontakt): Selin Aras, „Kastanienallee“ / „6a“ / „40233“ / „Düsseldorf“, „selin.aras@example.net“, „+49 160 3456789“, Geburtsdatum leer (Quelle ohne Geburtsdatum). „Curriculum Vitae“ nicht als Name.
Korrekt (Stellen 2/2): 03/2021–heute „Office & Procurement Specialist“, „Rheinwerk Technik GmbH“ (Quelle: „seit 03.2021 - Office & Procurement Specialist“); 09/2017–02/2021 „Customer Operations Specialist“, „Metroline Services KG“ (Quelle: „09.2017 - 02.2021“). Datumsformat nur technisch normalisiert.
Korrekt: Ausbildung 2014–2017 „Ausbildung zur Kauffrau für Büromanagement“, „IHK Düsseldorf“; 2012–2014 „Höhere Handelsschule“, „Berufskolleg Düsseldorf“. Software 6/6, Skills 5/5. Zertifikate: leer (Gold: 0) – korrekt, nichts erfunden.

| Feld | Extrahiert | Quelle | Gold | Bewertung |
|---|---|---|---|---|
| languages | Deutsch C2, Englisch C1, Türkisch C1 | „Deutsch C2 \| Englisch C1 \| Türkisch C1“ | C2 / C1 / C1 | **Falle bestanden** |
| driving_license | [„B“, „C1“] | „Fahrerlaubnis / Klassen B und C1“ | B, C1 | **Falle bestanden**: C1 nur aus dem Führerschein-Abschnitt, Sprach-C1 nicht als zusätzliche Klasse |

### DE_04_Unvollstaendige_Kontaktdaten – Interview-ready

| Feld | Extrahiert | Quelle | Gold | Bewertung |
|---|---|---|---|---|
| city | „Leipzig“ | „Leipzig \| nina.sommer@example.org“ | Leipzig | korrekt |
| street / house_number / postal_code | „“ / „“ / „“ | nicht vorhanden | NICHT VORHANDEN | **Falle bestanden**, nichts erfunden |
| phones | [] | nicht vorhanden | NICHT VORHANDEN | **Falle bestanden** |
| date_of_birth, country | „“ | nicht vorhanden | NICHT VORHANDEN | korrekt leer |
| emails | „nina.sommer@example.org“ | wörtlich | ebenso | korrekt |
| driving_license | [] | nicht vorhanden | 0 | korrekt, nichts erfunden |

Korrekt außerdem: Stellen 2/2 (11/2023–heute Junior Project Manager, Elster Digital GmbH; 10/2021–10/2023 Projektassistenz, Saxonia Media Services GmbH); Ausbildung 2/2 (10/2018–09/2021 B.A. Betriebswirtschaftslehre, Hochschule Leipzig; 08/2010–06/2018 Abitur, Goethe-Gymnasium Leipzig); Sprachen Deutsch „Muttersprache“, Englisch B2, Spanisch A2; Zertifikate 3/3 (Quelle ohne Jahre); Software 5/5; Skills 4/4.

### DE_05_Zweiseitig – Interview-ready (mit UNSICHER zur Seite-2-Falle)

Korrekt (Kontakt): Tobias Renner, „Am Stadtpark“ / „22b“ / „90402“ / „Nürnberg“, „tobias.renner@example.com“, „+49 176 99887766“; Geburtsdatum leer (Gold: NICHT VORHANDEN). „Bewerbungsprofil“ nicht als Name.
Korrekt (Stellen 4/4): 02/2024–heute Operations Analyst, Franken Logistik Solutions GmbH; 06/2021–01/2024 Disponent, SüdCargo KG; 01/2018–05/2021 Kaufmännischer Sachbearbeiter, Bavaria Handel GmbH; 08/2015–12/2017 Service Mitarbeiter, MesseService Nürnberg GmbH (Quelle „02.2024 - heute“ usw., nur Format normalisiert).
Korrekt: Ausbildung 2012–2015 „Kaufmann für Spedition und Logistikdienstleistung (IHK)“, Institution „Nürnberg“ (Quelle: „…(IHK), Nürnberg“; Gold identisch; „(IHK)“ vorhanden, anders als beim Q2_K_XL-Befund); 2008–2012 „Mittlere Reife“, „Realschule Nürnberg“. Sprachen Deutsch C2, Englisch B2, Tschechisch A2; Führerschein B, BE; Software 6/6; Zertifikate 4/4 („Arbeitssicherheit 2025“ wörtlich wie in Quelle und Gold); Skills 7/7. Kein zweites Profil, keine Doppelungen.

| Feld | Extrahiert | Quelle (Seite 2) | Gold | Bewertung |
|---|---|---|---|---|
| Projekt-/Sonderaufgaben | nicht im strukturierten Extrakt (Schema ohne Feld). Im `source_text` des Extrakts ist Seite 2 enthalten. | „Projekt- und Sonderaufgaben • Einführung eines monatlichen KPI-Dashboards für Transportabweichungen. • Optimierung der Dispositionsübergabe zwischen Früh- und Spätschicht. • Unterstützung bei einer Stammdatenbereinigung in SAP TM.“ | `PROJEKT-/SONDERAUFGABEN_ANZAHL: 3`; FALLE: „Seite 2 … darf weder ignoriert noch als neues Dokument/Profil behandelt werden.“ | **Mangel / Falle teilweise.** Teil „kein neues Profil“ bestanden; Teil „nicht ignorieren“ im strukturierten Profil nicht erfüllt. Keine Qualifikation, kein Arbeitgeber, kein Zeitraum betroffen → kein Papierkorb-Kriterium der Checkliste. **UNSICHER**, ob die Abnahme die Projekte als stellenrelevant wertet. |
| Mobilität | nicht erfasst | „Führerschein: B, BE \| eigener PKW“ | `WEITERE_MOBILITAET: eigener PKW` | Hinweis: kein Schemafeld; „eigener PKW“ korrekt **nicht** als Führerschein ausgegeben. |

### EN_01_Classic_Resume – Papierkorb (Schwere UNSICHER, siehe Abschnitt 1)

| Feld | Extrahiert | Quelle | Gold | Bewertung |
|---|---|---|---|---|
| personal.street | „18 Willow Street“ | „18 Willow Street, Bristol BS1 4QF, United Kingdom“ | `STRASSE: Willow Street` | **Kontakt-Zuordnung falsch** (Hausnummer im Straßenfeld) |
| personal.house_number | „“ | „18 Willow Street…“ | `HAUSNUMMER: 18` | **Kontaktfeld leer, obwohl in der Quelle** |

Korrekt: Emily Carter („Resume“ nicht als Name), postal_code „BS1 4QF“, city „Bristol“, country „United Kingdom“, „emily.carter@example.com“, „+44 7700 900123“. Stellen 3/3: „Mar 2022“–heute Customer Operations Lead, Harbour & Co Services Ltd (Quelle „Mar 2022 - Present“; „heute“ = zulässige Normalisierung); „Jul 2019“–„Feb 2022“ Order Management Specialist, Cedar Trading Group; „Sep 2016“–„Jun 2019“ Customer Service Coordinator, Northbridge Office Supplies. Ausbildung 2013–2016 BA Business Management, University of the West of England. Sprachen English Native, German B2, French A2. Führerschein leer (Gold 0). Zertifikate 3/3 (Quelle ohne Jahre). Software 6/6, Skills 5/5.

### EN_02_Two_Column_Trap – Papierkorb (Schwere UNSICHER, siehe Abschnitt 1)

| Feld | Extrahiert | Quelle | Gold | Bewertung |
|---|---|---|---|---|
| personal.street | „42 Kingfisher Road“ | „42 Kingfisher Road · Manchester M1 2AB“ | `STRASSE: Kingfisher Road` | **Kontakt-Zuordnung falsch** |
| personal.house_number | „“ | ebenso | `HAUSNUMMER: 42` | **Kontaktfeld leer, obwohl in der Quelle** |

Zweispalten-Falle sonst bestanden: „CURRICULUM VITAE“ nicht als Name; Sprachen English C2, Spanish C1, German B1; Führerschein nur „B“ (Quelle „Driving licence / Category B“), C1/B1 nicht als Klasse; Stellen 3/3 richtig gepaart (2023–heute Operations Coordinator, Redwood Mobility Ltd; 2020–2023 Customer Success Specialist, Blue Peak Systems; 2017–2020 Sales Support Administrator, Oakfield Distribution); Ausbildung 2/2 (BSc Business & Management, Manchester Metropolitan University, 2014–2017 – Zeilenumbruch „Metropolitan / University“ korrekt zusammengeführt; A Levels, Northside College, 2012–2014); Software 7/7 („TECH STACK“), Zertifikate 3/3, Skills 6/6. Kontakt sonst korrekt: „M1 2AB“, „Manchester“, „daniel.brooks@example.org“, „+44 7700 900555“; country leer (Gold: NICHT VORHANDEN) – korrekt.

### EN_03_Missing_Address_Fields – Interview-ready

| Feld | Extrahiert | Quelle | Gold | Bewertung |
|---|---|---|---|---|
| city / country | „Berlin“ / „Germany“ | „Berlin, Germany \| aisha.rahman@example.net“ | Berlin / Germany | korrekt |
| street / house_number / postal_code / phones / date_of_birth | leer | nicht vorhanden | NICHT VORHANDEN | **Falle bestanden**, nichts erfunden |

Korrekt außerdem: Stellen 2/2 (2024–heute Procurement Coordinator, Linden Works GmbH; 2021–2024 Operations Assistant, Urban Supply Europe GmbH); Ausbildung 2018–2021 B.A. International Business, Berlin School of Economics; Sprachen German C1, English C2, Arabic Native; Führerschein leer; Zertifikate leer (Gold 0); Software 5/5; Skills 5/5.

### EN_04_German_Address_English_CV – Interview-ready

Korrekt: Lucas Meyer („PROFILE“ nicht als Name); „Seestraße“ / „31“ / „78462“ / „Konstanz“ / „Germany“ (Quelle „Seestraße 31, 78462 Konstanz, Germany“); „lucas.meyer@example.com“, „+49 172 4000500“. Stellen 2/2 (04/2022–heute Service Delivery Manager, Alpine Cloud Services GmbH, Quelle „04/2022 - current“; 01/2019–03/2022 Support Operations Specialist, LakeTech Solutions AG). Ausbildung 2015–2018 B.Sc. Business Information Systems, HTWG Konstanz. Sprachen German C2, English C1, Italian B2. Führerschein B, BE. Zertifikate leer (Gold 0). Software 6/6, Skills 5/5. Befunde: keine.

### EN_05_Skills_Heavy – Papierkorb (Schwere UNSICHER, siehe Abschnitt 1)

| Feld | Extrahiert | Quelle | Gold | Bewertung |
|---|---|---|---|---|
| personal.street | „7 Orchard Lane“ | „7 Orchard Lane, Dublin D02 XY76, Ireland“ | `STRASSE: Orchard Lane` | **Kontakt-Zuordnung falsch** |
| personal.house_number | „“ | ebenso | `HAUSNUMMER: 7` | **Kontaktfeld leer, obwohl in der Quelle** |
| certificates[0].year | „“ | „2024 CIPS Procurement Essentials“ | `ZERTIFIKAT_1: CIPS Procurement Essentials \| 2024` | **Mangel: Datum fehlt** (UNSICHER, ob Pflicht) |
| certificates[1].year | „“ | „2023 Advanced Excel & Power Query“ | `… \| 2023` | wie oben |
| certificates[2].year | „“ | „2022 GDPR Awareness for Operations“ | `… \| 2022` | wie oben |

Korrekt: Sophia Bennett, „D02 XY76“, „Dublin“, „Ireland“, „sophia.bennett@example.com“, „+353 85 123 4567“. Stellen 3/3 (2022–heute Purchasing Specialist, Greenline Medical Supplies Ltd; 2019–2022 Supply Chain Administrator, Meridian Homeware Ltd; 2016–2019 Order Processing Assistant, Cobalt Distribution Ltd). Ausbildung 2012–2016 BCom, Dublin City University (die drei Kurse aus „Education & Training“ korrekt als Zertifikate, nicht als Abschluss). Sprachen English Native, German B1. Führerschein leer. Software 6/6, Skills 8/8.

## 3. Harte Defekte (Liste)

1. **EN_01** `personal.house_number` = „“ / `personal.street` = „18 Willow Street“; Quelle „18 Willow Street, Bristol BS1 4QF, United Kingdom“; Gold Straße „Willow Street“, Hausnummer „18“. Kontakt-Zuordnung falsch. (Schwere UNSICHER, siehe Abschnitt 1.)
2. **EN_02** `personal.house_number` = „“ / `personal.street` = „42 Kingfisher Road“; Quelle „42 Kingfisher Road · Manchester M1 2AB“; Gold „Kingfisher Road“ / „42“. (Schwere UNSICHER.)
3. **EN_05** `personal.house_number` = „“ / `personal.street` = „7 Orchard Lane“; Quelle „7 Orchard Lane, Dublin D02 XY76, Ireland“; Gold „Orchard Lane“ / „7“. (Schwere UNSICHER.)

Nicht gefunden: erfundene Arbeitgeber, Zertifikate, Führerscheine, Sprachen; Nicht-Sprachwörter als Sprache; falsche oder fehlende Beschäftigungsdaten; beendete Stellen als aktuell markiert; falsche E-Mail- oder Telefonwerte; erfundene Kontaktdaten bei DE_04/EN_03.

## 4. Mängel ohne Papierkorb-Wirkung (nach Checkliste), zur Entscheidung

- DE_01, EN_05: `certificates[*].year` leer, obwohl Quelle und Gold Jahre nennen (je 3×). **UNSICHER**, ob das Jahr Pflicht ist. Falls ja: DE_01 nicht interview-ready.
- DE_05: Projekt-/Sonderaufgaben von Seite 2 fehlen im strukturierten Extrakt (Schema ohne Feld). Gold-Falle „nicht ignorieren“ nur teilweise erfüllt. **UNSICHER**.
- DE_02: Abschlussnote „Note 2,1“ nicht erfasst (kein Schemafeld).
- DE_05: „eigener PKW“ nicht erfasst (kein Schemafeld), korrekt nicht als Führerschein.
- DE_01: Ortszusätze bei Arbeitgebern („, Münster“, „, Dortmund“, „, Essen“) nicht übernommen.

## 5. Betriebshinweise (kein Einfluss auf das HR-Urteil)

- Alle 10 `child_raw.json` enthalten `local_llm_cv.action = "disabled"` mit der Meldung „wird die lokale Lebenslauf-Auswertung auf dieser Hardware gestrichen; der manuelle Profilimport bleibt möglich.“ Im Produkt wäre die lokale CV-Auswertung auf diesem ThinkPad (Ryzen 5 PRO 4650U, 23,2 GiB RAM) also abgeschaltet. Der Harness hat den Importpfad trotzdem ausgeführt.
- Alle Logs: `peak_rss_exceeded soft-pass (not physical i3)`; Kindprozess ca. 3,5–4,1 GB gegen ein Budget von 3 132 727 552 Byte.
- Zwei Treiber-Abbrüche (DE_02, EN_02) mit Neustart. Erledigte CVs wurden übersprungen, nicht neu erzeugt. Alle 10 Ausgaben haben Exit-Code 0.

## 6. Konsequenz

| Kategorie | Sample-Satz | Urteil | Entscheidende Beobachtung | Versand frei |
|---|---|---|---|---|
| CV-Extrakt | SMOKE_DE_EN_10_V1, Q4_K_M, ThinkPad, Commit 47e8f83b, n=1 Lauf | 7 × Interview-ready, 3 × Papierkorb (EN_01, EN_02, EN_05; Schwere UNSICHER), 0 × Blockiert. **Satz insgesamt nicht interview-ready.** | Hausnummer bei UK/IE-Adressen im Straßenfeld, `house_number` leer. Keine Erfindungen. | **nein** |
| Matching | – | nicht bewertet (Blockiert laut BLIND_REVIEW_BERICHT) | – | nein |
| Anschreiben | – | nicht bewertet (Papierkorb laut BLIND_REVIEW_BERICHT Abschnitt 7) | – | nein |

Unbeaufsichtigter Versand bleibt AUS. Kein Schwellenwert wurde gesenkt, kein Gold geändert, kein Code geändert.
