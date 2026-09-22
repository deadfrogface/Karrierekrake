# Final Holdout (independent)

**Status:** Infrastructure ready — dataset not yet provided.

```
tests/final_holdout/
├── cvs/                     # 30–50 untouched CVs (to be supplied)
├── expected_results.json    # Ground truth (ONLY for Phase B)
└── README.md                # this file
```

## Rules

1. Do **not** generate expected results from parser output.
2. Phase A (`scripts/run_final_holdout_predictions.py`) may read **only** `cvs/`.
3. Phase B (`scripts/evaluate_final_holdout.py`) reads sealed predictions + GT + Scorer V2.
4. After first evaluation, this set becomes a regression corpus — further independent proof needs a **new** holdout.

See `docs/project/FINAL_HOLDOUT_PROTOCOL.md`.

## Dataset requirements (summary)

- 30–50 fully new CVs (no reused persons / employer combos / layout colour variants)
- DE + EN; 1–4 pages; 1–3 columns; tables/sidebars
- Missing fields, overlapping dates, self-employment, mini-jobs, parental leave, etc.
- No real PII
- OCR/scan cases marked separately

## Commands

```bash
python scripts/run_final_holdout_predictions.py   # Phase A — seals hashes
python scripts/evaluate_final_holdout.py          # Phase B — verifies seals, scores
```
