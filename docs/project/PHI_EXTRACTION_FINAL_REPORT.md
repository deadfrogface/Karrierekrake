# PHI_EXTRACTION_FINAL_REPORT

**Branch:** `cursor/phi-extract-99-d85b`  
**Date:** 2026-09-22  
**Rule:** OLD ∪ NEW requirements; no ground-truth hacks; no test deletion.

## Baseline

Authoritative corpus: `tests/fixtures/cv_corpus/CV_Parser_Sollwerte_Vollstaendig.txt` (DE_01–05, EN_01–05).

| Mode | Perfect | Field accuracy | Precision | Recall | F1 | wrong | missing | hallucinated | wrong_category | Wall |
|------|---------|----------------|-----------|--------|-----|-------|---------|--------------|----------------|------|
| Deterministic (+ verify/repair) | 10/10 | 1.000 | 1.000 | 1.000 | 1.000 | 0 | 0 | 0 | 0 | ~0.2 s |
| PHI_EXTRACT (temp=0, language split pass) | 10/10 | 1.000 | 1.000 | 1.000 | 1.000 | 0 | 0 | 0 | 0 | ~554 s |

Machine-readable: `artifacts/phi_extraction/baseline.json`

**≥99 % on this corpus: YES (100 %).** Not extrapolated to arbitrary real CVs.

## Alte Architektur (erhalten)

- Deterministic `core/cv_parser.py` + `cv_sections.py` + `cv_extract.py` (pypdf layout score)
- Language allowlist + `classify_non_language_token`
- Guenther `suggest_cv_extract` + `validate_cv_extract` grounding
- `reconcile_phi_into_parsed` (parser authority, Phi gap-fill)
- Sollwerte + Leonie P0 tests + `expected_results.json` corpus
- Profile merge / anti-resurrection / dialog geometry (P0) unchanged in scope

## Neue Architektur (hinzugefügt)

| Komponente | Pfad |
|------------|------|
| PHI_EXTRACT vs PHI_WRITE system prompts | `guenther/prompts.py` |
| Extract temp=0; write uses PHI_WRITE | `guenther/service.py` |
| Split language pass | `suggest_cv_extract_split` |
| Document backends (optional) | `core/cv_document_backends.py` |
| Evidence + qualitative status | `core/cv_evidence.py` |
| Verify + targeted repair (MAX_REPAIR_ATTEMPTS=3) | `core/cv_verify_repair.py` |
| Wired into `import_cv_canonical` | always runs verify/repair |
| Field metrics + baseline script | `core/cv_metrics.py`, `scripts/run_phi_extraction_baseline.py` |
| Backend benchmark | `scripts/run_document_backend_benchmark.py` |
| PHI_WRITE bio-claim guard | `guenther/validation.validate_writing` |

Structured-output libs (Outlines / LM Format Enforcer / Instructor): **not** adopted — prior license audit = REFERENCE only; llama-cpp free-form JSON + Pydantic validation retained.

## Parser Benchmark

| Backend | Available | Perfect | Field acc | F1 | Notes |
|---------|-----------|---------|-----------|-----|-------|
| CURRENT (pypdf) | yes | **10/10** | 1.000 | 1.000 | **Keep default** |
| pymupdf4llm | yes (optional) | 0/10 | 0.157 | 0.271 | Markdown breaks heuristics — do not default |
| Docling | no | skipped | — | — | Heavy; not installed in this cycle |
| Marker | not tried | — | — | — | Deferred |

Routing decision: **CURRENT only** until a markdown-aware parse path exists. Optional backends remain pluggable via `document_backend=`.

## Ablation (measured)

| Variant | Perfect | Notes |
|---------|---------|-------|
| CURRENT baseline DET | 10/10 | After P0 phone/experience guards |
| CURRENT + verify/repair | 10/10 | No regression; reclassifies injected non-languages in unit tests |
| CURRENT + PHI | 10/10 | No field gain on this corpus; ~550 s cost |
| pymupdf4llm replacing extract | 0/10 | **Regression — rejected as default** |

## Performance

| Path | Wall (10 PDFs) | Notes |
|------|----------------|-------|
| DET | ~0.2 s | Suitable for weak hardware |
| PHI | ~554 s | Local Phi; no GPU required; large latency trade-off with **zero** metric gain on this set |

Recommendation: keep Phi **optional** (`guenther_enabled`); deterministic path is production default for speed/quality on Sollwerte.

## Remaining Failures / LoRA

See `docs/project/REMAINING_FAILURES.md`.  
LoRA candidates file: `artifacts/phi_extraction/training_candidates.jsonl` (empty set for Sollwerte).

## P0 / alte offene Punkte

Weiterhin verbindlich (nicht durch diesen Prompt ersetzt): Ausbildung, Sprachen≠Weiterbildung, Berufsziel-Clears, Dialoggeometrie, Leonie golden — covered by `tests/test_p0_profile_cv_dialogs.py`.

## Recommendation (datenbasierter)

1. **Sollwerte ≥99 %:** erreicht (100 % DET und PHI).  
2. **Phi als Default:** nein — gleiche Accuracy, ~2700× langsamer.  
3. **pymupdf4llm Default:** nein — massive Regression.  
4. **Nächste Schritte:** Docling optional ablation; private/real CV holdout; Windows EXE smoke; keep collecting LoRA candidates only for true residual errors.
