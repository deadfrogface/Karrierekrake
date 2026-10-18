<!-- Nur synthetische Repo-Fixtures. Keine Modelldateien und keine Extrakt-Einzel-JSONs im Repo. Committete Belege: docs/qa/pr144_model_compare_2026-10-18/ (siehe Abschnitt „Belege“ unten). -->

> **Datum:** 2026-10-18. **Geprüfter Code-Stand:** `adc297cf27039f806066597e02b4da21a7ff8926` (Branch `cursor/roadmap-execution-20261012-d85b`). **Plattform:** VM 16 GB / 8 vCPU, **nicht i3**. Kein Merge nach main, kein Release.

# PR144 Modellvergleich: HR-Qualität (CV-Extrakt / Matching / Anschreiben)

- Repo-Stand adc297cf, Einstellungen über ein QA-Wrapper-Skript außerhalb des Repos (bei allen Modellen gleich, nur KARRIEREKRAKE_CV_LLM_MODEL unterscheidet sich; In-Process-Pfad, kein Server)
- Nur synthetische Daten (Repo-Fixtures). Gemessen auf **VM, nicht i3** (16 GB, 8 vCPU). Kein Ziel gesenkt, kein Test abgeschwächt, nichts gepusht.
- Modelle:
  - **Q2_K_XL** = ISTA-DASLab Qwen3.5-4B GGUF-GSQ Q2_K_XL (sha256 b7d9ec51…cb5a, 1 940 825 248 B) -> `q2_k_xl_4b_gsq/`
  - **Q4_K_M** = unsloth Qwen3.5-4B Q4_K_M, Referenz (sha256 00fe7986…11a4, 2 740 937 888 B) -> `q4_k_m_corpus/`
  - **8B, 27B: BLOCKIERT (nicht evaluiert).**

## 1. Die 12 Test-IDs (pytest, Produktionspfad)

| Test-ID | Q2_K_XL (GSQ 4B) | Q4_K_M (4B) |
|---|---|---|
| tests/test_cv_corpus.py::test_full_corpus_passes | PASSED | PASSED |
| test_each_corpus_document[DE_01_Klassisch] | PASSED | PASSED |
| test_each_corpus_document[DE_02_Zweispaltig_Trap] | PASSED | PASSED |
| test_each_corpus_document[DE_03_C1_Kontextfalle] | PASSED | PASSED |
| test_each_corpus_document[DE_04_Unvollstaendige_Kontaktdaten] | PASSED | PASSED |
| test_each_corpus_document[DE_05_Zweiseitig] | PASSED | PASSED |
| test_each_corpus_document[EN_01_Classic_Resume] | PASSED | PASSED |
| test_each_corpus_document[EN_02_Two_Column_Trap] | PASSED | PASSED |
| test_each_corpus_document[EN_03_Missing_Address_Fields] | PASSED | PASSED |
| test_each_corpus_document[EN_04_German_Address_English_CV] | PASSED | PASSED |
| test_each_corpus_document[EN_05_Skills_Heavy] | PASSED | PASSED |
| tests/test_cv_sollwerte_corpus.py::test_sollwerte_corpus_production_path_all_pass | **FAILED** (9/10, DE_05 AUSBILDUNG_1) | PASSED (10/10) |
| Gesamtlauf (24 Tests) | 23 passed, 1 failed, 1429 s | 24 passed, 1230 s |

**12 vs. 24 (aus junit geprüft):** Die 12 Zeilen oben sind die berichteten Korpus-Test-IDs. pytest hat insgesamt **24** Tests gesammelt: diese 12 plus `test_corpus_fixture_files_present` (1), `test_sollwerte_pdf_fixture_present[…]` (10) und `test_sollwerte_authoritative_file_present` (1). Die 12 zusätzlichen Tests prüfen nur, ob die Fixture-Dateien vorhanden sind; sie bestanden bei beiden Modellen. Die Extraktion läuft einmal (`test_full_corpus_passes`: Q2 1428 s, Q4 1229 s). Die übrigen Tests werten die zwischengespeicherten Extrakte aus (je ≤ 0,01 s).

Belege (committet): `docs/qa/pr144_model_compare_2026-10-18/q2_k_xl_4b_gsq/` und `docs/qa/pr144_model_compare_2026-10-18/q4_k_m_corpus/`, jeweils `pytest_junit.xml`, `RUN_PYTEST.stdout.log`, `RUN_PYTEST.watchdog.log`.

Q2_K_XL Sollwerte-Fehler (pytest): DE_05 AUSBILDUNG_1 erwartet `2012 - 2015 | Kaufmann für Spedition und Logistikdienstleistung (IHK) | Nürnberg`, bekommen: qualification ohne "(IHK)", institution "IHK, Nürnberg". Kein erfundener Inhalt, nur das Feld anders aufgeteilt. Derselbe Gate-Fehler trat auch in Lauf 1 auf (siehe Abschnitt 2).

## 2. CV-Extrakt pro Lauf

### Läufe (n=2 je Modell)

| Lauf | Was | Feld-Daten vorhanden? |
|---|---|---|
| **Lauf 1** = 10-CV-Extraktlauf (`RUN_ALL10`) | Ein Import pro CV über den Repo-Pfad `core.cv_parser.import_cv`, Extrakt als JSON gespeichert. Darauf liefen (a) der QA-Feld-Diff `diff.py` → `FIELD_DIFF.json` und (b) **unverändert die Repo-Evaluatoren** (`scripts/run_cv_sollwerte_corpus.evaluate` = Sollwert-Gate, `scripts/run_cv_corpus.evaluate_doc` = Korpus-Gate), Felder `repo_sollwerte_eval_fails` und `repo_expected_results_eval` in `FIELD_DIFF.json` | ja (Feld-Diff + Gate) |
| **Lauf 2** = pytest-Produktionspfad (`RUN_PYTEST`) | Eigener, neuer Import pro CV. Die Fixture `cv_corpus_importer` parst jedes PDF **einmal** und gibt allen Tests Kopien davon. | **nein**: pytest speichert keine Extrakte. Es gibt nur die Gate-Ergebnisse je CV (junit + JSON-Report im stdout) |

### Q2_K_XL (GSQ 4B)

| CV | Lauf 1: Feld-Diff (`diff.py`) | Lauf 1: Sollwert-Gate (Repo-Evaluator) | Lauf 2: Sollwert-Gate (pytest) | Lauf 2: Korpus-Gate |
|---|---|---|---|---|
| DE_01_Klassisch | 31/31 | PASS | PASS | PASS |
| DE_02_Zweispaltig_Trap | 50/50 (Hinweis: Hausnummer zusätzlich im Straßenfeld) | PASS | PASS | PASS |
| DE_03_C1_Kontextfalle | **27/28**: AUSBILDUNG_2 Qualifikation im Institutionsfeld (`"" / "Höhere Handelsschule, Berufskolleg Düsseldorf"`) | PASS (Gate prüft keine Feldzuordnung, siehe unten) | PASS | PASS |
| DE_04_Unvollstaendige_Kontaktdaten | 23/23 | PASS | PASS | PASS |
| DE_05_Zweiseitig | 36/36 (nur Hinweis `qualification_text_differs`: "(IHK)" fehlt in der Qualifikation, Institution "IHK, Nürnberg") | **FAIL AUSBILDUNG_1** | **FAIL AUSBILDUNG_1** | PASS |
| EN_01_Classic_Resume | 30/30 (Hinweis: "18 Willow Street") | PASS | PASS | PASS |
| EN_02_Two_Column_Trap | 33/33 (Hinweis: "42 Kingfisher Road") | PASS | PASS | PASS |
| EN_03_Missing_Address_Fields | 21/21 | PASS | PASS | PASS |
| EN_04_German_Address_English_CV | 28/28 | PASS | PASS | PASS |
| EN_05_Skills_Heavy | 32/32 (Hinweis: "7 Orchard Lane") | PASS | PASS | PASS |
| **Summe** | **311 korrekt / 1 falsch** | **9/10** | **9/10** | 10/10 |

### Q4_K_M (4B, Referenz)

| CV | Lauf 1: Feld-Diff | Lauf 1: Sollwert-Gate | Lauf 2: Sollwert-Gate (pytest) | Lauf 2: Korpus-Gate |
|---|---|---|---|---|
| DE_01 … DE_05, EN_01 … EN_05 | alle korrekt (31/50/28/23/36/30/33/21/28/32). Hinweis Hausnummer im Straßenfeld bei EN_01, EN_02, EN_05 | 10/10 PASS | 10/10 PASS | 10/10 PASS |
| **Summe** | **312 korrekt / 0 falsch** | **10/10** | **10/10** | 10/10 |

Für Lauf 2 (beide Modelle) gibt es **nur die Gate-Ergebnisse, keine Feld-Daten**. Ob z. B. Q2 in Lauf 2 bei DE_03 die Qualifikation wieder ins Institutionsfeld geschrieben hat, ist daher **UNSICHER**: Das Gate hätte es nicht bemerkt.

**Korrektur zur ersten Fassung:** Dort hieß es, der Q2-Fehler „wandere“ zwischen DE_03 und DE_05. Das stimmt nicht. Das **Sollwert-Gate scheitert in beiden Läufen an DE_05** (AUSBILDUNG_1). DE_03 AUSBILDUNG_2 wurde nur vom strengeren Feldzuordnungs-Check in `diff.py` (Lauf 1) als falsch gewertet, und das Gate lässt es durch. Die Summe 311/1 und das Gate-Ergebnis 9/10 messen also verschiedene Dinge.

### Warum Feld-Diff und Sollwert-Gate verschieden zählen

- **Sollwert-Gate** (`scripts/run_cv_sollwerte_corpus.evaluate`, geprüft von `test_sollwerte_corpus_production_path_all_pass`): Ergebnis pro CV PASS/FAIL. Bei der Ausbildung reicht es, wenn die **erwartete Qualifikation wörtlich (normalisiert) als Teilstring** in der Verkettung `qualification + institution + start_date + end_date` irgendeines Eintrags vorkommt. Feldzuordnung, Institution und Daten werden dafür nicht geprüft.
  - DE_05: Erwartet ist „Kaufmann für Spedition und Logistikdienstleistung (IHK)“. Q2 liefert die Qualifikation ohne „(IHK)“ und „IHK, Nürnberg“ als Institution. Der Teilstring „…logistikdienstleistung (ihk)“ fehlt also, und das Gate scheitert.
  - DE_03: „Höhere Handelsschule“ steht im Institutionsfeld, damit aber in der Verkettung. Das Gate besteht.
- **Feld-Diff** (`diff.py`, QA-Skript): Zählt jedes einzelne Sollfeld als correct / wrong / missing / invented.
  - **Lockerer als das Gate beim Qualifikationswortlaut:** Eine Qualifikation passt, wenn einer der Texte im anderen enthalten ist (in beide Richtungen). Fehlendes „(IHK)“ wird nur als Hinweis `qualification_text_differs` vermerkt und zählt als korrekt. Deshalb steht DE_05 im Feld-Diff mit 36/36, obwohl das Gate dort scheitert.
  - **Strenger als das Gate bei der Feldzuordnung:** Steht die Qualifikation nur im Institutionsfeld, wertet `diff.py` das als `wrong:qualification_in_institution_field`. Institution und Daten werden zusätzlich geprüft. Deshalb ist DE_03 im Feld-Diff falsch, beim Gate aber PASS.
  - Hausnummer im Straßenfeld wird als korrekt mit Hinweis gezählt.
- Fazit: Die Feldzahl (311/312) ist **kein Ersatz für das Gate**. Maßgeblich für „bestanden“ ist das Sollwert-Gate. Der Feld-Diff zeigt zusätzlich Zuordnungsfehler, die das Gate nicht prüft.

## 3. Erfundene Inhalte (Erfindung = Papierkorb)

Grounding-Prüfung (QA-Skript außerhalb des Repos; Ergebnis committet als `docs/qa/pr144_model_compare_2026-10-18/<modell>/GROUNDING.json`): Jeder extrahierte Wert wurde mit dem source_text des Parsers verglichen.
- **Q2_K_XL: keine Erfindungen.** Keine erfundenen Zertifikate, Führerscheine, Arbeitgeber, Abschlüsse oder Daten.
- **Q4_K_M: keine Erfindungen.**
- Nicht wörtlich im Text gefunden, aber belegt (bei beiden Modellen gleich): `end_date = "heute"` (DE_03, EN_01–05). Die Quelle sagt "seit 03.2021" bzw. "Present", "heute" ist also nur normalisiert. Datumsformate wie "03/2021" aus "03.2021" oder "Mar 2022" sind nur umformatiert. "IHK, Nürnberg" (Q2, DE_05) besteht aus Wörtern der Quelle. **Keine Erfindung.**

## 4. Anschreiben (core/cover_quality.py::rewrite_cover_letter, 16 Gold-Fälle mit expected_outcome=interview)

**BLOCKIERT** (vollständiger Lauf mit 16 Fällen nicht durchgeführt). Grund: Laufzeit. Der Smoke-Test mit cl-01 dauerte bei Q4_K_M 215 s und bei Q2_K_XL 248 s pro Fall (2 Modellversuche zu je ca. 100–135 s). Hochgerechnet sind das ca. 57–66 min pro Modell, für beide Modelle ca. 2 h. Das liegt deutlich über dem Zeitrahmen von ~45 min. RAM war unkritisch (Spitze 4559 bzw. 2500 MiB, MemAvailable min. 10 172 MiB).

Smoke-Ergebnis cl-01-dispatch-hafenlogistik (die Rohantworten gehören nicht zu den committeten Belegen):
- **Q4_K_M:** ok=False, reason=review_required, issue=unsupported_personal_claim, **kein Brief zurückgegeben**. Firma (HafenLogistik GmbH), Station (Disponent, Nordkai Spedition GmbH, 2019–2024) und Aufgaben stimmen mit dem Profil überein. Versuch 1 hat aber "SAP TM" fälschlich der Disponenten-Station zugeordnet ("In meiner Zeit als Disponent habe ich … SAP TM … beherrscht"). Im Profil steht SAP TM nur als Software und nicht bei dieser Station. Der Guard hat das abgefangen. Keine erfundenen Zertifikate oder Arbeitgeber.
- **Q2_K_XL:** ok=False, reason=review_required, issue=unsupported_personal_claim, **kein Brief zurückgegeben**. Firma und Station stimmen. Schwächer formuliert: Absätze wiederholen sich wörtlich, Grammatik- und Tippfehler ("die tägliche Abläufe", "einzuglieden"). Die Position wird nur im Schlusssatz genannt ("Dispatcher"). Keine erfundenen Zertifikate oder Arbeitgeber.
- Bewertung Anschreiben: **BLOCKIERT** für beide Modelle. Hinweis: Im einzigen Smoke-Fall hat bei beiden Modellen der Guard gegriffen und es wurde kein versandfähiger Brief erzeugt (UNSICHER, ob das für alle 16 Fälle gilt).

## 5. Ressourcen (VM, nicht i3)

| Lauf | Q2_K_XL | Q4_K_M |
|---|---|---|
| 10 CVs (RUN_ALL10): Spitze RSS / Laufzeit | 2548 MiB / 1351 s | 4603 MiB / 1188 s |
| pytest 24 Tests: Spitze RSS / Laufzeit | 2587 MiB / 1430 s | 4649 MiB / 1231 s |
| Anschreiben-Smoke (1 Fall): Spitze RSS / Laufzeit | 2500 MiB / 249 s | 4559 MiB / 216 s |
| min. MemAvailable | 10 610 MiB | 9 144 MiB |

Q2_K_XL braucht ca. 45 % weniger RAM, ist auf dieser VM aber ca. 10–16 % langsamer.

### RAM-Gate (docs/devops/i3-8gb-peak-rss-gate.md)

- Hartes Gate: Prozessgruppen-Peak **≤ 3 300 000 000 Bytes** (= 3147 MiB).
- **Q4_K_M verfehlt dieses Gate schon auf der VM:** 10-CV-Lauf 4603 MiB, pytest 4649 MiB, Anschreiben-Smoke 4559 MiB. Alle liegen deutlich über 3147 MiB.
- Q2_K_XL liegt auf der VM darunter (2548 / 2587 / 2500 MiB). Das ist **kein** Gate-Nachweis (siehe unten).
- **Peak auf dem i3 ist ungeprüft.** Gemessen wurde nur auf dieser VM. Laut Gate-Dokument sind VM-Zahlen keine Ship-Evidenz; Ship-Evidenz ist nur das Windows Job Object auf dem physischen i3-Laptop.
- **Messgröße:** Hier gemessen wurde die Summe von `ps rss` über den Prozessbaum (1-s-Stichproben, `guarded_run.sh`). Dieser RSS **enthält eingeblendete (mmap) Gewichtsseiten der GGUF-Datei** und ist **nicht gleich dem Job-Object-Commit** (`PeakJobMemoryUsed` / privater Commit), den das Gate zählt. Die Werte sind daher nur grob vergleichbar, in beide Richtungen.
- **Dieser Vergleich ist KEINE Modellempfehlung.**

## 6. Bewertung

| Modell | CV-Extrakt | Matching | Anschreiben |
|---|---|---|---|
| Q4_K_M (4B, Referenz) | **Interview-ready** (Geltungsbereich: nur CV-Extrakt, synthetisches 10-CV-Korpus, n=2 Läufe: 10-CV-Extraktlauf + pytest-Produktionspfad): 12/12 Korpus-Test-IDs grün (24/24 inkl. Fixture-Präsenztests), Sollwert-Gate 10/10 in beiden Läufen, Feld-Diff 312/312 (nur Lauf 1), keine Erfindungen. Hinweis: Hausnummer bei EN-CVs zusätzlich im Straßenfeld (vom Repo-Test toleriert). | **Blockiert** (nicht evaluiert, keine Daten) | **Blockiert** (Laufzeit, siehe 4; Smoke: Guard hat gegriffen, kein Brief) |
| Q2_K_XL (DASLab GSQ 4B) | **Nicht interview-ready / UNSICHER** (Geltungsbereich: nur CV-Extrakt, synthetisches 10-CV-Korpus, n=2 Läufe: 10-CV-Extraktlauf + pytest-Produktionspfad): keine Erfindungen (also kein Papierkorb wegen Erfindung), aber das Sollwert-Gate ist in **beiden** Läufen ROT (9/10, jeweils DE_05 AUSBILDUNG_1). Zusätzlich hat der Feld-Diff in Lauf 1 bei DE_03 die Qualifikation im Institutionsfeld gefunden (das Gate prüft das nicht; für Lauf 2 gibt es keine Feld-Daten). Ein HR-Leser würde eine falsch zugeordnete bzw. unvollständige Qualifikation sehen. | **Blockiert** (nicht evaluiert) | **Blockiert** (Laufzeit; Smoke: Guard hat gegriffen, Text wiederholt sich und hat Grammatikfehler) |
| 8B | Blockiert (nicht evaluiert) | Blockiert | Blockiert |
| 27B | Blockiert (nicht evaluiert) | Blockiert | Blockiert |

## 7. Versand

**Unbeaufsichtigtes Versenden bleibt AUS.** Es darf erst eingeschaltet werden, wenn ein Modell in allen drei Kategorien (CV-Extrakt, Matching, Anschreiben) interview-ready ist. Das einzige „Interview-ready“ in diesem Bericht gilt nur für den CV-Extrakt von Q4_K_M auf dem synthetischen 10-CV-Korpus bei n=2 Läufen. Das trifft auf kein Modell zu: Matching und Anschreiben sind bei allen Modellen blockiert, und Q2_K_XL fällt schon beim CV-Extrakt durch den Sollwerte-Test.

## UNSICHER
- Anschreiben-Qualität über alle 16 Fälle (nur 1 Fall pro Modell als Smoke-Test).
- Q2_K_XL CV-Extrakt: n=2 Läufe. DE_05 scheitert reproduzierbar am Gate. Ob der DE_03-Zuordnungsfehler auch in Lauf 2 auftrat, ist unbekannt (keine Feld-Daten).
- Matching: keine Daten.

## Belege (committet)

Ordner: `docs/qa/pr144_model_compare_2026-10-18/`, Prüfsummen in `docs/qa/pr144_model_compare_2026-10-18/SHA256SUMS` (Prüfung: `cd docs/qa/pr144_model_compare_2026-10-18 && sha256sum -c SHA256SUMS`).
Je Modell: `FIELD_DIFF.json`, `GROUNDING.json`, `pytest_junit.xml`, `RUN_ALL10.stdout.log`, `RUN_ALL10.watchdog.log`, `RUN_PYTEST.stdout.log`, `RUN_PYTEST.watchdog.log`. Für beide Modelle sind alle Dateien vorhanden.

Vor dem Commit durchsucht nach Tokens, Umgebungsvariablen, Box-Hostnamen und echten Personendaten. E-Mails und Telefonnummern stammen aus den fiktiven Fixtures (`example.*`-Domains), Pfade nur unter `/workspace`. **Geschwärzt:** nur der Box-Hostname im junit-Attribut `hostname="…"` beider `pytest_junit.xml`, ersetzt durch `[REDACTED-BOX-HOSTNAME]`. Alle anderen Dateien sind byte-identisch mit den Originalen.

| Datei | geschwärzt | sha256 Original | sha256 committet |
|---|---|---|---|
| `q2_k_xl_4b_gsq/FIELD_DIFF.json` | no | `50b1d548e03dd94ae5849c1faebcc2f4449af8b354524b2626a1c7bc68edf275` | `50b1d548e03dd94ae5849c1faebcc2f4449af8b354524b2626a1c7bc68edf275` |
| `q2_k_xl_4b_gsq/GROUNDING.json` | no | `da34704a3901617487e549699fd32d6babf5d9853701c5f60d699fa3878293ea` | `da34704a3901617487e549699fd32d6babf5d9853701c5f60d699fa3878293ea` |
| `q2_k_xl_4b_gsq/RUN_ALL10.stdout.log` | no | `12b77839dea6ca7dfe364b598ab5834b85f79ebe6ec60b74050d71a067d737ae` | `12b77839dea6ca7dfe364b598ab5834b85f79ebe6ec60b74050d71a067d737ae` |
| `q2_k_xl_4b_gsq/RUN_ALL10.watchdog.log` | no | `44d254b4dfc9a191a616308fcf935cd3f3bb21b49af4fb4cd2a6bd862dbf7776` | `44d254b4dfc9a191a616308fcf935cd3f3bb21b49af4fb4cd2a6bd862dbf7776` |
| `q2_k_xl_4b_gsq/RUN_PYTEST.stdout.log` | no | `5e9e0a75e5e13afcbca858c341fdece0f1478f298d7d72259de532fa1f55bab9` | `5e9e0a75e5e13afcbca858c341fdece0f1478f298d7d72259de532fa1f55bab9` |
| `q2_k_xl_4b_gsq/RUN_PYTEST.watchdog.log` | no | `e7aed2136a1acff225427fd73d5511599a048114d4f40285e706e0b18052fdfc` | `e7aed2136a1acff225427fd73d5511599a048114d4f40285e706e0b18052fdfc` |
| `q2_k_xl_4b_gsq/pytest_junit.xml` | yes | `3c5d0b4686323c92faa7a6005d42d7785cabe1dc5255bc44291d28983ae8f402` | `3ba03cc5243a8955c88fae4987762747424f0885352f6239493bd2ff8de728c2` |
| `q4_k_m_corpus/FIELD_DIFF.json` | no | `00cea45874386f1d01bd1fe02245f3ea89531d9b359e56ce4d40705096b52394` | `00cea45874386f1d01bd1fe02245f3ea89531d9b359e56ce4d40705096b52394` |
| `q4_k_m_corpus/GROUNDING.json` | no | `fa6d6e952975b608387fabfa110ef02d1dcff97b3ba2bb7db4cdebe11c295ffb` | `fa6d6e952975b608387fabfa110ef02d1dcff97b3ba2bb7db4cdebe11c295ffb` |
| `q4_k_m_corpus/RUN_ALL10.stdout.log` | no | `7448808fa0f9dc597f70de12ce55cac92b57733908ebb4167a0513655191439d` | `7448808fa0f9dc597f70de12ce55cac92b57733908ebb4167a0513655191439d` |
| `q4_k_m_corpus/RUN_ALL10.watchdog.log` | no | `f694cf61c6be96a5e5b61ffa4f4564dae96432b4cb9243996ba4462299c51fde` | `f694cf61c6be96a5e5b61ffa4f4564dae96432b4cb9243996ba4462299c51fde` |
| `q4_k_m_corpus/RUN_PYTEST.stdout.log` | no | `b7ce18faf60e94539146299613c032bc842bb530f71960462d83f7b19905a534` | `b7ce18faf60e94539146299613c032bc842bb530f71960462d83f7b19905a534` |
| `q4_k_m_corpus/RUN_PYTEST.watchdog.log` | no | `2acacd97961a090d71eb6fb0a81ce60a4259b4c66ad5ccd167a47b71bf7669d9` | `2acacd97961a090d71eb6fb0a81ce60a4259b4c66ad5ccd167a47b71bf7669d9` |
| `q4_k_m_corpus/pytest_junit.xml` | yes | `1358e073c2599e817028ec44eb305ec0884d0f3b50071ca0b990e8d3487aa434` | `f78022ec6871a674e9c9e04474a7889efecd329665c9590682fac3c353534045` |
