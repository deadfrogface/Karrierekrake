# Language Extraction Root Cause (POST-ANALYSIS)

**Corpus:** Final-Holdout 50 CVs as Post-Analysis Development and Regression Corpus  
**Frozen baseline (immutable):** Accuracy 0.674 · F1 0.805 · Languages F1 0.000 · Perfect Core 0/50  
**Audit commit reference:** `00674c3`

## Summary

The Languages F1 of 0.000 is not a ground-truth or scorer defect. The productive DET path fails at **section heading detection**: the corpus uses composite language/licence headings that `is_heading()` did not classify as `languages`. Language lines were therefore absorbed into the previous section (usually `education`), `_parse_languages` received an empty body, and `languages[]` stayed empty. Driving licences still appeared via full-text `_inline_licence_mentions`, which masked the section-routing failure for licences only.

## Pipeline stage

```text
PDF text → split_named_sections / is_heading  ← FAILURE
         → _parse_languages(sections["languages"])
         → licence harvest / reclassification
         → canonical output
```

Responsible stage: **Section Detection** (`core/cv_sections.py`).

## Heading survey (50/50 documents)

| Raw heading | Count | `is_heading` before fix | Effect |
| --- | ---: | --- | --- |
| `Sprachen & Fahrerlaubnis` | 45 | `None` | Body routed under prior section (education) |
| `Languages & licences` | 5 | `None` | Same |

No document used a bare `Sprachen` / `Languages` heading. Recognised language-section count before fix: **0/50**.

## Root-cause table

| Cause | Documents | Expected languages | Actual output | Responsible stage | General fix possible? |
| --- | ---: | --- | --- | --- | ---: |
| Composite DE heading `Sprachen & Fahrerlaubnis` not in aliases / `_COMPOSITE_REST_OK` | 45 | Language/level pairs + licence line | `languages=[]`; licence often still via full-text regex | Section Detection | Yes — accept licence tokens as composite rest after `sprachen`/`languages` |
| Composite EN heading `Languages & licences` not recognised | 5 | Same pattern (EN heading, mixed DE/EN names) | `languages=[]` | Section Detection | Yes — same composite rest (`licences`/`licenses`/`driving`) |
| Language body never parsed → pairs never formed | 50 | e.g. Deutsch/Muttersprache, Englisch/A2 | Empty list | Language pairing (starved input) | Yes — follows from heading fix |
| Licence lines under mixed section reclassified as certificates when heading *is* languages | latent | Licence classes only | `Führerschein:…` → certificates | Cross-field / reclassification | Yes — skip licence lines in language reclass; harvest into `driving_license` |
| Bare CEFR vs licence C1 confusion | rare (e.g. `Führerschein: B, C1`) | Language C1 vs licence C1 by line label | Full-text licence path OK when labelled; language path empty before fix | Line classification | Yes — label/partner/evidence based (already partially present) |

## Non-causes (ruled out)

- Ground-truth language labels are present and consistent.
- Scorer V2 language matching works when predictions are non-empty (audit: empty-level bug fixed separately; Languages F1=0 was empty predictions).
- Frozen predictions correctly reflected empty `languages[]`.
- Licence extraction was not the primary failure mode for this corpus.

## Intended general fix (no document IDs)

1. Normalize heading punctuation (en/em dash → space).
2. Treat licence-related tokens as valid composite rest after language headings.
3. Add a few general aliases (`language skills`, `kenntnisse sprachen`, `skills languages`, …).
4. In language bodies: skip licence lines for language parse/reclass; harvest classes into `driving_license`.
5. Keep software/IT context from treating Python/R/etc. as human languages.

## Out of scope here

- FH_011 (Elternzeit as education) — separate iteration after language decision.
- Productive Phi integration — only after measured comparison.
