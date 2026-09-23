# Language Pipeline Comparison (POST-ANALYSIS)

**Label:** POST-ANALYSIS  
**Frozen Final-Holdout (immutable):** F1 0.805 · Languages F1 0.000 · Perfect Core 0/50  
**Corpus:** 50 FH CVs as development/regression corpus after sealed holdout  

## Decision rule applied

Quality first (Language Precision/Recall/F1, pair accuracy, licence F1, hallucinations, overall F1).  
At equal quality: prefer simpler, faster, lower RAM, higher reproducibility.

## Measured variants

| Variante | Language Precision | Language Recall | Language F1 | Pair Accuracy | Licence F1 | Hallu (overall) | Gesamt-F1 | Perfect Core | Zeit/CV | Peak RAM |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| DET Baseline (frozen preds) | 0.000 | 0.000 | **0.000** | 0.000 | ~0.76* | 0.071 | **0.805** | 0/50 | n/a (sealed) | n/a |
| DET repaired (+ FH_011 headings) | **1.000** | **0.950** | **0.974** | **0.950** | 0.765 | **0.006** | **0.941** | 0/50 | **~15 ms** | **~43 MB** |
| Phi Language-only | 0.984 | 0.984 | 0.984 | **0.60** | 0.929 | 1 lang hallu / 4% invalid | n/a (lang-only) | n/a | **~16.1 s** | **~5.2 GB** |
| DET→Phi Fallback | skipped | | | | | | | | | |
| Arbitration | skipped | | | | | | | | | |

\*Baseline licences were already partly recovered via full-text `Führerschein:` regex despite empty language sections.

## DET repaired — what changed

1. Composite headings `Sprachen & Fahrerlaubnis` / `Languages & licences` → `languages`
2. Licence tokens in `_COMPOSITE_REST_OK`; dash normalization for `Kenntnisse – Sprachen`
3. Licence lines harvested from mixed language bodies; not reclassified as certificates
4. (Separate KEEP) `Berufspraxis` → experience; `Weitere Angaben` → profile; career-break filter

## Remaining language FN (5)

Ground-truth lists duplicate `Englisch` rows on five documents (e.g. C1 + B1). DET correctly emits one paired line. Treated as annotation duplicates, not parser failure. Language hallucination count: **0**. Language/licence C1 confusions: **0**.

## Phi Language-only

Offline-only (`scripts/run_phi_language_only_benchmark.py`).  
Input: DET-identified language block only. Temperature 0. Not wired into `import_cv`.

DET already closes the primary failure class (empty languages) with P=1.0 / F1=0.974 at ~15 ms/CV. Phi costs ~19 s/CV and model RAM; remaining DET FNs are GT duplicates Phi cannot legitimately “fix” without inventing a second conflicting level.

## Fallback / Arbitration

**Not activated.** DET repaired solves the heading-routing failure on 50/50 docs. No GT-free trigger subset remains where Phi would add net quality without cost.

## Winner

**DET ONLY**

- Language F1 0.000 → 0.974  
- Overall F1 0.805 → 0.941 (POST-ANALYSIS)  
- Hallucination rate 0.071 → 0.006  
- 100-CV regression unchanged at F1 0.998 / Perfect 89  
- Phi left experimental / out of production extraction path  

## Artifacts

- `artifacts/final_holdout/post_analysis_language/det_baseline_language_results.json`
- `artifacts/final_holdout/post_analysis_language/det_language_results.json`
- `artifacts/final_holdout/post_analysis_language/phi_language_results.json`
- `artifacts/final_holdout/post_analysis_language/pipeline_comparison.json`
