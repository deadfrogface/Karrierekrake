# HOLDOUT_100_REMAINING_FAILURES

Post-analysis A5 still **far below 99 %** (Field Acc ≈ 0.63, Perfect Docs 0/100).

## Top residual classes

| Class | Typical cause | Stage | LoRA likely? |
|-------|---------------|-------|--------------|
| software missing | Tools not listed with `Software:` label / novel names | DET skills/software | Maybe |
| skill extras | Soft labels / prose fragments | DET | Prefer rules |
| employment missing | Multi-job layouts / title-company swaps | DET experience | Maybe |
| address incomplete | Missing street when only city present (intentional traps) | DET — correct UNCERTAIN | No |
| target_role as employment | Trap still fires on some docs | DET | Rules |
| languages missing | Nonstandard language section layouts | DET/Phi | Maybe |
| education missing | Unusual date/open-ended wording beyond `ohne Abschluss` | DET | Rules first |

## Ground-truth review candidates

None auto-filed in this cycle (`artifacts/holdout_100/ground_truth_review_candidates.json` = `[]`).  
If traps expect `UNCERTAIN` for invalid dates, parser currently omits rather than marking UNCERTAIN explicitly — acceptable as non-hallucination.

## Next technical steps

1. Expand labeled-line routing for EN synonyms (`Systems:`, `Tools:`).
2. Stronger employment/education date-first parsers for holdout layouts.
3. Explicit UNCERTAIN markers for invalid dates.
4. Fresh **private** CV holdout before any global % claim.
5. Collect hard negatives into `training_candidates.jsonl` only after rule plateau.
