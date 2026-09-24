# FINAL HOLDOUT — PHASE A REPORT

**Status:** `SEALED`  
**Pipeline:** `DET_PRODUCTION`  
**Ground truth used:** `false`  
**Evaluation performed:** `false`

## Dataset

| Item | Value |
| ---- | ----- |
| Source archive | `tests/Karrierekrake_FINAL_HOLDOUT_50_PHASE_A_BLIND.zip` |
| PDF directory | `tests/final_holdout/phase_a_pdfs/` |
| Count | **50** (`FH_001.pdf` … `FH_050.pdf`) |
| Duplicates / missing IDs | 0 / 0 |
| Pages per PDF | 1–2 |
| Total PDF bytes | 2 252 614 |
| `PDF_MANIFEST.json` | present; SHA-256 verified for all 50 files |
| Damaged / empty PDFs | 0 |
| Ground-truth filenames present | none (path check only; contents not read) |

## Codezustand

| Item | Value |
| ---- | ----- |
| Branch | `cursor/holdout-100-d85b` |
| Commit at seal | `f196378da7a2c77622c827c3b6ceef8dc7f3012c` |
| Prior product commit | `8c81a5a` (DET-only CV import) |
| Git dirty at seal | `false` |
| Runner change before seal | `scripts/run_final_holdout_predictions.py` — Phase-A hardening only (no parser changes) |
| Entrypoint | `core.cv_parser.import_cv` → `import_cv_canonical` → `parse_cv_text` |
| Document extractor | `core.cv_extract.extract_text` |
| Pipeline | DET production (Phi/C1 disabled) |
| Python | see `FROZEN_METADATA.json` → `hardware.python` |
| Platform | see `FROZEN_METADATA.json` → `hardware.platform` |
| Scorer | **not executed** (metadata note only) |

## Ausführung

| Item | Value |
| ---- | ----- |
| Started / sealed (UTC) | see `FROZEN_METADATA.json` |
| Wall time | **0.752 s** |
| Avg / median / P95 | **14.75 ms** / **13.68 ms** / **17.59 ms** |
| Min / max | **10.07 ms** / **66.63 ms** |
| Peak RSS | **~42.7 MB** |
| Model loads | 0 |
| Subprocesses | 0 |
| Technical errors | **0** |
| Empty predictions | **0** |
| `UNCERTAIN` field mentions | **0** |
| Phi extract calls | **0** |
| C1 / thin / verify / repair calls | **0** |

## Versiegelung

| Artifact | Path |
| -------- | ---- |
| Predictions | `artifacts/final_holdout/frozen_predictions/FH_001.json` … `FH_050.json` |
| Input hashes | `artifacts/final_holdout/FROZEN_INPUT_HASHES.json` |
| Prediction hashes | `artifacts/final_holdout/FROZEN_PREDICTION_HASHES.json` |
| Metadata | `artifacts/final_holdout/FROZEN_METADATA.json` |
| Seal | `artifacts/final_holdout/PHASE_A_SEAL.json` |

| Check | Result |
| ----- | ------ |
| Predictions | 50 |
| PDF↔Prediction ID mapping | 50/50 exact |
| Prediction hash mismatches | **0** |
| Predictions manifest SHA-256 | `97c64fb31cf8dfff78e530364a546f759bcaa24f1df899af3844d4a4f8c9075c` |
| Re-run overwrite protection | abort (seal present) |
| Post-seal hash re-check | passed |

## Hinweise

* Predictions are **not** quality-scored in this phase.
* No ground truth was opened or used.
* Local prediction JSON files may remain untracked per `.gitignore`; hashes and seal are authoritative.
* Phase B must be started separately with an independent ground-truth package.
