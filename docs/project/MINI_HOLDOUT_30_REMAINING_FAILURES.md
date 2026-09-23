# Mini Holdout 30 — Remaining Failures (Phase B, no fixes)

Documentation only. Predictions, scorer, parser, and ground truth were **not** changed.

## Summary

Independent sealed evaluation of DET candidate `918998c` on `MH_001`–`MH_030`:

| Metric | Value |
|---|---:|
| F1 | 0.8548 |
| Normalized Accuracy | 0.7463 |
| Hallucination Rate | 0.0576 |
| Perfect Documents | 0/30 |
| Perfect Core (scorer def.) | 0/30 |
| Critical invented events | 5 (licences) |

## Error mass by group

| Group | Dominant failure | Count (approx.) |
|---|---|---:|
| Skills | missing | 102 |
| Software | missing | 92 |
| Certificates | hallucinated extras | 62 |
| Languages | missing pairs | 14 |
| Address | missing components | 13 |
| Personal | missing (mostly DOB/name) | 7 |
| Licences | hallucinated when GT empty | 5 |

Wrong values / wrong category: **0** across the corpus.

## Hypotheses (not fixes)

1. **Software / Skills recall gap**  
   Many GT software and skill tokens are not emitted by DET on these synthetic layouts (composite “Programme und Werkzeuge” / “Fachkompetenzen” blocks). Post-analysis on the Final-50 corpus overfitted visible patterns; this independent set still misses most set members.

2. **Certificate hallucinations**  
   Long free-text or neighbouring section content is classified as certificates (`certificate_extra:*`). High precision failure (P≈0.20) despite perfect recall on true certificates.

3. **Licence field pollution (critical)**  
   On five documents with empty GT licences, `driving_license` contains a concatenated blob of languages + tools + skills. Scorer marks this as licence hallucination / invented_licence.

4. **Language pair misses**  
   14 missing language/level pairs (7 docs × typically both languages). Language-heading fixes from Final-50 help some cases but do not generalise to all MH layouts.

5. **Address / name / DOB gaps**  
   A minority of documents miss city/street/house/postal or DOB/name — not dominant vs software/skills, but enough to keep Perfect Core at zero even if soft fields were ignored under a narrower core definition.

## What worked

- Employment record matching: **300/300** correct facts  
- Education record matching: **175/175** correct facts  
- Contact email/phone: **56/56**  
- No employment↔education confusions, no wrong dates/companies/institutions in the scored universe

## Perfect-Core blockers

Under the audited Scorer V2 definition (`perfect_document(core_only=True)` only skips `career_intent`), **every** document fails — almost always via software/skills/certificates, often also languages or licences.

Documents whose *only* error groups are `{software, skills, certificates}`: **17/30**.  
Even on those, Perfect Core remains false under the current scorer definition.

## Explicit non-actions

- No parser rule changes  
- No second prediction run  
- No scorer loosening  
- No ground-truth edits  
- Any remediation requires a **separate** mandate and a **new** independent holdout afterward
