# Device-aware local AI setup

The normal first-run wizard shows an offline CPU/RAM/disk snapshot, one recommended model and one download button. Users of setup versions below 3 are offered the new flow once; Finish records version 3, while Cancel preserves their draft. Setup can be continued later without AI.

| Device resources | Preferred model | Download |
| --- | --- | --- |
| At least 7.0 GiB total RAM (8 GB laptops) | DASLab Qwen3.5-4B GSQ Q2_K_XL | 1,940,825,248 bytes |
| At least 15.0 GiB total RAM | DASLab Qwen3-8B GSQ Q3_K_M (alternative only while its peak is unverified) | 4,124,161,376 bytes |
| At least 47 GiB RAM and 12 physical cores | DASLab Qwen3.8-27B GSQ-RCO IQ2_XS (alternative only while its peak is unverified) | 8,422,841,472 bytes |

Free disk must cover the artifact plus 500 MB. These are conservative CPU-only recommendations, not measured laptop throughput or HR-quality guarantees. The smaller releases use GSQ, not GSQ-RCO. See "Thresholds and budgets" below for the exact rules.

Downloads use immutable upstream revisions and SHA-256 digests recorded in `guenther/setup_models.py`. Interrupted downloads resume through ModelManager. A bad checksum never reaches the runtime probe. A damaged existing artifact can be downloaded again.

After verification, a child process loads the real GGUF at a 4096-token context and generates a small JSON response. It runs without a GUI or the app's single-instance lock. Cancellation, timeout, a native crash or an invalid response prevents activation. The child process tree is terminated on exit. Only success atomically writes `active-model.json`. CV import and writing resolve the same active ID on subsequent calls, including after restart. App updates preserve this independent user-data model.

No specifications or user documents are uploaded. The explicit download sends an ordinary artifact request to Hugging Face. There is no account, paid API or inference server requirement.

## Validation

- Real pinned 4B and 8B artifacts downloaded through ModelManager and verified against their published SHA-256 hashes.
- Both passed the isolated load/generation probe and activation.
- Real 8B production CV runtime returned the exact requested first/last name JSON for a fictional name; the writing provider loaded the same selected ID and returned valid JSON.
- Automated regressions cover resource selection, checksum rejection, cancellation before activation, responsive setup controls, setup migration, timeout process cleanup, persistence across restart, and app updates retaining the selected model.
- UI layout inspected at 640 × 560.

The short generation probes are load/JSON checks, not full CV corpus or letter-quality acceptance. The 27B artifact's hardware recommendation is tested in resource fixtures; this change has not run it on a physical desktop. Packaged Windows/macOS/Linux validation and physical Fujitsu/ThinkPad throughput remain separate acceptance steps. No release is published by this change.

## Thresholds and budgets

One budget source, `guenther/model_budgets.py`, is used by both the offline device report (`guenther/device_check.py`) and the setup recommendation (`guenther/setup_models.py`).

- **Budget semantics:** `CLASS_RAM_MIN_GIB` is the *minimum* RAM (GiB) a model class needs while running. A higher value is stricter. 4B = 6.0, 8B = 9.0, 27B = 14.0 (the stricter of the two formerly diverging values; the device report used 12.0). A device-report candidate's own estimate can only raise this floor, never lower it.
- **Device check (`fits`):** `fits[model_id]` is true when the installed device can host the model: total RAM passes the class gate (4B: total >= 7.0 GiB; 8B and 27B: total >= 15.0 GiB), for 8B and 27B the class budget plus the 2.0 GiB reserve also fits in total RAM (27B therefore needs >= 16.0 GiB total and never fits a 16 GB device with ~15.6-15.7 GiB), and the file plus 500 MB fits on disk. 4B is exempt from the headroom rule because its 6.0 + 2.0 GiB exceed an 8 GB laptop's ~7.7 GiB; the 7.0 GiB class gate sizes it instead. `fits` is a device check only. It is not a release, quality or speed statement.
- **Current free RAM (recommendation):** the shared rule `min(total, free) - 2.0 GiB >= class budget` decides whether 8B or 27B can be recommended. 4B is not rejected by free RAM; it only gets `low_free_ram`.
- **Device report = wizard:** `model_budgets.usable_ram_fits` is the one RAM rule for both views (4B: installed RAM, 7.0 GiB class gate, no headroom; 8B/27B: the free-RAM rule above). `guenther/device_check.py` uses it for its candidates and names the recommendation by calling `setup_models.recommend_setup_model` itself (`DeviceCheck.setup_model_id`, `DeviceCheck.recommended`, one report line "Passendes Modell für dieses Gerät: <wizard display name>" / EN "Model that fits this device: <name>", i18n key `device_report.fitting_model`; the bundled Q4_K_M is a neutral line "Mitgeliefertes Modell: …" / "Bundled model: …", key `device_report.bundled_model`, not a second recommendation), so for the same total/free RAM, cores and disk both views name the same model. An 8 GB laptop's device report therefore lists 4B GSQ instead of no candidate. `device_check` still never accepts a model that `fits` rejects.
- **`low_free_ram` warning:** set when free RAM is below `LOW_FREE_RAM_WARN_GIB` for the recommended model's class. 4B: the i3 / 8 GB peak gate (3,300,000,000 bytes, `docs/devops/i3-8gb-peak-rss-gate.md`) in GiB plus 0.5 GiB, about 3.57 GiB. 8B/27B: their class budget (9.0 / 14.0 GiB). The 4B value is derived from the gate, not measured on target hardware. T05.06 (measured low-free-RAM scenario on the i3) is ENTFALLEN by Damiano's decision of 2026-10-18 17:45; the value and all gates stay unchanged.
- **Classification by total RAM:** 4B is recommended whenever total RAM >= 7.0 GiB and its file fits on disk. Low free RAM keeps the recommendation and only adds `low_free_ram` (e.g. 7.7 GiB total with 3.0 GiB free warns; with 6.5 GiB free it does not).
- **Alternatives:** all other models with `fits` true, larger classes first.
- **8B:** `fits` and alternative from 15.0 GiB total. The recommendation gate is unchanged from before (total >= 23.0 GiB, >= 4 physical cores, free RAM covers 9.0 + 2.0 GiB) and additionally requires a complete peak attestation; while `peak_unverified` is true 8B is only listed in `alternatives`. With fewer than 4 physical cores and 8B fitting, the warning `slow_cpu` is set. UNSICHER: 8B usability on a 2-core i3 is unmeasured.
- **Attestation duty for every class above 4B:** 8B and 27B are recommended only with a complete peak attestation for exactly that artifact (`model_sha256` equal to that model's catalog `sha256`). Without it the recommendation is at most 4B; 8B and 27B stay selectable `alternatives` when they fit. An 8B attestation never unlocks 27B. This only adds a condition; no existing threshold is relaxed.
- **27B:** recommended only with >= 47 GiB total, >= 12 physical cores, its 14.0 GiB budget currently free (thresholds unchanged) and a complete 27B peak attestation; while `peak_unverified` is true 27B is only listed in `alternatives`. UNSICHER/OFFEN: the attestation peak bound is the i3 / 8 GB gate (3,300,000,000 bytes) for every class; whether an 8B Q3_K_M (4,124,161,376-byte file) or the 27B can ever stay below it is unknown. Per-class peak gates are a proposal awaiting a decision, not implemented.
- **No model (`model_id` is None):** only with `reason` `ram_too_small` (total < 7.0 GiB) or `disk_too_small` (no class-eligible file fits on disk).
- **Peak attestation:** `PEAK_ATTESTATION` in `guenther/setup_models.py` holds one record per model and is `None` for all three today. `peak_unverified[model_id]` becomes false only for a dict with all of: `commit` (full 40-character lowercase hex SHA; short SHAs are rejected), `measurement_sha256` (64 lowercase hex), `device` (non-empty), `model_sha256` equal to the catalog `sha256` of exactly that artifact, `peak_private_bytes` and `peak_bytes` as integers in 0..3,300,000,000, `method` = Windows Job Object, `ship_evidence` true and `hard_fail` false (real booleans). The record comes from `scripts/run_i3_peak_job_benchmark.py --attest-physical-i3` on the physical i3 / 8 GB laptop plus provenance. Anything missing, wrongly typed, a hash mismatch, `True`, `None` or a non-dict keeps the model unverified. There is no device-level peak warning.
- **Fields:** `SetupRecommendation` gains `reason`, `warnings` (`low_free_ram`, `slow_cpu`), `alternatives`, `fits` and `peak_unverified`. All have defaults, so existing callers and positional construction keep working.

The table tests in `tests/test_setup_thresholds.py` prove this logic only. They are no peak-memory evidence: the i3 / 8 GB hard gate (A7) stays open until a real i3 benchmark has run. The setup panel does not yet show the new fields; the wording belongs to the Designer.

