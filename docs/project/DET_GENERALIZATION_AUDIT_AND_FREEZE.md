# DET Generalization Audit and Freeze

**Status:** `POST-ANALYSIS TARGET ACHIEVED – INDEPENDENT 0.99 NOT YET PROVEN`

## Unveränderliche Ergebniswahrheit

| Messung | F1 | Hallucination | Perfect Core |
|---------|-----|---------------|--------------|
| **Frozen Independent V2 (gültig)** | **0.7246** | **0.0983** | **0/50** |
| IH2 Post-Analysis (nicht unabhängig) | 1.0000 | 0 | 50/50 |

Der Post-Analysis-Wert ist **kein** unabhängiger Erfolgsnachweis und darf nicht als Frozen-0.99 zitiert werden.

---

## Phase 1 – Diff-Inventar (`3c9f5bd` → freeze candidate)

Ausgangscommit unabhängiger Parser-Stand: `3c9f5bd7cfdac328221c0a3bfae614501f82032c`  
Produktive Parserdateien: `core/cv_parser.py`, `core/cv_sections.py`  
Scorer: `scripts/holdout_scorer_v2.py` (siehe Phase 4)

| Änderung | Datei/Funktion | Fehlerklasse | Allgemeine Regel | Risiko | Betroffene Felder |
|----------|----------------|--------------|------------------|--------|-------------------|
| FR/NL/EN Employment-Headings | `cv_sections.HEADINGS[experience]` | Section Detection | Mehrsprachige Berufsabschnitte | low | employment |
| FR/NL/EN Education-Headings inkl. `Education / Ausbildung` | `cv_sections.HEADINGS[education]` | Section Detection | Bilinguale Edu-Überschriften | low | education |
| Languages & Mobility / Langues / Talen | `cv_sections.HEADINGS[languages]` | Section Detection | EU-Sprachsektionen | low | languages |
| Applications / Programme, Outils, Logiciels | `cv_sections.HEADINGS[software]` | Section Detection | Tool-Sektionen FR/NL/EN | low | software |
| Core Competencies / Compétences / Vaardigheden | `cv_sections.HEADINGS[skills]` | Section Detection | Skill-Sektionen FR/NL/EN | low | skills |
| Profile stoppers FR/NL | `cv_sections.HEADINGS[profile]` | Section Detection | Zusatzinfo-Stopper | low | boundary |
| COMPOSITE_REST_OK mobility/programme/ausbildung | `cv_sections._COMPOSITE_REST_OK` | Section Detection | Composite-Überschriften | low | multi |
| Muttersprachen-Aliase in Level-Norm | `_normalize_lang_level` | Languages / Normalization | moedertaal/langue maternelle/… → `native` | low | languages |
| Endonyme in `_KNOWN_LANGUAGES` | `_KNOWN_LANGUAGES` | Languages | EU-Autonyme (čeština, nederlands, …) | med* | languages |
| Software dump filter | `_looks_like_non_software_dump` | Software / Cross-Field | Datum/Heading/Middot-Skills ≠ Software | low | software |
| Software accept heuristic | `_accept_software_item` | Software | Section + Tool-Struktur, kein Allowlist-only | med | software |
| Software wrap proficiency | `_join_software_wrap_lines` | Software / Reading Order | `Tool -` + Level-Zeile | low | software |
| Slash-Listen `/` | `_parse_software` | Software | `A / B / C` unter Tools | low | software |
| Notion/-tion Fix | `_accept_software_item` | Software | Kurze `tion`-Produkte ≠ Skill-Morphologie | low | software |
| Microsoft 365 Wrap | `_route_labeled_kenntnisse_lines` | Software / Reading Order | `Microsoft` + `365` zusammenführen | low | software |
| Skills middot vor EMP_LEAK | `_parse_skills` | Skills / Entry Boundary | `•`/`·` → Skills, nicht Emp | low | skills |
| Kein Skill-Steal aus Software TitleCase | `parse_cv_text` relocate | Cross-Field Validation | Revit bleibt Software | med | software/skills |
| Rijbewijs/Permis Labels | `_inline_licence_mentions` | Normalization | NL/FR Licence-Labels | low | licenses |
| Same-line licence only | `_inline_licence_mentions` | Cross-Field Validation | Kein Capture über Newline (Türkisch→T) | low | licenses |
| Skip language lines in `_parse_driving` | `_parse_driving` | Cross-Field Validation | Sprache ≠ Klasse | low | licenses |
| Bare `Klasse C` ohne Kontext entfernt | `_inline_licence_mentions` | Cross-Field Validation | Schule/Theorie ≠ Licence | low | licenses |
| Certificaten/Certificats | labeled cert route | Normalization | NL/FR Zertifikat-Labels | low | certificates |
| Né(e)/Geboren DOB | `_DOB` | Normalization | FR DOB-Marker | low | personal |
| EU City Unicode + PL/spaced/optional street | `_CITY_CHARS`, `_POSTAL_*` | Normalization | Strukturelle PLZ-Formate | med | address |
| Scorer native-level aliases | `holdout_scorer_v2._native_level_aliases` | Scoring/Testcode | Muttersprachen-Synonyme beim Match | med** | languages score |

\*Endonym-Liste ist taxonomisch, nicht IH2-Wert-Kopie; unbekannte Sprachen in klarer Sektion bleiben strukturell möglich über CEFR-Paare.  
\*\*Scorer-Änderung: siehe Phase 4 (Dual-Score).

Keine Zeile mit `IH2_`, Dateiname, Dokument-ID, Hash-Routing oder Layout-Klasse in `core/`.

---

## Phase 2 – Leakage-/Hardcoding-Audit

### Suche (Produktion `core/`)

| Muster | Treffer Produktion | Einstufung |
|--------|-------------------|------------|
| `IH2_` / IH2-Dateinamen | keine | — |
| Personennamen / Adressen / Arbeitgeber IH2 | keine (Kommentare bereinigt) | — |
| `expected_results` / `solution_sheet` | keine | — |
| `document_id` / `layout_class` Parse-Routing | keine | — |
| Holdout-Runner ändert Parse-Logik | nein | — |

### Semantik

| Stelle | Einstufung | Entscheidung |
|--------|------------|--------------|
| Mehrsprachige Headings | GENERALIZABLE | KEEP |
| Software-Section-Heuristik (TitleCase, Proficiency) | OVERFIT_RISK (strukturell begründet) | KEEP + kontrastierende Tests |
| `_KNOWN_LANGUAGES` Endonyme | GENERALIZABLE | KEEP |
| EU-PLZ-Muster (PL `NN-NNN`, spaced, 4-digit city-only) | GENERALIZABLE | KEEP |
| Scorer native aliases | GENERALIZABLE (Scoring) | KEEP; Dual-Score dokumentiert |
| Bare `Klasse X` / Newline nach Fahrerlaubnis | DIRECT_LEAKAGE-Risk (Halluzination) | **ENTFERNT/VERSCHÄRFT** |
| IH2-Städtenamen in Parser-Kommentaren | OVERFIT_RISK (Doku) | **ENTFERNT** |

**Direkte Datenlecks:** 0 (nach Audit)  
**Entfernte dokumentbezogene Regeln:** 0 (keine ID-Hacks vorhanden); entfernt wurden halluzinogene Licence-Muster und IH2-Beispielkommentare.

---

## Phase 3 – Kontrastierende Tests

Neu: `tests/test_det_generalization_guards.py`  
Abdeckung: Software (IH2-like / unknown / wrong section / no heading / Notion / wrap / Organisation), Languages (CEFR, endonym, C1 isolation, FR/NL), Skills, Employment, Licence vs BE/C1, Address structural.

---

## Phase 4 – Scorer-Audit

### Änderung seit `3c9f5bd`

Nur `_native_level_aliases`: mappt mehrsprachige Muttersprachen-Begriffe auf `native` beim Language-Pair-Match.  
**Kein** Entfernen von Feldern, **kein** Ignorieren von Extras, **keine** IH2-only Toleranz, **kein** Index-Matching.

### Dual-Score IH2 Post-Analysis (aktueller Parser)

| Scorer | F1 | Perfect Core |
|--------|-----|--------------|
| Aktuell (mit Aliases) | 1.0000 | 50/50 |
| Vorher (nur `muttersprache`→native) | 0.9891 | 10/50 |

Differenz ≈ Language-Level-Label-Matching (`moedertaal`/`langue maternelle` in GT vs Parser-`native`).  
Parser-Verbesserungen tragen den Großteil des F1-Sprungs; Scorer erklärt ~0.011 F1 und Perfect-Core-Lücke.

**Scorer unverändert:** nein (Aliases hinzugefügt; begründet und dual gemessen).

---

## Phase 5 – Korpus-Regressionen (DET-Kandidat, Re-Import)

Quelle: `artifacts/det_candidate_regression/regression_summary.json`  
Frozen Predictions wurden **nicht** überschrieben.

| Korpus | F1 | Precision | Recall | Hallu | Perfect | Perfect Core | Invented critical | Wall | Peak RSS | Phi | C1 |
|--------|-----|-----------|--------|-------|---------|--------------|-------------------|------|----------|-----|-----|
| Holdout 100 | 0.9986 | ~0.999 | ~0.998 | 0.0007 | 89 | 89 | 2 (`S/4HANA`, `InDesign` vs GT) | ~2.2s | ~45 MB | 0 | 0 |
| Final Holdout 50 | 0.9985 | ~0.999 | ~0.998 | 0.0000 | 44 | 44 | 0 | ~1.3s | ~45 MB | 0 | 0 |
| Mini Holdout 30 | 1.0000 | 1.0 | 1.0 | 0 | 30 | 30 | 0 | ~0.8s | ~45 MB | 0 | 0 |
| IH2 V2 Post-Analysis | 1.0000 | 1.0 | 1.0 | 0 | 50 | 50 | 0 | ~1.2s | ~45 MB | 0 | 0 |

### Bekannte Vorschäden

| Test | Status | Einfluss der neuen Änderungen |
|------|--------|-------------------------------|
| `test_cv_corpus` EN_02 Skills-Count 5&lt;6 | **unverändert fehlend** (schon bei `3c9f5bd`) | nicht verschlechtert |
| `test_cv_corpus` EN_05 Skills | **jetzt grün** (war 2&lt;8 bei `3c9f5bd`) | verbessert |
| `test_cv_import_replace` Straße `Technologiering 5` vs House-Number-Split | **unverändert fehlend** | Vorschaden, nicht neu |
| DE_04 Software Notion | temporär regressiert, durch `-tion`-Fix behoben | behoben |

Unit: Guards + Metamorphic + Licence/Address + Phi-Removal — grün.

---

## Phase 6 – Metamorphic Tests

Datei: `tests/test_det_metamorphic.py`  
Section-Shuffle, Leerzeilen/Bullets, Heading-Case, FR/NL Muttersprachen-Äquivalenz, Software-Wrap, Unknown Tool/Skill, C1/BE/B Nicht-Licence, Unicode Ort/Arbeitgeber, keine `document_id`/`layout_class`-Parameter, Datumsvarianten.

**Ergebnis:** bestanden. Robustheitstests ≠ unabhängiger 0.99-Nachweis.

---

## Phase 7 – KEEP / REVERT

| Änderung | Entscheidung |
|----------|--------------|
| Alle Section-/Language-/Software-/Address-Regeln oben | **KEEP** |
| Scorer native aliases | **KEEP** (mit Dual-Score-Transparenz) |
| Bare Klasse / Newline-Licence-Capture | **REVERT/REMOVE** (Halluzination) |
| IH2-Kommentar-Beispiele | **REVERT** (Doku-Scrub) |

---

## Phase 8 – Freeze

| Feld | Wert |
|------|------|
| Branch | `cursor/ih2-det-kenntnisse-fix-d85b` |
| Ausgangscommit | `3c9f5bd7cfdac328221c0a3bfae614501f82032c` |
| Finaler Parser-Commit | *(siehe Git nach diesem Freeze-Commit)* |
| Parser-Quellcode-Hash (SHA-256 über Parser-Quellen) | `feece3bdf434e720cf696b1159d508f0a83363f678f89ba048972a33126d71f9` *(vor Freeze-Commit; nach Commit neu berechnen und hier ergänzen)* |
| Phi-Aufrufe | 0 |
| C1-Aufrufe | 0 |
| Neuer unabhängiger 0.99-Nachweis | **nein** |

Parser-Quellen im Hash: `cv_parser.py`, `cv_sections.py`, `cv_intelligence.py`, `cv_extract.py`, `cv_verify_repair.py`, `cv_evidence.py`.

---

## Phase 9 – Neuer Blindtest-Runner

`scripts/run_final_external_style_holdout_phase_a.py`

- Dataset-ID: `FINAL_EXTERNAL_STYLE_HOLDOUT`
- 50–100 PDFs, content-addressed `EXT_<sha12>`
- PDF-Manifest SHA-256, Prediction-Manifest, Repeat, Runtime/RSS, Phi/C1, Seal
- **Keine** Evaluation in Phase A, **kein** GT-Lesen
- Keine Annahmen zu Dateinamen, Sprache, Layout, Personen, Toolnamen
- `--dry-ready` ohne Dataset: Runner bereit, **keine Predictions**

Phase B: separat; ohne unbekannten Datensatz keine Erfolgsmetrik.

---

## Klare Aussage

Der DET-Kandidat ist auditiert und für den **nächsten unabhängigen Blindtest** eingefroren.  
**Es liegt noch kein neuer unabhängiger Frozen-Nachweis für F1 ≥ 0.99 vor.**  
Letzter gültiger unabhängiger IH2-Wert bleibt **F1 0.7246**.
