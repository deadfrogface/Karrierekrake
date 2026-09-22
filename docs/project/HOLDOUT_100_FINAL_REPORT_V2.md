# HOLDOUT_100 – Final Report V2

Korrigierte Bewertung nach Scorer-Audit. Historische V1-Berichte bleiben erhalten und werden hier eingeordnet – **nicht** gelöscht.

```
RESULT: SCORER V2 VALIDATED – FROZEN HOLDOUT BELOW 99 %
```

## Scorer-Audit

* V1 wertete produktive Profilfelder plus Trap `target_role_not_employment` auf (nahezu) allen Dokumenten.
* Testmetadaten (`document_id`, `filename`, `layout`, `region_note`, `traps`, `missing`, `expected_status`, `language`) flossen **nicht** in Acc/F1 ein.
* Evidence-lose `target_role`-Erwartungen und indexbasiertes Employment/Education-Matching verzerrten Rankings (C1 wirkte besser als DET).
* Details: `docs/project/HOLDOUT_100_SCORER_AUDIT.md`.

## Änderungen am Scorer

| Änderung | Begründung | Tests |
|----------|------------|-------|
| Metadaten nie scorebar | keine Parserfelder | `test_metadata_*`, `test_unsupported_metadata_*` |
| `target_role` evidence-gated (14/100) | nur sichtbare Labels | `test_target_role_*` |
| Bipartites Entry-Matching | Reihenfolge ≠ Fehler | `test_employment_*` |
| Language+Level-Paare | Swap = wrong | `test_language_level_swap_*` |
| Sets order-independent + Duplikate | Produktmodell | `test_set_*`, `test_duplicates_*` |
| Null/leer vs. Halluzination | FP/FN-Klarheit | `test_null_*` |
| Perfect ignoriert Metadaten | Fairness | `test_perfect_*` |
| Primärmetrik P/R/F1 auf evaluierbaren Fakten | kein TN-Aufblasen | `test_aggregate_*` |

Implementierung: `scripts/holdout_scorer_v2.py`, Runner `scripts/run_holdout_scorer_v2.py`.

## Integritätsnachweis

* Vor Neubewertung: `artifacts/holdout_100/FROZEN_PREDICTIONS_INTEGRITY.json` (1527 Dateien, SHA-256, Größe, mtime).
* Nach Neubewertung: `FROZEN_PREDICTIONS_INTEGRITY_VERIFY.json` → `{ "ok": true, "mismatches": [] }`.
* Frozen Predictions wurden nicht regeneriert oder überschrieben.
* `expected_results_full.json` unverändert; Projektion in `evaluation_manifest_v2.json`.

## Frozen Scorer V1 vs. V2

| Pipeline | V1 Acc / F1 | V2 Acc / F1 | Perfect V1→V2 |
|----------|------------:|------------:|---------------|
| DET A5 | 0.474 / 0.643 | **0.557 / 0.715** | 0→0 |
| C1 hybrid | **0.525 / 0.689** | 0.548 / 0.708 | 0→0 |
| Phi B4 verify | 0.507 / 0.673 | 0.530 / 0.692 | 0→0 |
| Phi B1 only | 0.438 / 0.610 | 0.378 / 0.549 | 0→0 |
| D2 pymupdf DET | 0.305 / 0.467 | 0.291 / 0.451 | 0→0 |

Vollständige Matrix: `artifacts/holdout_100/scorer_v1_vs_v2_comparison.json`.

## Post-Analysis Scorer V1 vs. V2

| | V1 | V2 |
|--|---:|---:|
| A5 Kenntnisse-Routing Acc | 0.629 | **0.698** |
| F1 | 0.773 | **0.822** |
| Perfect | 0/100 | **17/100** |

Echte Verbesserung vs. Frozen DET V2: F1 +0.107, Perfect +17. Bleibt **POST-ANALYSIS REGRESSION RESULT**.  
KEEP: generalisierbares Kenntnisse-Routing (keine Dateinamen-Hacks).

## Feldgruppen (Frozen DET A5 V2)

Siehe `scorer_v2_frozen_results.json` → `by_group`. Schwach: Software (missing), Skills (hallu), Employment (missing entries), Address country.

## Perfect Matches

* V1 und Frozen V2: **0/100**
* Ursache war **nicht** Testmetadaten, sondern Extraktionsfehler
* Post-Analysis V2: **17/100**; Rest vor allem Skills/Software/Employment

## C1-Fallback

Routing-Signal (vor GT): DET `languages` **oder** `education` **oder** `work_experience` leer → **64 Docs**.

| | DET auf Subset | C1 auf Subset |
|--|---------------:|--------------:|
| Acc | 0.425 | 0.451 |
| F1 | 0.597 | **0.622** |
| Hallu | 0.263 | 0.268 |

Nettogewinn F1 ≈ +0.025, Hallu leicht ↑. Laufzeit C1 ≫ DET (~21 s vs ~0.01 s/Doc global).  
**Entscheidung:** `KEEP_C1_FALLBACK` nur als schmaler Uncertain-Fallback; **Standard bleibt DET A5**. Dateiname/GT dürfen Routing nicht steuern.

## Phi

* Frozen V2: unter DET und unter/ähnlich C1; Laufzeit 27–50 s/Doc
* Halluzinationen höher als DET; Precision bei B1 hoch, Recall schwach
* **Kein Standard**; kein entscheidender Nettogewinn auf Frozen nach Scorer V2
* Fallback-Arbitration (C4/C5) spiegelt Phi-Product – kein Vorteil vs. DET

## Gewinner

| Rolle | Wahl |
|-------|------|
| Bester Frozen Score (V2) | **DET A5** (F1 0.715) |
| Bester Post-Analysis Score (V2) | **DET A5 + Kenntnisse-Routing** (F1 0.822) |
| Empfohlener Standard | DET A5 (+ Post-Analysis-Routing in Produktcode) |
| Empfohlener Fallback | C1 nur bei „DET dünn“ (leere languages/education/work) |
| Verworfen als Default | Phi-always-on, pymupdf4llm-alone, Docling/Marker (N/A) |

## Ehrliche Interpretation

| Kategorie | Befund |
|-----------|--------|
| Alter Scorer | Trap + Index-Matching; Metadaten unschuldig an Acc |
| Echte Parserfehler | Software missing, Skill extras, Employment gaps |
| Ground-Truth | `target_role` oft ohne PDF-Evidence (86/100 nicht evaluierbar) |
| Schema-Gaps | target_role ↔ SearchIntent optional |
| Performance | DET ~0.01 s; C1/Phi Größenordnungen langsamer |
| vs. 99 % | Frozen und Post-Analysis klar darunter |

## Artefakte

* `docs/project/HOLDOUT_100_SCORER_AUDIT.md`
* `docs/project/HOLDOUT_100_FROZEN_REEVALUATION_V2.md`
* `docs/project/HOLDOUT_100_REMAINING_FAILURES_V2.md`
* `tests/holdout_100/evaluation_manifest_v2.json`
* `artifacts/holdout_100/FROZEN_PREDICTIONS_INTEGRITY.json`
* `artifacts/holdout_100/schema_mapping_v2.json`
* `artifacts/holdout_100/evidence_manifest_v2.json`
* `artifacts/holdout_100/evidence_manifest_v2_qa.json`
* `artifacts/holdout_100/scorer_v1_reproduction.json`
* `artifacts/holdout_100/scorer_v2_frozen_results.json`
* `artifacts/holdout_100/scorer_v2_post_analysis_results.json`
* `artifacts/holdout_100/scorer_v1_vs_v2_comparison.json`
* `artifacts/holdout_100/c1_fallback_analysis_v2.json`
* `tests/test_holdout_scorer_v2.py`
