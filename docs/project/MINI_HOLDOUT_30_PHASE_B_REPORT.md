# Mini Holdout 30 — Phase B Report (Sealed Evaluation)

**Status:** `RESULT: INDEPENDENT MINI-HOLDOUT BELOW 99 %`  
**Dataset:** `MINI_HOLDOUT_30` (`MH_001`–`MH_030`)  
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
| Seal file SHA-256 | `4cc27cb7e08b5c384f5096d9b1048271db907b8b91d4510095f3603b40c927c4` — **PASS** |
| Manifest SHA-256 | `da50d4559e12f32bfa06eeb445b2964389f22b5a50331824fad7e644a873851d` — **PASS** |
| Prediction hash mismatches | **0** |
| PDF hash mismatches | **0** |
| Prediction count | 30 |
| Ground-truth count | 30 |
| Precheck (`documents=30`, empty `duplicate_languages` / `invalid_emails` / `unexpected_fields`) | **PASS** |
| `import_cv` / `parse_cv_text` | **0** |
| `extract_text` (evidence only) | 30 |
| Phi / C1 / writer | **0** |
| Parser changes | **0** |
| Prediction changes | **0** |
| Ground-truth changes | **0** |
| Phase-A artefacts overwritten | **no** |

Scorer SHA-256: `9aeb89887b952aff40ab7a47123260972618e70ef7d84fca001a8f315f4e435c`  
GT SHA-256: `61f0db6997161d6684daaade7470777e0f28cf16d580c4389ecb5317ee0aeda5`  
Integrity file: `artifacts/mini_holdout_30/PHASE_B_INTEGRITY.json`

### Commits

| Role | Commit |
|---|---|
| Parser (DET content) | `918998ca341551ad03eabc834ba73cac24b16119` |
| Phase-A runner | `d5c3f42299256eb4447d3c6980f304091b0cdc42` |
| Phase-A seal | `9cea54c2bab7e591abfd5d5a03eab0cb94f7a3f7` |
| Scorer audit ancestry | `00674c3` |

---

## Datensatz

| Property | Value |
|---|---|
| Documents | 30 |
| IDs | `MH_001.pdf` … `MH_030.pdf` |
| GT package | `tests/KarriereKrake_MINI_HOLDOUT_30_PHASE_B_SOLUTIONS.zip` |
| GT path | `tests/mini_holdout_30/phase_b_solutions/` |
| Field scope | name, address, DOB, email/phone, target_role, languages, licenses, employment, education, certificates, software, skills |
| Document language | de=26, en=4 |
| Pages | 1-page=23, 2+=7 |
| Layout classes | 0–11 (2–3 docs each) |

Test metadata (`document_id`, filename, layout, language, source_type) was **not** counted in Accuracy/F1.

---

## Gesamtmetriken (Scorer V2)

| Metric | Value | Target | Pass |
|---|---:|---:|:---:|
| Normalized Field Accuracy | **0.7463** | ≥ 0.99 | no |
| Strict Scalar Accuracy* | 0.9293 | (secondary) | — |
| Precision | 0.9283 | — | — |
| Recall | 0.7920 | — | — |
| **F1** | **0.8548** | ≥ 0.99 | no |
| Hallucination Rate | **0.0576** | ≤ 0.01 | no |
| Missing Field Rate | 0.1960 | — | — |
| Wrong Category Rate | 0.0000 | — | — |
| False Positive Rate | 0.0576 | — | — |
| Duplicate Rate | 0.0000 | — | — |
| Perfect Documents | **0 / 30** | — | — |
| Perfect Core Profiles† | **0 / 30** | — | — |
| Documents with critical errors | **5** | 0 | no |
| Correct facts | 868 | — | — |
| Missing facts | 228 | — | — |
| Hallucinated facts | 67 | — | — |
| Wrong values | 0 | — | — |
| Wrong category | 0 | — | — |
| Field universe | 1163 | — | — |

\* Strict scalar accuracy covers personal/contact/address/DOB scalars only (casefold+trim).  
  Normalized accuracy is the full Scorer-V2 universe. They are **not** the same fact set; see scorer audit.  
† Scorer `perfect_document(core_only=True)` excludes only `career_intent`; with this corpus it matches full Perfect Documents.

**Ziel erreicht: nein.**

---

## Feldgruppen

| Group | Precision | Recall | F1 | Hallu | Facts |
|---|---:|---:|---:|---:|---:|
| Contact | 1.000 | 1.000 | **1.000** | 0.000 | 56 |
| Employment | 1.000 | 1.000 | **1.000** | 0.000 | 300 |
| Education | 1.000 | 1.000 | **1.000** | 0.000 | 175 |
| Personal | 1.000 | 0.919 | 0.958 | 0.000 | 86 |
| Address | 1.000 | 0.908 | 0.952 | 0.000 | 141 |
| Licences | 0.844 | 1.000 | 0.915 | 0.156 | 32 |
| Languages | 1.000 | 0.767 | 0.868 | 0.000 | 60 |
| Certificates | 0.195 | 1.000 | 0.326 | 0.805 | 77 |
| Skills | 1.000 | 0.233 | 0.378 | 0.000 | 133 |
| Software | 1.000 | 0.107 | **0.193** | 0.000 | 103 |

**Weakest field group:** Software (F1 0.193) — dominated by missing software values.  
Certificates: high hallucination (section/skill text pulled into certificates).  
Languages: 14 missing language/level pairs (recall 0.767); 0 language hallucinations.  
Licences: 5 documents hallucinate licence text when GT expects none (languages/software blob in `driving_license`).

---

## Slices (with document counts)

| Slice | n docs | Acc | F1 | Hallu |
|---|---:|---:|---:|---:|
| lang:de | 26 | 0.734 | 0.847 | 0.060 |
| lang:en | 4 | 0.829 | 0.907 | 0.039 |
| pages:1 | 23 | 0.751 | 0.858 | 0.068 |
| pages:2+ | 7 | 0.731 | 0.844 | 0.025 |
| address:de | 20 | 0.745 | 0.854 | 0.061 |
| address:foreign_or_other | 10 | 0.749 | 0.856 | 0.050 |
| address:complete | 27 | 0.744 | 0.853 | 0.060 |
| address:incomplete | 3 | 0.776 | 0.874 | 0.031 |
| contact:complete | 26 | 0.751 | 0.858 | 0.058 |
| contact:missing_or_partial | 4 | 0.715 | 0.834 | 0.058 |
| employment:1 | 10 | 0.722 | 0.839 | 0.059 |
| employment:multi | 20 | 0.756 | 0.861 | 0.057 |
| education:1 | 25 | 0.743 | 0.853 | 0.054 |
| education:multi | 5 | 0.759 | 0.863 | 0.074 |
| target_role:present | 5 | 0.778 | 0.875 | 0.069 |
| target_role:absent | 25 | 0.739 | 0.850 | 0.055 |
| c1_context | 12 | 0.742 | 0.852 | 0.045 |
| layout_class:0 … 11 | 2–3 each | 0.686–0.805 | 0.814–0.892 | varies |

**Weakest slice (enough facts):** `layout_class:3` (n=3, F1 0.814) — small slice; not a general claim.

---

## Kritische Fehler

| Kind | Count | Documents |
|---|---:|---|
| invented_licence | 5 | MH_002, MH_006, MH_014, MH_018, MH_030 |

Pattern: GT has empty licences; prediction places a multi-line languages/software/skills blob into `driving_license`.  
No invented employment, education, personal names, or language records under the critical classifier.  
Wrong employment/education values: **0**. Employment/Education record matching: **perfect** on this corpus.

---

## Perfect-Core-Verteilung (error buckets)

| Bucket | Documents |
|---|---:|
| 0 errors | **0** |
| 1 error | **0** |
| 2 errors | **0** |
| 3–5 errors | **1** |
| >5 errors | **29** |

Nearly all documents fail Perfect Core primarily via **software / skills missing** and/or **certificate hallucinations**, not via employment/education identity errors.

---

## Vergleich

| Corpus | Method | F1 | Perfect / Perfect Core | Note |
|---|---|---:|---:|---|
| 100-CV | Post-Analysis | 0.998 | 89/100 Perfect | Development corpus after visible analysis — **not** independent frozen proof |
| 50-CV Final Holdout | Post-Analysis after Phase B | 0.9985 | Perfect Core 44/50 | Tuned on revealed Final Holdout — **not** independent |
| **30-CV Mini Holdout** | **Frozen Phase A → Phase B** | **0.8548** | **0/30 / 0/30** | **Independent sealed test of DET candidate `918998c`** |

Post-Analysis high scores do **not** transfer to this independent mini-holdout.

---

## Ehrliche Schlussfolgerung

1. Seal and predictions are intact; evaluation is valid.  
2. Independent frozen DET performance on 30 new CVs is **well below 99 %** (F1 ≈ 0.85, Acc ≈ 0.75, hallu ≈ 0.058).  
3. Strengths: employment, education, contact are essentially perfect here.  
4. Weaknesses: software/skills recall, certificate over-extraction, residual language-pair misses, licence blob hallucinations (5 docs).  
5. **No global ≥99 % claim** is justified by this holdout.  
6. **No parser fixes, no second Phase A, no GT edits** were performed in Phase B.

Artefacts:

- `artifacts/mini_holdout_30/phase_b_results.json`
- `artifacts/mini_holdout_30/per_document_results.json`
- `artifacts/mini_holdout_30/per_field_results.json`
- `artifacts/mini_holdout_30/field_group_metrics.json`
- `artifacts/mini_holdout_30/slice_metrics.json`
- `artifacts/mini_holdout_30/error_inventory.json`
- `artifacts/mini_holdout_30/critical_errors.json`
- `artifacts/mini_holdout_30/PHASE_B_INTEGRITY.json`
- `docs/project/MINI_HOLDOUT_30_REMAINING_FAILURES.md`
