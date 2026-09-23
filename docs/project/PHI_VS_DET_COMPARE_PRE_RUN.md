# Phi vs DET — Pre-Run Lock (before scoring)

| Feld | Wert |
|------|------|
| Manifest | `tests/phi_vs_det_compare/SAMPLE_MANIFEST_LOCKED.json` (locked before scoring) |
| Sample | PHI_VS_DET_COMPARE_8_V1 (4 DE + 4 EN Mini-30) |
| Scorer | `scripts/holdout_scorer_v2.py` unchanged (sha256 `0d80bdd6…`) |
| DET | Current product `import_cv` @ HEAD (DET-only; `guenther_enabled` ignored) |
| Phi | One config: `phi4-mini` Q4_K_M, `SYSTEM_PHI_EXTRACT`, `suggest_cv_extract` temp=0, B1-style map |
| Productive path | Unchanged |
| Known corpus | Development data — **not** an independent blind test |

## Sample (locked before scoring)

| ID | Lang | Traits |
|----|------|--------|
| MH_001 | de | classic, single page |
| MH_015 | de | multi-employment, abroad |
| MH_020 | de | multipage |
| MH_030 | de | multi-employment, abroad |
| MH_024 | en | multipage, multi-employment |
| MH_025 | en | classic |
| MH_026 | en | sparse/abroad address |
| MH_027 | en | multi-employment, abroad |

## Pre-declared gates

| Gate | Value | Source |
|------|-------|--------|
| Peak RSS | ≤ 8192 MB | STANDARD tier / 15 GiB host headroom |
| Avg s/CV | *not specified* | No CV-import latency SLA in project docs |
| Clearly better | ΔF1 ≥ 0.05 **and** RAM gate | Manifest rule |

## Context (not this run’s score)

- IH2 frozen DET F1 **0.7246** (independent) vs post-analysis **1.0000** (not independent)
- PR #59 SmartResume section-accuracy ~**0.73** ≠ F1; smoke gate failed
