# Final Independent Holdout 50 V2 — Phase B Report (Sealed Evaluation)

**Status:** `RESULT: FINAL INDEPENDENT 50 V2 BELOW TARGET`  
**Dataset:** `FINAL_INDEPENDENT_50_V2` (`IH2_001`–`IH2_050`)  
**Pipeline evaluated:** sealed `DET_PRODUCTION` predictions only  
**Scorer:** `scripts/holdout_scorer_v2.py` (audited; unchanged)  
**Ground truth mutated:** no  
**Predictions mutated:** no  
**Parser mutated:** no  
**Re-extraction / Phi / C1:** 0  

---

## Integrität

| Check | Result |
|---|---|
| Seal file SHA-256 | `79a1a80a8e0a1dc85e47dd9afde710cfa52dcb9053a97df74726b7cfbb663b09` — **PASS** |
| Manifest SHA-256 | `f5fe1390d7750e48033b6a1e5c2f96d765d8aa9b965b3ea8e980427a6bca1a39` — **PASS** |
| Prediction hash mismatches | **0** (before and after scoring) |
| PDF hash mismatches | **0** |
| Prediction count | 50 |
| Ground-truth count | 50 |
| Precheck (`documents=50`, empty `duplicate_languages` / `invalid_emails` / `unexpected_fields`) | **PASS** |
| `import_cv` / `parse_cv_text` | **0** |
| Phi / C1 / writer | **0** |
| Parser changes | **0** |
| Prediction changes | **0** |
| Ground-truth changes | **0** |
| Phase-A artefacts overwritten | **no** |

Scorer SHA-256: `9aeb89887b952aff40ab7a47123260972618e70ef7d84fca001a8f315f4e435c`  
GT SHA-256: `f4fecbb175ae687297f56b115d8de05fb716d35ada603f44e5e29b0b20b45dba`  
Integrity file: `artifacts/final_independent_50_v2/PHASE_B_INTEGRITY.json`

### Commits

| Role | Commit |
|---|---|
| Parser (DET content ancestor) | `3c9f5bd7cfdac328221c0a3bfae614501f82032c` |
| Phase-A runner | `520eb11e50f8ec36b332a7106861a0e3712485b6` |
| Phase-A seal | `aa6fb96d7ac3b83dbe46c46e663d293887a17bb4` |
| Scorer | unchanged (`holdout_scorer_v2.py`) |

---

## Datensatz

| Property | Value |
|---|---|
| Documents | 50 |
| IDs | `IH2_001.pdf` … `IH2_050.pdf` |
| GT package | `tests/Karrierekrake_FINAL_INDEPENDENT_50_V2_PHASE_B_SOLUTIONS.zip` |
| GT path | `tests/final_independent_50_v2/phase_b_solutions/` |
| Predictions | `artifacts/final_independent_50_v2/frozen_predictions/` (sealed Phase A) |

Test metadata was **not** counted in Accuracy/F1.

---

## Gesamtmetriken (Scorer V2)

| Metric | Value | Target | Pass |
|---|---:|---:|:---:|
| Normalized Field Accuracy | **0.5682** | ≥ 0.99 | no |
| Strict Scalar Accuracy* | 0.9151 | (secondary) | — |
| Precision | 0.8494 | — | — |
| Recall | 0.6318 | — | — |
| **F1** | **0.7246** | ≥ 0.99 | no |
| Hallucination Rate | **0.0983** | ≤ 0.01 | no |
| Missing Field Rate | 0.3311 | — | — |
| Wrong Category Rate | 0.0000 | — | — |
| False Positive Rate | 0.1007 | — | — |
| Perfect Documents | **0 / 50** | — | — |
| Perfect Core Profiles | **0 / 50** | — | — |
| Documents with critical errors | **34** | 0 | no |
| Correct facts | 942 | — | — |
| Missing facts | 549 | — | — |
| Hallucinated facts | 163 | — | — |
| Wrong values | 4 | — | — |
| Wrong category | 0 | — | — |
| Field universe | 1658 | — | — |

\* Strict scalar accuracy covers personal/contact/address/DOB scalars only.  
Normalized accuracy is the full Scorer-V2 universe.

**Ziel erreicht: nein.**

---

## Feldgruppen

| Group | Precision | Recall | F1 | Hallu | Notes |
|---|---:|---:|---:|---:|---|
| contact | 1.000 | 1.000 | **1.000** | 0.000 | stable |
| career_intent | 1.000 | 1.000 | **1.000** | 0.000 | n=2 |
| personal | 1.000 | 0.921 | **0.959** | 0.000 | mostly stable |
| certificates | 1.000 | 0.900 | **0.947** | 0.000 | 5 missing |
| address | 0.981 | 0.897 | **0.938** | 0.000 | 4 wrong / 24 missing |
| licenses | 1.000 | 0.818 | **0.900** | 0.000 | 10 missing |
| employment | 0.950 | 0.831 | **0.886** | 0.042 | 13 invented employment |
| education | 1.000 | 0.647 | **0.785** | 0.000 | 41 missing |
| software | 0.293 | 0.395 | **0.336** | **0.489** | 150 extras, 95 missing |
| languages | 1.000 | 0.164 | **0.282** | 0.000 | 107 missing |
| skills | 1.000 | 0.068 | **0.127** | 0.000 | 206 missing |

Weakest field group: **skills** (F1 0.127).  
Weakest slice (among slices with enough facts): **lang:nl**.

---

## Kritische Fehler

| Kind | Count (hallucinated) |
|---|---:|
| `invented_software` | **150** |
| `invented_employment` | **13** |
| **Total critical invented** | **163** |
| Documents affected | **34 / 50** |

Dominant software extras include section headings / competency labels dumped as software (e.g. `Kompetenzprofil` and similar structural tokens) — structural routing failure on this independent corpus, not scorer noise.

---

## Dominante Fehlerklassen (ohne Fixes)

1. **Skills missing** — largest miss volume (206); section/entry generalisation does not cover this holdout’s skill headings/structures.
2. **Software hallucinations** — 150 extras; high hallu rate; headings and non-tool tokens enter software.
3. **Languages missing** — 107 misses; language block recall collapses on this corpus (precision remains 1.0).
4. **Education / employment gaps** — education misses; some invented employment rows.
5. **Stable areas** — contact perfect; personal/certificates/licenses/address relatively strong vs Kenntnisse.

---

## Regression / Prozessgarantien

| Check | Result |
|---|---|
| Sealed predictions only | yes |
| No parser edits in Phase B | yes |
| No re-import / re-parse | yes (`import_cv_calls=0`) |
| Phi / C1 | 0 |
| Prior Mini-30 frozen seal | untouched |
| Prior Final-50 / Holdout-100 | untouched |

---

## Artefakte

| File | Path |
|---|---|
| Results | `artifacts/final_independent_50_v2/phase_b_results.json` |
| Per document | `artifacts/final_independent_50_v2/per_document_results.json` |
| Per field | `artifacts/final_independent_50_v2/per_field_results.json` |
| Field groups | `artifacts/final_independent_50_v2/field_group_metrics.json` |
| Slices | `artifacts/final_independent_50_v2/slice_metrics.json` |
| Error inventory | `artifacts/final_independent_50_v2/error_inventory.json` |
| Critical | `artifacts/final_independent_50_v2/critical_errors.json` |
| Integrity | `artifacts/final_independent_50_v2/PHASE_B_INTEGRITY.json` |
| Complete marker | `artifacts/final_independent_50_v2/PHASE_B_COMPLETE.json` |

---

## Ehrliche Einordnung

1. Dies ist der **unabhängige Frozen-Test** des DET-Stands nach Licence/Software/Skills/Cert-Fixes (`3c9f5bd`).
2. Post-Analysis auf Mini-30 (F1 ≈ 0.994) **generalisiert nicht** auf diesen neuen Korpus.
3. Hauptbruch: **Kenntnisse-Routing** (Skills missing, Software hallu, Languages missing).
4. Contact/Personal bleiben stark — stabile Bereiche nicht das Problem.
5. Nächster Schritt (separater Auftrag): Root-Cause auf Frozen-Fehler inventarisieren; **keine** stillen Fixes ohne neuen Blindtest.

```text
RESULT: FINAL INDEPENDENT 50 V2 BELOW TARGET
```

Holdout is no longer unseen. Further parser fixes require a new independent holdout after any change.
