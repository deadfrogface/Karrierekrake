# Peak-RSS Hard Gate ≤ 3.3 GB (PR #62)

**Target machine:** Intel Core i3 (11th gen), **exactly 8 GB RAM**.  
**Hard fail:** combined Docling+Qwen CV-path Peak RSS **> 3.3 GB (3300 MB)**.  
**Obsolete:** soft Peak ≤ **12 GB / 12000 MB** — **not** success, **not** merge-ready.

## Verdict: **NO-GO**

Measured on Agent-VM (absolute RSS still applies):

| Component | Peak RSS |
|-----------|----------|
| Import process (Docling + adapter) | **1.81 GB** |
| llama.cpp Qwen3.5-4B-Q4 (`n_ctx=4096`) | **6.89 GB** |
| **Combined CV path** | **8.50 GB** |
| Hard gate | ≤ **3.3 GB** |
| UI froze | not measured (CLI only) |

Shrink attempt: restart llama with `n_ctx=2048` → server RSS still **~5.4 GB** alone (before Docling). Still **> 3.3 GB**.

**Recommendation:** Stop feature expansion on this stack for 8 GB hardware. Options: abort Docpick+Qwen3.5-4B as on-device CV parser for i3/8 GB; or replace with a far smaller model / keep DET / cloud LLM. Soft ≤12 GB must not be treated as pass.

## What counts

| Component | Included? |
|-----------|-----------|
| Python import process (Docling + adapter) | yes |
| Local llama.cpp / Qwen3.5-4B server | **yes** |
| Soft ≤12 GB alone | **no pass** |

`RUSAGE_SELF` of the extract script alone is **insufficient** when the model runs in a second process (prior ~2.6 GB seals understated the real footprint).

## Gates changed

| Location | Old | New |
|----------|-----|-----|
| `core/cv_docpick_import.py` `CV_IMPORT_PEAK_RSS_MB_MAX` | (absent; soft 12 GB elsewhere) | **3300** hard |
| `scripts/run_docpick_qwen35_compare.py` | `max_peak_rss_mb: 12000` | **3300** |
| `docs/project/DOCPICK_QWEN35_CV_REPLACE_PRE_RUN.md` | ≤12000 MB | ≤3.3 GB hard |
| `docs/project/DOCPICK_RUNTIME_BUDGET.md` | ≤3.5 GB | ≤3.3 GB hard |
| `docs/project/PHASE3_PARSER_STATUS.md` | ≤3.5 GB | ≤3.3 GB hard |
| `docs/project/DOCPICK_BLIND_DE_EN_V1_RESULTS.md` | ≤3.5 GB | ≤3.3 GB hard |
| `tests/test_cv_docpick_helpers.py` | — | asserts gate == 3300, not 12000 |

## Reproduce

```bash
.venv/bin/python scripts/run_docpick_peak_rss_gate.py
```

Artifact: `tests/docpick_qwen35/peak_rss_gate/PEAK_RSS_GATE_RESULT.json`.
