# Blind-Review Personaler — Befund auf `main`

Datum: 2026-09-24.  
Geprüfter Stand: `origin/main` `cca25fcfb16fc8a23376e52a5f2f1af829ac7142`.  
Prüfmaßstab: `docs/personaler/ABNAHME_CHECKLISTE.md`.  
Arbeitsweise: Lesen der im Baum vorhandenen Fixtures, Gold-Dateien und Scorer-Diffs. Kein Parser-Lauf, keine neu erfundenen Lebensläufe, Matches oder Anschreiben.

Dieser Bericht ändert keinen Anwendungscode. Parser, Qwen, Docling und die Branches zu #62 und #63 sind unberührt. Der Basis-Commit von `main` enthält den bereits gemergten UI-Stand aus #63; diese Runde fügt nur die beiden Dateien unter `docs/personaler/` hinzu.

## Gesamturteil

| Kategorie | Urteil auf den vorhandenen Proben | Unbeaufsichtigter Versand |
|---|---|---|
| CV-Extrakt | **Papierkorb** auf den versiegelten Scorer-Ständen; **Blockiert**, wo der Extrakt oder das benannte Gold fehlt | **Blocker** |
| Matching | **Papierkorb** für die vorhandenen Demo- und Contract-Stubs; **Blockiert**, weil kein Matching-Gold mit Anzeige und bestätigtem Profil existiert | **Blocker** |
| Anschreiben | **Papierkorb** für die gelesenen Proben mit konkreten Fehlbehauptungen. Ein Personaler-Gold für Anschreiben ist **nicht spezifiziert** | **Blocker** |

Kein Kategorie-Satz ist interview-ready. Unbeaufsichtigter Versand ist auf diesem Stand nicht frei.

## 1. CV-Extrakt

Lesbare Extrakt-JSONs (`frozen_predictions`) liegen für die Holdouts nicht im Checkout. `artifacts/mini_holdout_30/LOCAL_PREDICTIONS_PATH.txt` verweist auf gitignorierte Dateien; das Verzeichnis ist nicht vorhanden. Geprüft wurden deshalb die committeten Soll-Dateien und die committeten Feld-Diffs (erwartet gegen tatsächlichen Extrakt). Ein grünes Scorer-Aggregat ohne lesbaren Extrakt wird nicht als Interview-ready gewertet.

### 1.1 `SMOKE_DE_EN_10` — Blockiert

Der Name `SMOKE_DE_EN_10` kommt im Baum nicht vor. Es gibt kein Sample unter diesem Gold-Namen.

Nächstliegendes Korpus: `tests/fixtures/cv_corpus/` (10 fiktive PDFs, 5 DE / 5 EN) plus `expected_results.json`. Die Sollwerte enthalten Name und teilweise Kontakt, aber **keine** Stellenliste mit Titel, Arbeitgeber und Zeitraum und **keine** Abschlusszeilen. Viele Dokumente führen nur `work_count` und `education_count`. Ein abgelegter Parser-Extrakt zu diesen PDFs fehlt. `docs/cv-corpus-acceptance.md` meldet ein automatisches 10/10-`PASS` auf Sektionszählern. Das ist kein Personaler-Blindreview von Stellen, Zeiträumen und Knock-out-Qualifikationen.

Urteil: **Blockiert**. Nicht interview-ready, nicht als Papierkorb der zehn PDFs ausgeschrieben, weil der Extrakt selbst nicht vorliegt.

Quelle ohne gepaarten Extrakt, deshalb ebenfalls nicht gewertet: `tests/fixtures/cv_corpus/Fake_Lebenslauf_Neuer_Blindtest_Leonie_Brandt.txt`.

### 1.2 `MINI_HOLDOUT_30` — Papierkorb (versiegelter Stand)

Vorhanden: `MH_001`–`MH_030` als PDFs in `tests/KarriereKrake_MINI_HOLDOUT_30_PHASE_A_BLIND.zip`, Soll in `tests/KarriereKrake_MINI_HOLDOUT_30_PHASE_B_SOLUTIONS.zip`, Scorer-Diffs unter `artifacts/mini_holdout_30/`.

Versiegelter Diff `artifacts/mini_holdout_30/per_document_results.json`:

| Befund | Wert |
|---|---|
| Dokumente | 30 |
| perfect / perfect_core | 0 / 0 |
| fehlende Felder | 228 |
| halluzinierte Felder | 67, in 28 Dokumenten |
| erfundene Führerscheine | 5 |

Papierkorb-Fälle, erfundene Lizenz (Soll leer, Ist ein zusammengeklebter Block aus Sprachen, Werkzeugen und Skills):

- `MH_002.pdf`, `MH_006.pdf`, `MH_014.pdf`, `MH_018.pdf`, `MH_030.pdf`
- Beleg `MH_002`: Ist beginnt mit `Französisch: B2 Englisch: B1 Programme und Werkzeuge SAP MM - Grundlagen …` im Feld `licenses` (`artifacts/mini_holdout_30/critical_errors.json`).

Weiterer erfundener Fakt, kein Zertifikat: `MH_001.pdf` führt `certificate_extra` mit dem Ist-Wert `Programme und Werkzeuge` sowie `ZBrush - Grundlagen`, Soll `null`. Das ist Abschnitts- und Skilltext, der als Zertifikat in den Extrakt läuft und damit in Matching und Anschreiben weiterlaufen kann.

`artifacts/mini_holdout_30/PHASE_B_COMPLETE.json` setzt `overall_pass` auf false.

Der spätere Diff `artifacts/mini_holdout_30/post_analysis/per_document_results.json` zeigt 26/30 perfect, 0 Halluzinationen und 13 fehlende Adressfelder. Interview-ready verlangt korrekten Kontakt. Diese vier Dokumente scheitern daran:

| Dokument | fehlend |
|---|---|
| `MH_011.pdf` | Straße Rue du Rhône, Hausnummer 54, PLZ 1204, Ort Genève |
| `MH_012.pdf` | Quai de la Goffe 71, 4000 Liège |
| `MH_026.pdf` | Ort Genève |
| `MH_027.pdf` | Quai de la Goffe 84, 4000 Liège |

Dieser Post-Analyse-Diff hebt den versiegelten Papierkorb nicht auf eine Interview-Freigabe: die Extrakt-JSONs fehlen, und vier Profile haben eine unvollständige Anschrift. Beschäftigungs- und Ausbildungszähler in den Metrikdateien ersetzen die Wortlautprüfung von Titel und Zeitraum nicht.

Urteil Kategorie-Sample `MINI_HOLDOUT_30`: **Papierkorb** auf dem versiegelten Extrakt. Post-Analyse zusätzlich **nicht interview-ready**.

### 1.3 `NV3_001`–`NV3_050` — Blockiert

Kein Dateiname, kein Feld und kein Bericht unter `NV3_001` … `NV3_050`. Urteil: **Blockiert** (Gold fehlt).

### 1.4 Weitere Extrakt-Diffs auf demselben `main` (nicht die benannten Golds)

Diese Sätze sind zusätzliche Proben, kein Ersatz für die fehlenden Gold-Namen.

`artifacts/final_holdout/per_document_results.json` (50 Dokumente): 0 perfect, 117 halluzinierte und 39 falsche Felder. Urteil der versiegelten Schicht: **Papierkorb** (erfundene oder falsche Fakten).

`artifacts/final_holdout/post_analysis_remaining/per_document_results.json`: weiterhin 0 perfect. `FH_020.pdf` hat eine falsche E-Mail, Soll `veit.van dijk@example.org`, Ist `dijk@example.org`. Fünf weitere Dokumente (`FH_002`, `FH_012`, `FH_022`, `FH_032`, `FH_042`) verlieren ein Englisch-Level (Soll `B1`, Ist nur noch `C1`). Urteil: **nicht interview-ready** (Kontakt falsch bzw. Sprachlevel unvollständig). Der falsche Mailkontakt ist ein Versandfehler; die versiegelte Schicht bleibt Papierkorb.

`artifacts/final_independent_50_v2/per_document_results.json`: 0/50 perfect, 163 halluzinierte Felder. Urteil: **Papierkorb**.

`artifacts/final_independent_50_v2/post_analysis/final_metrics.json` meldet 1859/1859 Felder correct, Halluzinationsrate 0, 50/50 perfect documents. Die Extrakt-JSONs fehlen (`frozen_predictions` nicht im Baum, analog `LOCAL_PREDICTIONS_PATH.txt`). Stellen, Zeiträume und Abschlüsse sind im Wortlaut nicht lesbar. Urteil dieser Schicht: **Blockiert** für eine Interview-Freigabe. Das Scorer-Aggregat wird nicht als Interview-ready übernommen.

Demo-Profile `mobile/assets/demo/profile_000.json` … `profile_007.json` enthalten Vorname, Nachname, E-Mail und Ort (`A0` / `B0` / `a0@example.com`) und keine Beschäftigung, keinen Zeitraum, keinen Abschluss. Das sind Vertrags-Stubs, keine CV-Extrakte. Urteil: **Blockiert** als Extrakt-Probe.

## 2. Matching

Ein benanntes Matching-Gold (Anzeige, bestätigtes Profil, Ausgabe) ist auf `main` nicht vorhanden. Vorhanden sind nur hart kodierte Gründe.

### 2.1 Mobile-Demo — Papierkorb

`mobile/assets/demo/job_000.json` … `job_039.json` (40 Dateien): Titel `Stelle 0` … `Stelle 39`, Firma `Firma N`, Gründe ausschließlich `skill-0` … `skill-4`. Kein Profilbezug, keine Anforderung aus einer Anzeige. Urteil: **Papierkorb** (Platzhalter statt belegter Begründung).

### 2.2 Desktop-Demo — Papierkorb

`desktop/demo_data.py`, Profil `Alex Muster`, Skills `MS Office`, `Terminplanung`, `Kommunikation`, Titel unter anderem `Teamassistenz`.

| Stelle | Grund im Sample | Befund |
|---|---|---|
| Teamassistenz Vertrieb, Havel Soft AG | `Assistenz-Erfahrung`, `CRM-Nähe` | CRM kommt im Profil nicht vor und ist als Nähe-Treffer gesetzt |
| Office Manager, Nordlicht Consulting GmbH | `Titel passt`, `Hybrid in Pendelreichweite`, `Office-Skills` | Titel und Office liegen im Profil; die Anzeige im Sample hat keine ausformulierte Anforderungsliste |
| Projektkoordination Remote, Kiefer Digital UG | `Remote erlaubt`, `Koordinationsprofil` | Remote ist eine Stellenbedingung, kein belegtes Personenmerkmal |
| Empfangs- und Büromanagement, Spree Klinikverbund | `Büroorganisation` | Büroorganisation ist im Profil nicht genannt |

Der CRM-Treffer ohne CRM im Profil ist eine unbelegte erfüllte Anforderung. Urteil des Satzes: **Papierkorb**.

### 2.3 Contract-Fixture — Papierkorb

`contracts/fixtures/v1/job.valid.json`: Titel `SAP Lohnbuchhalter (m/w/d)`, Firma `Beispiel GmbH`, `description` leer, `match_score` 80, Gründe `✓ Zielberuf` und `✓ SAP`, zugleich `rejection_reasons`: `keine direkte SAP-HCM-Erfahrung`. Kein Profil hängt an der Datei. Score und Haken auf SAP stehen gegen die ausgewiesene SAP-HCM-Lücke. Urteil: **Papierkorb**.

Urteil Kategorie Matching: **Papierkorb** für die vorhandenen Stubs und **Blockiert** als Abnahme-Satz, weil kein Matching-Gold existiert. Beides blockiert unbeaufsichtigten Versand.

## 3. Anschreiben

**Personaler-Gold für Anschreiben ist nicht spezifiziert** und wird hier nicht nachträglich erfunden. `benchmark/cover_specialization/gold_set.jsonl` ist ein Modell-Gold (80 Fälle, `content_sha256` im Manifest `ee44e08b3f71b367b580905f730846a0587e4162bd37f0678b05459afd13df7c`). Es wird als vorhandenes Sample gelesen, nicht als benanntes Abnahme-Gold.

### 3.1 Modell-Gold `gold_set.jsonl` — Papierkorb

Alle 80 Fälle: `verified_plan` null, `allowed_direct_evidence_ids` und `allowed_related_evidence_ids` leer, `ready_as_is` true, kein Feld für Nutzerfreigabe. `ready_as_is` ist keine Freigabe der Endfassung.

Profilzeile 1 in `benchmark/guenther_final_model_shootout_fixture.json` ist der Personenname, nicht der Arbeitgeber. Sechs Briefe machen diesen Namen zum Arbeitgeber (`bei <Name>`):

| Fall | Profil | Entscheidende Behauptung |
|---|---|---|
| `sc_strong_06` | `Fay Retail` / Einzelhandelskaufmann / Kasse, Beratung; Ziel ModeHaus West | `Als Einzelhandelskaufmann bei Fay Retail` — Name wird Arbeitgeber. Zusätzlich `Leidenschaft für Mode`, Mode steht nicht im Profil |
| `sc_med_01` | `Uma Office` / Terminplanung, Korrespondenz, Excel | `die ich bei Uma Office erworben habe` |
| `sc_med_03` | `Wes Project` / Termine, MS Project Grundlagen | `Berufserfahrung als Projektassistenz` und `Tätigkeit bei Wes Project`. Projektassistenz ist die Zielrolle, nicht die belegte Vergangenheit |
| `sc_med_06` | `Zed Help` / First-Level, Windows, Passwort-Resets | `Meine Rolle bei Zed Help` und `multilingualen Umgebung` |
| `sc_career_18` | `Fox Pack` / Kommissionierung — Interesse Schichtleitung | `Kommissionierungsspezialist bei Fox Pack` und `Schichten effektiv zu leiten`. Das Profil nennt Interesse, keine geleitete Schicht |
| `sc_des_06` | `Xia Talent` / Active Sourcing — **kein Personio** | Der Brief behauptet Personio mehrfach: `Erfahrung im Bereich des Personio-Assistenten`, `erfahren in der Nutzung von Personio`. Das widerspricht dem Profil |

Firma und Zielrolle stehen in diesen Betreffs überwiegend korrekt (ModeHaus West, BureauOne GmbH, TicketTree AG, StockLead AG, HireWave KG). Eine falsche Personenbehauptung genügt für Papierkorb. Urteil dieser Proben: **Papierkorb**.

### 3.2 Blind-Set v2 — Papierkorb, obwohl `final_ok`

40 Ausgaben unter `benchmark/guenther_writing_quality_final_raw/final_blind_covers_v2/`, Profile in `benchmark/corpus/guenther_writing_quality_final_fixtures.json` Schlüssel `final_blind_covers_v2`. 32 sind `final_ok: true`. Keine Datei enthält eine Nutzerfreigabe. Acht sind vom Modell geblockt (`UNSUPPORTED_CREDENTIAL`, `JOB_REQUIREMENT_USED_AS_EVIDENCE` oder `EMPTY_OUTPUT`), darunter `fb2_strong_01`, `fb2_strong_03`, `fb2_strong_04`, `fb2_strong_05`, `fb2_strong_08`, `fb2_hard_01`, `fb2_hard_02`, `fb2_des_05`.

Proben mit `final_ok: true` und mindestens einer unbelegten konkreten Behauptung:

| Fall | Profil | Output |
|---|---|---|
| `fb2_strong_02` | `Ben Pack` / Ausbildung Fachlagerist / Kommissionierung, Staplerschein; Ziel Fachlagerist, PackHub SE | Firma und Rolle stimmen. Zusätzlich unbelegt: `in verschiedenen Lagersystemen` und `die Lagerbestände genau zu verwalten`. `final_errors` ist leer, `unsupported_material` false. Der Modell-Haken übersieht die Behauptung |
| `fb2_med_01` | `Ines Desk` / Excel, Ablage, Telefonzentrale; Ziel Office Clerk, AdminCore GmbH | `ein neues System zur Organisation von Dokumenten … Reduzierung des Ablageaufwands um 20%`. Weder System noch 20 % stehen im Profil. `final_ok` true |
| `fb2_career_03` | `Sam Pivot` / Empfang — Transfer Recruiting Koordination | `Empfangstransfer Koordinator bei XYZ Corp` |
| `fb2_career_04` | `Tina Shop` / Einzelhandel — Transfer Logistikkoordination | `bei Tina Shop` — Name als Arbeitgeber |
| `fb2_career_08` | `Xenia Service` / Kundenservice — Transfer Inside Sales; Ziel GlowDesk GmbH | `Während meiner Zeit bei XYZ Company` und `20%igen Steigerung der Kundenbindung` |

Urteil dieser Proben: **Papierkorb**. Stelle und Firma sind in mehreren Fällen richtig; die eine unbelegte Personenbehauptung entscheidet.

### 3.3 Vorlage und Demo-Entwürfe — Blockiert als Anschreiben-Probe

`templates/cover_letter.txt` ist eine Platzhaltervorlage (`{job_title}`, `{company}`, `{experience_sentence}`, `{skills}`, `{full_name}`), kein geschriebenes Anschreiben.

`mobile/assets/demo/draft_000.json` … `draft_014.json` sind Antwortentwürfe (`Körpertext 0`, Betreff `Betreff 0`). Alle 15 haben `approved: false` und `binding_review_approved: false`. Kein Lebenslaufbezug. Urteil: **Blockiert** als Anschreiben-Abnahme.

Urteil Kategorie Anschreiben: die lesbaren Briefe mit konkreten Behauptungen sind **Papierkorb**. Ein interview-ready Brief mit Nutzerfreigabe liegt nicht vor. Das fehlende Personaler-Gold ist ein eigener **Blocker** für unbeaufsichtigten Versand.

## 4. Offene Blocker für unbeaufsichtigten Versand

1. `SMOKE_DE_EN_10` fehlt. `NV3_001`–`NV3_050` fehlen.
2. Holdout-Extrakte sind als JSON nicht im Baum; Scorer-Aggregate ersetzen die Wortlautprüfung nicht.
3. Versiegelte Extrakt-Diffs von `MINI_HOLDOUT_30`, Final-Holdout und Independent-50 enthalten erfundene Felder.
4. Matching-Gold mit Anzeige und bestätigtem Profil fehlt. Die vorhandenen Gründe sind Platzhalter oder unbelegt (`CRM-Nähe`, SAP-Widerspruch).
5. Anschreiben-Gold für die Personaler-Abnahme ist nicht spezifiziert. Die vorhandenen Briefe enthalten unbelegte Arbeitgeber, widersprochene Tools (Personio) und erfundene Kennzahlen, teilweise bei `final_ok: true` und `ready_as_is: true`. Eine Nutzerfreigabe der Endfassung fehlt in allen gelesenen Proben.

## 5. Nicht Gegenstand dieser Runde

Keine Änderung an Parser, Qwen, Docling, Scrapern, RAM-Gates, Qt-UI oder Python-Laufzeit. Keine Bearbeitung der Branches oder Diffs zu #62 und #63. Keine neu geschriebenen Musterinhalte, um Lücken zu füllen.
