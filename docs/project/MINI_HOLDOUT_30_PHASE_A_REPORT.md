# Mini Holdout 30 — Phase A Report (Blind Sealed Predictions)

**Status:** `SEALED` — ready for separate Phase B  
**Dataset:** `MINI_HOLDOUT_30` (`MH_001`–`MH_030`)  
**Pipeline:** `DET_PRODUCTION` only  
**Ground truth used:** no  
**Evaluation performed:** no  

---

## Dataset

| Property | Value |
|---|---|
| PDF count | 30 |
| ID range | `MH_001`–`MH_030` |
| Source zip | `tests/KarriereKrake_MINI_HOLDOUT_30_PHASE_A_BLIND.zip` |
| PDF directory | `tests/mini_holdout_30/phase_a_pdfs/` |
| Total bytes | 1 353 730 |
| Total pages | 37 |
| Manifest | `PDF_MANIFEST.json` — **verified** (0 size/hash mismatches) |
| Integrity | all PDFs readable, ≥1 page, non-empty, no duplicates/extra IDs |
| MH ground truth in repo | **not present** (path check only) |

| Datei | Bytes | Seiten | SHA-256 |
|---|---:|---:|---|
| MH_001.pdf | 44627 | 1 | `b762f70e74060ff9336b532d9b2f77f387ef1d6052cc55d033ff5fbd281af116` |
| MH_002.pdf | 45243 | 1 | `83040fb00cd35a740a4c9033261b051c27a82df900be3ac2c4882051614b5fef` |
| MH_003.pdf | 45377 | 1 | `42df2f1c853c32439ebd7777af7cd188399cdd28c723f33a7967a1eb794237f2` |
| MH_004.pdf | 45694 | 2 | `8fade6095caa895de0ee91dd69b9db54acfb43a2d9f0a873c92097354a159b00` |
| MH_005.pdf | 44906 | 1 | `10152d2ef434596d05b3f3863951aeb8d8ea0efaf9399c00612e387cac2ea7cf` |
| MH_006.pdf | 45004 | 1 | `78995d03fbbf1e8ac6cb7528cca1fc58836537c5875b6a883f5bf57435d7b33c` |
| MH_007.pdf | 44816 | 1 | `ae23c2f6df63d62f5dca71e088eee079d4bcdb0ee5bf2d2cc3250b924f8cc931` |
| MH_008.pdf | 45765 | 2 | `89f4c30064cc329fcb5ec5c6fd0f524290f451bdcc759c44fbfb1165c9048307` |
| MH_009.pdf | 45011 | 1 | `c7c2d0f2f4efe94b1154d2b5431b31814beeef317c3edad35270aed7b75899bc` |
| MH_010.pdf | 44791 | 1 | `6c15848958328c8524405f6fe6765c6ffd08c79846e97979bd78837331d855c0` |
| MH_011.pdf | 45310 | 1 | `c4820966cddb7251a0cf8743ed612153a776b9ca493e1d904693ce6548302f2d` |
| MH_012.pdf | 45600 | 2 | `04751c4ff2192ba88db60c565c677cd3eef53e17cca6519497a5ef2a0cab26c7` |
| MH_013.pdf | 44641 | 1 | `6bcf779c1d29a5e4bf58a5b46a5265b1c5f1959423675aba1856209d88ce1578` |
| MH_014.pdf | 44692 | 1 | `9cc5a27e69ef309419a36cd3910750b91f013a400ea9bb5be47925342ded57ff` |
| MH_015.pdf | 45512 | 1 | `54f5a3579a784ae116058f09c123a70f4d155fb4938eb1b8b6b79213597779c6` |
| MH_016.pdf | 45316 | 2 | `a3936df6421264b8538c8029e0a4481f166d64e773056043d6836365279225d9` |
| MH_017.pdf | 45007 | 1 | `b1d6d132b439b399e17722c16058689a367c4fa63af110bd9267e5e4b62a2c3d` |
| MH_018.pdf | 44846 | 1 | `dd37d92960b75c5000710ed81841e230416288baee65016c260bb797b7f2eff0` |
| MH_019.pdf | 45142 | 1 | `a2f31b9b4933ef7d522c88dcfd4142d5ea89de914f496c3d421e3eb31ec811c4` |
| MH_020.pdf | 45703 | 2 | `77898e02ab1aa0854191013551df7b5e6f412e8648464ff58710304320f36cf4` |
| MH_021.pdf | 45024 | 1 | `abaa8305279ab1b4980fd399dcefce3d1390d9d62c5a04efb63e38adc97da79f` |
| MH_022.pdf | 45119 | 1 | `7608f8569413cc8b398bbbee351e32b192490e6e2325f638fdae4780a3cb36c1` |
| MH_023.pdf | 45357 | 1 | `e92bb67322db44232707eb67c10a8424b673417444e4729a2ae5ac6e8789dc3a` |
| MH_024.pdf | 45664 | 2 | `d4b78be62d096c6026e2f280f0d118b50ec3a601726abe05af9d49d18f25796f` |
| MH_025.pdf | 44313 | 1 | `c3627089ed1008d5bf412eb6071d4859c37144c59d1ba7dd1c3740353226418a` |
| MH_026.pdf | 44722 | 1 | `5b6970b3c19226413c889ccc8dc42b4ac53637104b4f62d49cebd3e104d36996` |
| MH_027.pdf | 44940 | 1 | `324be4aa6197e11865130df02d9a0d57f4b7054eaccf542f2ef7713c32c06193` |
| MH_028.pdf | 45304 | 2 | `a514eeb1747c01dde6eef8fd0fa025b8c9358098a4d798c6dbd23236410cdf42` |
| MH_029.pdf | 44829 | 1 | `c9e250e188706facc1355a5dc62505a433add202c72d9e7d120e5d153938cceb` |
| MH_030.pdf | 45455 | 1 | `16b6969e40fc04da72b7dad6238f1b343bda911287b8b52bb0a3aa512097a5fa` |

Hash status: **PASS** (manifest + sealed input hashes + post-seal re-hash).

---

## Codezustand

| Property | Value |
|---|---|
| Branch | `cursor/holdout-100-d85b` |
| HEAD at seal | `d5c3f42299256eb4447d3c6980f304091b0cdc42` |
| Parser commit (DET content) | `918998ca341551ad03eabc834ba73cac24b16119` (ancestor; no parser edits in runner commit) |
| Runner commit | `d5c3f42299256eb4447d3c6980f304091b0cdc42` |
| Dirty state at seal | clean |
| Pipeline | `DET_PRODUCTION` via `core.cv_parser.import_cv` → `import_cv_canonical` → `parse_cv_text` |
| Document extractor | `core.cv_extract.extract_text` |
| Feature flags | `guenther_enabled=False` (ignored); Phi/C1 not productively reachable |
| Language-Fix | contained (ancestor `fb8be36` / HEAD chain through `918998c`) |
| Restfehler-Fixstand | contained (`d70d71d` / `918998c`) |
| Python | 3.12.3 |
| OS | Linux 6.12.94+ x86_64 (glibc 2.39) |
| CPU | 4 |
| RAM | ~16.8 GB |
| GPU | none used |
| Timezone | UTC |
| Runner | `scripts/run_final_holdout_predictions.py --dataset mini_holdout_30` |

Confirmations:

- Productive CV import uses DET only.
- Phi/C1 is not productively reachable (`PHI_EXTRACT` removed).
- Current language and remaining-error DET fixes are in the tested ancestry.
- Runner change was path/ID/count parametrization only (committed before blind run).
- `artifacts/final_holdout/` was not overwritten.

---

## Ausführung

| Metric | Value |
|---|---|
| Start (UTC) | see `FROZEN_METADATA.json` → `started_at_utc` |
| End (UTC) | see `FROZEN_METADATA.json` → `sealed_at_utc` |
| Wall time | **0.531 s** |
| Avg / doc | **17.3 ms** |
| Median | **14.4 ms** |
| P95 | **25.1 ms** |
| Fastest | **9.0 ms** |
| Slowest | **87.9 ms** |
| Peak RSS | **42.5 MB** |
| Technical errors | **0** |
| Empty predictions | **0** |
| `UNCERTAIN` field mentions | **0** |
| `phi_extract_calls` | **0** |
| `c1_calls` | **0** |
| `phi_verify_calls` | **0** |
| `phi_repair_calls` | **0** |
| `thin_routings` | **0** |
| `phi_model_loads` | **0** |
| Subprocesses | **0** |

No quality metrics (accuracy / precision / recall / F1 / perfect matches) were computed.

---

## Versiegelung

| Artifact | Path |
|---|---|
| Predictions (local, gitignored) | `artifacts/mini_holdout_30/frozen_predictions/MH_001.json` … `MH_030.json` |
| Local path note | `artifacts/mini_holdout_30/LOCAL_PREDICTIONS_PATH.txt` |
| Input hashes | `artifacts/mini_holdout_30/FROZEN_INPUT_HASHES.json` |
| Prediction hashes | `artifacts/mini_holdout_30/FROZEN_PREDICTION_HASHES.json` |
| Metadata | `artifacts/mini_holdout_30/FROZEN_METADATA.json` |
| Seal | `artifacts/mini_holdout_30/PHASE_A_SEAL.json` |

| Check | Result |
|---|---|
| Prediction count | 30 |
| PDF↔prediction 1:1 | PASS |
| Unknown / missing predictions | 0 |
| Prediction hash re-verify | PASS (0 mismatches) |
| PDF hash re-verify | PASS (0 mismatches) |
| `predictions_manifest_sha256` | `da50d4559e12f32bfa06eeb445b2964389f22b5a50331824fad7e644a873851d` |
| Seal file SHA-256 | `4cc27cb7e08b5c384f5096d9b1048271db907b8b91d4510095f3603b40c927c4` |
| Seal status | `SEALED` |

---

## Stop

Phase A ends here. Predictions must not be altered. Phase B (ground truth / evaluation) must be provided separately.
