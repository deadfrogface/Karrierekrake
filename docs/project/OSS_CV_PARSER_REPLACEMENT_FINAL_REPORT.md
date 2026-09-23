# OSS CV-Parser Replacement — Final Report

**Status: DET-Ersatz noch nicht erreicht; DET läuft vorübergehend weiter.**

| | |
|--|--|
| Branch | `cursor/cv-parser-oss-replace-d85b` |
| PR | #61 |
| Productive DET | **unchanged** |
| Architecture tried | Docling (layout text) + SmartResume Qwen3-0.6B local + evidence/schema adapter |
| Sample | `SMOKE_DE_EN_10_V1` locked before scoring |
| Scorer | Holdout Scorer V2 unchanged (F1, not section-accuracy) |
| Correction rounds | 1 (schema drift: `name` string / `languages` dicts) |

## Candidate decisions (short)

| Candidate | Fit | License | Blocker / test | Decision |
|-----------|-----|---------|----------------|----------|
| SmartResume | Partial schema via LLM | Apache-2.0 | Prior smoke ~0.73 section-acc; this run F1 **0.805** after Docling | Supplement only; **not** production |
| Docling | Text/layout only | MIT | Was torch/torchvision `nms`; **fixed**, convert OK | Frontend OK; no CV schema alone |
| oksomu/resume-ner | EN entities | Apache-2.0 | `token_type_ids` **fixed** by strip; EN-only; DE garbled | Not DE/EN primary |
| resume-extract | TS wrapper on oksomu | MIT (README) | EN-only + Bun stack | Not primary |
| Tanya | Reference | MIT | Small/overfit (prior) | Reference only |
| pyresparser | Incomplete fields | **GPL-3.0** | License | Reject |
| brijkpatel | Broad fields | MIT (pyproject) | **Gemini cloud** for core sections | Reject (offline/PII) |

## Chosen components vs own code

- **Used:** Docling convert; local `Alibaba-EI/SmartResume` Qwen3-0.6B weights (cache, not in git)
- **Own code only:** `scripts/run_oss_cv_replace_prototype.py` — Docling call, prompt, evidence filter, schema normalize, Scorer-V2 mapping (no new DET rule farm)

## Metrics (Scorer V2, known fixtures — not a blind proof)

| Side | Slice | P | R | F1 | Hallu | Perfect Core | Invented | Zeit/CV | Peak RSS |
|------|-------|---|---|-----|-------|--------------|----------|---------|----------|
| DET | ALL | 0.765 | 1.000 | **0.867** | 0.235 | 0/10 | 29 | 0.014 s | 3369 MB |
| OSS | ALL | 0.783 | 0.829 | **0.805** | 0.182 | 0/10 | 26 | 26.4 s | 5592 MB |
| DET | DE | 0.800 | 1.000 | 0.889 | 0.200 | 0/5 | 14 | 0.018 s | — |
| OSS | DE | 0.783 | 0.756 | 0.769 | 0.173 | 0/5 | 13 | 30.9 s | — |
| DET | EN | 0.720 | 1.000 | 0.837 | 0.281 | 0/5 | 15 | 0.010 s | — |
| OSS | EN | 0.782 | 0.924 | 0.847 | 0.193 | 0/5 | 13 | 21.9 s | — |

### Gate (pre-declared)

| Criterion | Need | OSS | Pass? |
|-----------|------|-----|-------|
| F1 | ≥ 0.90 | 0.805 | no |
| Hallu | ≤ 0.03 | 0.182 | no |
| Invented emp/edu | 0 | 26 | no |
| Process success | 10/10 | 10/10 | yes |

→ **Gate failed.**

## Productive DET path

**Still productive.** No DET removal. Archive tag `archive/det-cv-parser-f3a17c0` remains. Old parser PRs **not** closed (replacement not achieved).

## What is not proven

- Independent holdout / 0.99 claim
- That Docling+SmartResume generalizes beyond these fixtures
- That fixture Scorer-V2 hallu on DET (GT has counts, not full emp/edu lists) equals real DET quality (IH2 frozen F1 **0.7246** remains the independent DET reference)

## Next only if restarted later

Need a **DE-capable** offline extractor with full address/licence/software schema and hallu control — not EN-only NER, not GPL, not cloud LLM. Do not delete DET until a new locked gate passes on a protocol that uses full GT entries.
