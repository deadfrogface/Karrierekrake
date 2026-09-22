# HOLDOUT_100 – Scorer-Audit (V1 → V2)

Audit des bisherigen Holdout-Scorers (`scripts/evaluate_holdout_100.py`) gegen produktive KarriereKrake-Profildaten. Original-GT `tests/holdout_100/expected_results_full.json` unverändert.

## Was V1 bewertet hat

V1 baut pro Dokument Fakt-Zeilen aus:

* Skalare Profilfelder (Name, Kontakt, Adresse, DOB)
* Sprachen, Lizenzen, Skills, Software, Zertifikate (Listen)
* Education / Employment **indexbasiert** (Position `i` vs. Prediction `i`)
* Zusätzlich immer: Trap-Feld `target_role_not_employment` (Zielrolle darf nicht in Employment stehen)

**Nicht** in `field_total` eingeflossen (geprüft im Code): `document_id`, `filename`, `layout`, `region_note`, `traps`, `missing`, `expected_status`, `language` (Dokumentmetadatum).

## Numerischer Metadaten-/Trap-Einfluss

| Effekt | Einfluss auf Acc/F1? | Beleg |
|--------|---------------------:|-------|
| Testmetadaten als erwartete Parserfelder | **Nein** | Keine Rows in `evaluate_document` |
| `target_role_not_employment` auf (nahezu) allen Docs | **Ja** | +~100 Rows / Pipeline; A5: 40× `wrong_category`, C1: 97× |
| Anteil Trap an A5 `field_total` | ~2,8 % | 100 / 3544 |
| Evidence-lose `target_role` als Extraktionsziel | indirekt über Trap | PDF-Evidence nur bei 14/100 Docs (V2) |

Fazit: Die großen Verzerrungen kamen **nicht** von `document_id`/`layout`/…, sondern vom **durchgängigen Target-Role-Trap** und von **indexbasiertem Entry-Matching**.

## Feld-für-Feld

| Ground-Truth-Feld | Bisher bewertet? | Parser-Zielfeld | Im PDF sichtbar? | Produktives Profilfeld? | Künftig werten? | Begründung |
| ----------------- | ---------------: | --------------- | ---------------: | ----------------------: | --------------: | ---------- |
| `document_id` | Nein | — | n/a | Nein | Nein | Testmetadatum |
| `filename` | Nein | — | n/a | Nein | Nein | Testmetadatum; Dateiname ≠ Evidence |
| `layout` | Nein | — | n/a | Nein | Nein | Testmetadatum / Slice |
| `region_note` | Nein | — | n/a | Nein | Nein | Testmetadatum |
| `traps` | indirekt (Logik) | — | n/a | Nein | Nein | Verwaltungsnotiz; Trap-Logik war Scoring-Regel, nicht Extraktionsfeld |
| `missing` | indirekt | — | teils | Nein | nur als Absenz-Annotation | steuert erwartete Abwesenheit |
| `expected_status` | Nein | — | n/a | Nein | Nein | CONFIRMED/UNCERTAIN-Klassifikation |
| `language` (de/en) | Nein | — | n/a | Nein | Nein | Dokumentsprachen-Metadatum ≠ `languages[]` |
| `name.first_name` | Ja | `personal.first_name` | ja (Corpus) | Ja | Ja | Core |
| `name.last_name` | Ja | `personal.last_name` | ja | Ja | Ja | Core |
| `email` | Ja | `emails[0]` | wenn nicht in `missing` | Ja | Ja | Core |
| `phone` | Ja | `phones[0]` | wenn nicht in `missing` | Ja | Ja | Core |
| `dob` | Ja | `personal.date_of_birth` | ja | Ja | Ja | Core |
| `address.street` | Ja | `personal.street` | meist | Ja | Ja | Core |
| `address.house_number` | Ja | `personal.house_number` | oft nur in Straßenzeile | Ja | Ja | Evidence über Straßenzeile erlaubt |
| `address.postal_code` | Ja | `personal.postal_code` | meist | Ja | Ja | Core |
| `address.city` | Ja | `personal.city` | meist | Ja | Ja | Core |
| `address.country` | Ja | `personal.country` | oft nur implizit DE | Ja | Ja | Alias DE/Deutschland |
| `languages` | Ja | `languages` | wenn Sektion vorhanden | Ja | Ja | Paare Sprache+Level |
| `licenses` | Ja | `driving_license` | wenn vorhanden | Ja | Ja | Core |
| `education` | Ja (Index) | `education` | wenn vorhanden | Ja | Ja | V2: bipartites Matching |
| `employment` | Ja (Index) | `work_experience` | wenn vorhanden | Ja | Ja | V2: bipartites Matching |
| `skills` | Ja | `skills` | variabel | Ja | Ja | Set, order-independent |
| `software` | Ja | `software` | variabel | Ja | Ja | Set |
| `certificates` | Ja | `certificates` | variabel | Ja | Ja | Set |
| `target_role` | indirekt als Trap | `target_role` / SearchIntent | **nur 14/100 explizit** | Optional (B) | **nur mit PDF-Evidence** | kein Dateiname, keine Ableitung aus Jobs |

## Problematische V1-Vergleiche

1. **Employment/Education nach Listenindex** – Vertauschung = Doppel-Fehler.
2. **Language-Level** – Membership ohne strikte Paarung riskiert Swap-Blindheit (V1 list_membership auf Strings).
3. **`target_role_not_employment`** – bewertet eine Policy auf allen Docs, nicht Extraktion sichtbarer Zielrollen.
4. **Accuracy inkl. vieler trivialer Korrektheiten** – Quality-Score mit Hallu-Gewichtung; V2 priorisiert Precision/Recall/F1 auf evaluierbaren Fakten.
5. **Leere Listen** – teils als korrekt gewertet wenn beide leer (ok); fehlende vs. leere Prediction inkonsistent je Feld.

## Schema-Mapping (Soll)

Siehe `artifacts/holdout_100/schema_mapping_v2.json` und `tests/holdout_100/evaluation_manifest_v2.json`.

## Feldklassen

* **A – CORE:** Name, Kontakt, Adresse, DOB, Languages, Licenses, Education, Employment, Skills, Software, Certificates  
* **B – OPTIONAL:** `target_role` nur mit sichtbarem Label (`Berufswunsch` / `Zielposition` / …)  
* **C – METADATA:** die acht Verwaltungsfelder oben – nie in Acc/F1/Perfect

## Reproduktion V1

`artifacts/holdout_100/scorer_v1_reproduction.json`: A5 Acc **0.474** / F1 **0.643**, C1 Acc **0.525** / F1 **0.689**, Perfect **0/100** – reproduziert.
