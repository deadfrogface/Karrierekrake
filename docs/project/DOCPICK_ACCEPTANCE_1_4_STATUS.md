# Acceptance criteria 1–4 status (PR #62 Docpick+Qwen)

## 1) Peak RSS ≤ 3.3 GB — **FAIL**

| | |
|--|--|
| Measured combined CV-path Peak | **8.504 GB** (8707.7 MB) |
| Gate | ≤ 3.3 GB (3300 MB) hard |
| Command | `.venv/bin/python scripts/run_docpick_peak_rss_gate.py` |
| Fixture | `tests/fixtures/cv_corpus/DE_01_Klassisch.pdf` |
| Breakdown | import 1.81 GB + llama.cpp 6.89 GB |
| Artifact | `tests/docpick_qwen35/peak_rss_gate/PEAK_RSS_GATE_RESULT.json` |

Soft ≤12 GB is obsolete and not a pass.

## 2) Explicit fail-cases — **PASS** (implemented + demonstrated)

| Case | Code | Evidence |
|------|------|----------|
| empty CV | `empty_cv` | unit + `scripts/run_docpick_fail_cases_demo.py` → `FAIL_CASES_DEMO.json` |
| corrupt/unreadable | `unreadable_cv` | same |
| parser timeout | `timeout` | `_enforce_timeout` / `CV_IMPORT_TIMEOUT_S` |
| Peak > 3.3 GB | `peak_rss_exceeded` | live RSS 5560 MB > 3300 → hard `CvImportError` |

No silent hang: raises `CvImportError` immediately; UI worker surfaces `failed` signal.

## 3) Matching-Contract CV↔Job — **PASS** (stable, no silent drift)

- Frozen contract: `docs/project/CV_JOB_MATCHING_CONTRACT.md`
- Version `PARSED_CV_CONTRACT_VERSION = 1`
- Keys unchanged vs prior Docpick parsed shape
- Diff this PR: **none** on names/types (additive metadata only: `parsed_cv_contract_version`, `peak_rss_mb_at_end`)
- Guard: `contract_drift` on missing top-level keys; unit `test_parsed_cv_matching_contract_stable`

## 4) Output samples (extract JSON + cover letter) under 3.3 GB — **BLOCKED**

Blocked by (1): a successful parse under ≤3.3 GB is not achievable on this stack (combined Peak 8.5 GB; even llama alone ~5.4–6.9 GB).  
Therefore no compliant extract JSON / cover-letter sample can be produced under the hard limit without aborting or replacing the model.

## Overall merge readiness

**Not done.** (1) FAIL, (4) BLOCKED by (1). (2) and (3) met.
