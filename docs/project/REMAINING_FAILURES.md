# PHI Extraction — Remaining Failures

Corpus: `CV_Parser_Sollwerte_Vollstaendig.txt` (10 fictional PDFs)  
Measured: 2026-09-22 via `scripts/run_phi_extraction_baseline.py --both`

## Summary

On the authoritative Sollwerte corpus:

| Mode | Perfect docs | Field accuracy | Hallucinations |
|------|--------------|----------------|----------------|
| Deterministic + verify/repair | **10/10** | **1.000** | **0** |
| + PHI_EXTRACT (temp=0, split languages) | **10/10** | **1.000** | **0** |

**No remaining field failures on this corpus.**  
`artifacts/phi_extraction/training_candidates.jsonl` is therefore empty (header comment only).

## Out-of-corpus / residual risks (not counted as corpus fails)

| Class | Docs | Stage | Notes | LoRA likely? |
|-------|------|-------|-------|--------------|
| Novel multi-column layouts beyond DE_02/EN_02 | unknown real CVs | document extract | CURRENT pypdf layout heuristics still fragile on unseen layouts | Maybe later |
| OCR / scanned PDFs | none in corpus | document extract | No OCR path | Separate feature |
| pymupdf4llm markdown as sole input | all 10 | document→parser | 0/10 perfect when replacing CURRENT text — do **not** default | No — wrong format for heuristics |
| Docling | n/a | not installed | Skipped (heavy); re-benchmark before adopting | Unknown |
| PHI_WRITE bio claims | synthetic unit | validate_writing | Hardening added for Führung/SAP/Führerschein/Master | Prefer validators |

## Recommendation

≥99 % on the binding Sollwerte set is **measured as 100 %** for DET and PHI.  
Do not claim global real-world 99 % without a private/real CV holdout. Next: private Windows EXE smoke + optional Docling ablation if RAM budget allows.
