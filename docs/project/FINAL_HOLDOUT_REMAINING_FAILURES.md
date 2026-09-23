# FINAL HOLDOUT — REMAINING FAILURES

Hypotheses only. **No fixes in Phase B.**

Source: sealed DET predictions `artifacts/final_holdout/frozen_predictions/` vs  
`tests/final_holdout/phase_b_solutions/expected_results.json` (Scorer V2).

## Summary

| Area | Observation | Dominant status |
| ---- | ----------- | --------------- |
| Languages | Predictions have empty `languages` for essentially all docs | missing (100) |
| Employment | Structured `work_experience` often empty (≈46/50 empty in spot check) | missing |
| Skills | Many extra skill tokens not in GT | hallucinated (116) |
| Education | Qualification/institution often merged or wrong field filled | wrong / missing |
| Address | Street often includes house number; country sometimes missing | missing / wrong |
| Critical | `Elternzeit` emitted as education on FH_011 | hallucinated education |

## Hypotheses (not implemented)

1. **Language section routing:** DE/EN language blocks may not be recognized on these layouts; CEFR / Muttersprache lines dropped before `languages[]` is filled.  
2. **Employment vs narrative:** Job lines may land in free-text / skills / education instead of `work_experience` records.  
3. **Skill wrap / section bleed:** Responsibilities and section headers may be tokenized into `skills` → FP hallu.  
4. **Education string fusion:** `qualification | institution` in one field breaks bipartite institution matching.  
5. **Career notes:** Life events (Elternzeit, etc.) classified as education instead of ignored / schema-extension.  
6. **Address country:** Country may be omitted when only city/PLZ visible to DET heuristics.

## Priority for a future Post-Analysis (separate turn)

1. Stop emitting life-events as education (critical).  
2. Restore language extraction on FH layouts (largest missing block).  
3. Recover employment records without inventing employers.  
4. Reduce skill extras without document-specific rules.  
5. Split education qualification vs institution.

## Explicit non-actions this turn

* No parser edits  
* No allowlist growth  
* No re-run of Phase A  
* No scorer relaxation  
* No GT edits
