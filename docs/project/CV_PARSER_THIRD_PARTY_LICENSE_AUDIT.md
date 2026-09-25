# CV Parser Third-Party License Audit

**Branch:** `cursor/cv-parser-smartresume-de-en`  
**Date:** 2026-09-23  
**Scope:** Components considered for DE/EN CV extraction replacement

## Summary table

| Project | Code license | Model license | Commercial use | Local use | Hardware | Result |
|---------|--------------|---------------|----------------|-----------|----------|--------|
| Alibaba SmartResume | Apache-2.0 (verified) | Qwen3-0.6B-resume / Alibaba-EI/SmartResume: **Apache-2.0** (HF model card) | Yes under Apache-2.0 | Yes (vLLM/transformers; ModelScope or HuggingFace download) | GPU recommended (6–10+ GB VRAM); CPU possible for 0.6B; RAM ≥8–16 GB | **Usable** – model not committed; optional local download |
| Docling | MIT (verified) | Per-model (IBM Docling layout/OCR packages; check each artifact) | Code: yes; models: verify per package | Yes | CPU OK; layout models add RAM | **Usable** for layout/OCR frontend if model licenses OK |
| oksomu/resume-ner | Apache-2.0 (model card) | Apache-2.0 | Yes | Yes (PyTorch/ONNX) | CPU OK (~250 MB DistilBERT) | **EN-only** – usable as EN entity candidate only |
| TanyaIgnatenko Resume-Parser | MIT (verified) | Training artifacts: verify before shipping weights | Code: yes | Yes | CPU | **Reference only** unless isolated test shows gain (small dataset) |

## SmartResume notes

- Code: https://github.com/alibaba/SmartResume – Apache-2.0
- Weights: https://huggingface.co/Alibaba-EI/SmartResume – `license: apache-2.0`, base `Qwen/Qwen3-0.6B`
- Redistribution of weights in Karrierekrake installer: **allowed under Apache-2.0** with NOTICE retention; still prefer **cache download + SHA-256 manifest** (do not commit multi-GB weights).
- DE support: project is layout-aware and LLM-based; **no strong published DE claim**. Must be measured on DE smoke set. Chinese-centric training risk for German headings.
- Default config uses cloud DashScope API – **forbidden** for PII CVs. Production path must force `use_direct_models: true` / local only.

## Docling notes

- Code MIT. Models (e.g. `docling-project/docling-models`, RapidOCR, TableFormer) have **separate** licenses – only enable packages documented as Apache-2.0/MIT/compatible.
- No cloud upload of CV bytes.

## oksomu/resume-ner notes

- Explicit limitation: **English resumes only**
- Must not be applied as primary extractor on German CVs

## TanyaIgnatenko notes

- MIT code; small training set → high overfit risk
- Use for schema/eval patterns; model only if Variant C isolated gain proven

## SBOM (planned installs – no weights in git)

| Component | Version / pin | Role | License | Cache path |
|-----------|---------------|------|---------|------------|
| smartresume (vendored/api adapter) | git pin at clone time | Orchestration reference | Apache-2.0 | `vendor/` or pip |
| Alibaba-EI/SmartResume Qwen3-0.6B | HF revision pin + SHA-256 | Local LLM extract | Apache-2.0 | `~/.cache/karrierekrake/models/smartresume/` |
| yolov10/best.onnx (SmartResume layout) | same HF repo | Layout | Apache-2.0 (same card) | same cache |
| docling | PyPI latest audited | Layout/OCR frontend | MIT + model deps | pip + HF cache |
| oksomu/resume-ner | HF revision pin | EN NER candidate | Apache-2.0 | HF cache |
| torch (CPU) | PyPI | Runtime | BSD-style | pip |
| transformers | PyPI | Runtime | Apache-2.0 | pip |

## Decision

Proceed to isolated smoke evaluation of Variants A/B/C under **local-only** constraint.  
If DE quality fails smoke gate → abort replacement; keep DET production path (archive tag `archive/det-cv-parser-f3a17c0`).
