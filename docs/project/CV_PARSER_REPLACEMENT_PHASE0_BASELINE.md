# Phase 0 Baseline – CV Parser Replacement

| Feld | Wert |
|------|------|
| Working branch at start | `cursor/ih2-det-kenntnisse-fix-d85b` |
| HEAD at documentation | `bac9a0d6f97f8a5f733b7bc796fec61ae5d784c1` |
| DET freeze commit | `f3a17c09fe8a2d4d196aabb58e49c8d97ecfcfc8` |
| Parser source hash | `8e53ee6f35d33929c9ee7f80eb740d9387def883f021f3aca0f1f5083bebd211` |
| Archive tag | `archive/det-cv-parser-f3a17c0` |
| Archive branch | `archive/det-cv-parser-f3a17c0` |
| New work branch | `cursor/cv-parser-smartresume-de-en` (from f3a17c0) |
| Uncommitted at start | none |
| Open parser PRs | #58 (DET multilingual), #57 (Holdout-100), #56 (Phi extract) |
| Independent DET metrics | F1 0.7246, hallu 0.0983, Perfect Core 0/50 |
| Post-analysis (not independent) | F1 1.0000, Perfect Core 50/50 |
| Hardware | 15 GiB RAM, no CUDA, Python 3.12.3 |
| Productive entry | `core.cv_parser.import_cv` → `cv_intelligence.import_cv_canonical` → `parse_cv_text` |
| Known pre-damages | EN_02 skills count; import_replace street/house_number split |

## Parser files (legacy DET)

- `core/cv_parser.py`, `core/cv_sections.py`, `core/cv_extract.py`
- `core/cv_intelligence.py`, `core/cv_evidence.py`, `core/cv_verify_repair.py`
- `core/cv_metrics.py`, `core/cv_document_backends.py`
