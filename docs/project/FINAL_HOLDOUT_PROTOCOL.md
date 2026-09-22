# FINAL_HOLDOUT_PROTOCOL

Unabhängiger Final-Holdout (30–50 CVs) — versiegelt, zweiphasig.

## Ziel

Belastbare Messung der **produktiven DET-Pipeline** auf einem unangetasteten Datensatz, der nicht zur Entwicklung genutzt wurde.

Korrekte Erfolgsformulierung (nach Auswertung):

> Auf dem unabhängigen synthetischen Final-Holdout wurden mindestens 99 % erreicht.

Keine unbegrenzte globale Garantie.

## Verzeichnisstruktur

```text
tests/final_holdout/
├── cvs/
├── expected_results.json   # nur Phase B
└── README.md

artifacts/final_holdout/
├── frozen_predictions/
├── FROZEN_METADATA.json
├── FROZEN_HASHES.json
├── PHASE_A_COMPLETE.json
├── EVALUATION_RESULTS.json
└── PHASE_B_COMPLETE.json
```

## Phase A — blinde Predictions

Befehl: `python scripts/run_final_holdout_predictions.py`

Darf lesen:

* `tests/final_holdout/cvs/`

Darf **nicht** lesen:

* `tests/final_holdout/expected_results.json`

Erzeugt versiegelte Predictions + Metadata + SHA-256-Hashes.

Pipeline: produktives `import_cv` (DET only, `phi_extract_call_count == 0`).

## Phase B — Auswertung

Befehl: `python scripts/evaluate_final_holdout.py`

Voraussetzung: gültiges Phase-A-Siegel.

Liest: versiegelte Predictions, Ground Truth, Scorer V2.

Darf **nicht**: Predictions neu erzeugen/ändern, Parser anpassen, GT ändern.

Bei Hash-Mismatch: Abbruch.

## Leakage-Schutz

1. Phase A öffnet GT nicht (Runtime-Guard).
2. Produktionscode importiert `expected_results.json` nicht.
3. Dateinamen steuern keine Extraktionsregeln.
4. GT-Pfad wird nicht an `parse_cv_text` / `import_cv` übergeben.
5. Predictions werden gehasht und in Phase B verifiziert.
6. Git-Commit und Dirty-State werden in Metadata dokumentiert.
7. Nach Phase B ist der Holdout nicht mehr „ungesehen“ (`PHASE_B_COMPLETE.json`).

## Dataset-Anforderungen

* 30–50 vollständig neue CVs
* keine Wiederverwendung bisheriger Personen / Arbeitgeberkombinationen
* keine bloßen Farb-/Namensvarianten alter Layouts
* unterschiedliche Typografie und Abschnittsreihenfolgen
* 1–/2–/3-spaltig, Tabellen, Seitenleisten, Textboxen, 1–4 Seiten
* Deutsch und Englisch; DE/grenznahe/ausländische Adressen
* fehlende Felder, überlappende Zeiträume, laufende/abgebrochene Ausbildung
* Selbstständigkeit, Minijob, Praktikum, Elternzeit, Arbeitslosigkeit
* parallele Tätigkeiten, Quereinstieg, seltene Berufe
* Software/Skills mit Level; C1-Sprache und C1-Führerschein
* unbekannte Software, ungewöhnliche Überschriften, echte Mehrdeutigkeit → `UNCERTAIN`
* absichtlich fehlende Kontaktdaten; **keine realen PII**
* Scan/OCR separat markieren und auswerten

## Nach der ersten Auswertung

* Frozen-Ergebnis unverändert speichern
* Fixes ⇒ Post-Analysis; kein nachträgliches „Frozen“
* Datensatz wird Regressionstest; neuer unabhängiger Nachweis braucht neuen Holdout

## Mindestziel (nach späteren echten Runs)

* F1 ≥ 0.99, Accuracy ≥ 0.99, Hallucination ≤ 0.01
* keine kritischen erfundenen Berufserfahrungen / Ausbildungen / Qualifikationen
