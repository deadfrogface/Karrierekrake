# Phase 3 – Parser-Weiterentwicklung (Zwischenstand)

## Budget (vor finalem Blindtest, Agent-VM CPU)

| Größe | Grenze | Begründung |
|-------|--------|------------|
| Laufzeit/CV (warm LLM) | ≤ **120 s** praktikabel; Ziel ≤ **60 s** | gemessen ~100–118 s LLM |
| Peak RSS Import | ≤ **3,5 GB** | Round2 Peak 3,2 GB; Baseline 2,45 GB |
| UI-Freeze | **0 s** (Extract im Worker) | Phase 2 erfüllt |

## Bekannte Daten (Round2) — Regression, kein Blind-0,99

Freeze `72ea744` / Score V3.1: **F1 0,989**, Perfect Core **23/40**, 19 missing / 7 wrong / 1 hallucinated, Ø **87,8 s**, Peak **3,2 GB**.

Dominante Missing-Ursache: `employment.end_date` erwartet ``heute`` (Present/current nicht gemappt).

## Änderungen (allgemein, kein Doc-Hardcoding)

1. Schema-Beschreibungen: `position` = Titel only; `end_date` = ``heute`` bei laufend; incomplete education.
2. System-Prompt: Diakritika, Titel vs. Duties, ``heute``, abgebrochene Ausbildung.
3. Post-Norm: Present/current/… → ``heute``; ``ohne Abschluss``.

## Error-Cluster Re-Extract (7 bekannte Docs mit fehlendem ``heute``)

`tests/docpick_qwen35/phase3_error_cluster/CLUSTER_REEXTRACT.json`

- **heute_hits: 7/7**
- MH_009 / MH_029: `qualification=Studium abgebrochen` wieder da
- MH_025: Software weiterhin leer (Minitab/Qlik Sense) — Restfehler
- Wall ~582 s / 7 CVs, Peak RSS ~1,7 GB

**Kein F1 auf dem Vollkorpus neu berechnet** in diesem Schritt (voller 40er-Lauf ≈ 1 h). Cluster belegt die Ursache-Fix-Richtung.

## Unabhängiger Blindtest

**Nicht durchgeführt / F1≥0,99 nicht behauptet.**

Nächster Nachweis braucht:

1. Code/Modell/Prompt/Scorer einfrieren
2. Unberührten DE/EN-Korpus mit vollständiger GT
3. Erst PDFs → versiegelte Predictions, dann GT + Score

Kandidat für späteren Blindlauf: `Fake_Lebenslauf_Neuer_Blindtest_Leonie_Brandt.pdf` (+ ggf. neuer versiegelter Satz) — **nicht** Round2/Mini-Holdout als „neu“ verkaufen.

## Architektur-Empfehlung falls Blind < 0,99

- Restfehler: Jobtitel vs. Aufgaben-Bullets, Diakritika (Célina/Mikołaj), Software-Recall
- Nächster Wechsel: stärkeres/quantisiertes Modell **oder** Zwei-Pass (Titel/Daten getrennt), nicht DET
