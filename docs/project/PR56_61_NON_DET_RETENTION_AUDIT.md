# PR #56–#61 — Änderungen außerhalb DET / Entscheidung

Bewertet gegen Branch `cursor/docpick-qwen35-cv-replace-d85b` (PR #62).
DET, Phi und C1-Hybrid werden **nicht** erneut aktiviert.

## Entscheidungstabelle

| PR | Entscheidung | Begründung |
|----|--------------|------------|
| **#56** Phi-Extract | **ÜBERHOLT** (kein Merge der Phi-Produktpfad-Teile) | Ancestor von #62. Phi-EXTRACT/WRITE und Verify-als-Produktpfad sind abgelöst. Bereits in #62 enthalten und **behalten**: `core/cv_evidence.py`, `core/cv_document_backends.py`, `core/cv_verify_repair.py` (als Bibliothek), `core/text_normalize.py`, Desktop-Dialog-/Merge-Hilfen, Tests `test_p0_profile_cv_dialogs.py`. **Nicht** übernehmen: Reaktivierung von PHI_EXTRACT im Import. |
| **#57** Holdout-100 | **ÜBERHOLT** für produktiven DET-Routing; **Infrastruktur behalten** | Ancestor von #62. Bereits in #62: `scripts/holdout_scorer_v2.py`, `scripts/run_final_holdout_phase_b_eval.py`, Holdout-Protokolle unter `docs/project/HOLDOUT_*`, `FINAL_HOLDOUT_*`. DET-Pipeline-Auswahl / C1-Hybrid **nicht** aktivieren. Frozen Predictions/Seals nicht überschreiben. |
| **#58** DET multilingual | **ÜBERHOLT** | Keine einzigartigen Dateien gegenüber #62. Inhalt = DET-Post-Analysis (Kenntnisse/Adressen). Würde DET-Extraktion wieder nähren — **kein Cherry-Pick** von `parse_cv_text`-Änderungen. |
| **#59** SmartResume | **ÜBERHOLT** | Ancestor; Smoke-Gate failed. Lizenz-/Phasen0-Docs bereits in Linie. Kein SmartResume-Produktpfad. |
| **#60** Phi vs DET | **ÜBERHOLT** (Vergleichs-Artefakte optional archivieren) | Einzige Dateien **nicht** in #62: `scripts/run_phi_vs_det_compare.py`, `tests/phi_vs_det_compare/*`, zwei Report-Docs. Nur historischer Vergleich; **kein** Phi-Import. Bei Bedarf Docs/Manifest als Archiv cherry-picken — **nicht** nötig für Docpick-Betrieb. |
| **#61** OSS SmartResume | **ÜBERHOLT** | Ancestor; Gate failed; durch #62 ersetzt. Audit-Docs bereits in Linie. |

## Konkret behalten (bereits auf PR #62)

| Datei / Bereich | Funktion |
|-----------------|----------|
| `scripts/holdout_scorer_v2.py` | Unveränderter Scorer V2 (Historie) |
| `scripts/holdout_scorer_v3_complete_gt.py` | Neue Metrik (dieses Audit) |
| `scripts/run_final_holdout_phase_b_eval.py` | Eval-Hilfen / `classify_critical` |
| `core/cv_evidence.py` | Evidenz-Hilfen |
| `core/cv_document_backends.py` | PDF-Backend-Abstraktion |
| `core/text_normalize.py` | Normalisierung |
| `core/cv_verify_repair.py` | Verify/Repair-Hilfen (nicht als DET-Fallback) |
| `desktop/widgets/dialog_geometry.py`, `desktop/services/profile_merge.py` | UI/Import-UX |
| Holdout-/Lizenz-Docs unter `docs/project/` | Nachvollziehbarkeit |

## Nicht übernehmen

- Jede Reaktivierung von `parse_cv_text` / DET-Kenntnisse-Routing
- PHI_EXTRACT als produktiver CV-Pfad
- C1-Hybrid / „DET bleibt Absicherung“-Fallbacks
- Scorer- oder GT-Änderungen, die alte V2-Zahlen nachträglich „reparieren“

## Konflikte

Konflikte allein sind kein Schließgrund. Inhaltlich sind #56–#61 für den
Docpick-Produktpfad **ersetzt**; benötigte Infrastruktur steckt bereits in #62.
Schließung der Draft-PRs kann manuell erfolgen (Forge-Tool in dieser Session
ohne Schreibrecht auf `Karrierekrake`-PRs).
