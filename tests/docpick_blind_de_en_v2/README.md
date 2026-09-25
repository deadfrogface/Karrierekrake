# Docpick Blind DE/EN v2 — NV3_50 (Phase A)

**Status:** Phase A corpus installed (NV3_001–NV3_050). GT **not** present.

## Corpus

- 50 synthetic DE/EN CVs (supplier: 25/25), IDs `NV3_001`…`NV3_050`
- Source zip: `PHASE_A_PDFS.zip` (`PDF_SHA256_MANIFEST.json` verified)
- Previously shared CVs excluded by supplier

## Protocol

1. **Freeze** Round7 parser/model/prompt/scorer (commit + file/model hashes)
2. **Phase A:** extract each PDF once → `frozen_predictions/` + `PHASE_A_EXTRACTION_SEAL.json`
3. Stop; request `PHASE_B_SOLUTIONS.zip`
4. **Phase B:** verify seal, then score once — no parser change between A and B

## Commands

```bash
python scripts/run_docpick_blind_de_en_v2_sealed_extract.py
# after PHASE_B_SOLUTIONS.zip:
python scripts/run_docpick_blind_de_en_v2_sealed_score.py
```

`phase_b_solutions/` must be absent/empty during Phase A.
