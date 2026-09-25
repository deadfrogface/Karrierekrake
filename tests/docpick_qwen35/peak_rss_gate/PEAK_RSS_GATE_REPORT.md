# Peak-RSS Hard Gate (≤ 3.3 GB)

- **Target:** Intel Core i3 (11th gen), 8 GB RAM
- **Gate:** ≤ **3.3 GB** (hard fail above) — soft ≤12 GB is obsolete
- **PDF:** `tests/fixtures/cv_corpus/DE_01_Klassisch.pdf`
- **Import process Peak RSS:** 1812.9 MB
- **llama.cpp server Peak RSS:** 6894.8 MB
- **Combined CV-path Peak RSS:** **8707.7 MB (8.504 GB)**
- **Wall:** 110.6 s
- **UI froze:** None (CLI only — UI not exercised)
- **Verdict:** **NO-GO** (gate_passed=False)

If NO-GO: stop feature expansion; shrink memory (quantization, unload Docling after parse, no second LLM, smaller n_ctx) or abort this approach for 8 GB hardware.
