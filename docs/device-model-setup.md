# Device-aware local AI setup

The normal first-run wizard shows an offline CPU/RAM/disk snapshot, one recommended model and one download button. Users of setup versions below 3 are offered the new flow once; Finish records version 3, while Cancel preserves their draft. Setup can be continued later without AI.

| Device resources | Preferred model | Download |
| --- | --- | --- |
| Smaller CPU / laptop | DASLab Qwen3.5-4B GSQ Q2_K_XL | 1,940,825,248 bytes |
| At least 23 GiB RAM and 4 physical cores | DASLab Qwen3-8B GSQ Q3_K_M | 4,124,161,376 bytes |
| At least 47 GiB RAM and 12 physical cores | DASLab Qwen3.8-27B GSQ-RCO IQ2_XS | 8,422,841,472 bytes |

Free RAM must cover the model's planning budget plus 2 GiB for the OS/app. Free disk must cover the artifact plus 500 MB. The algorithm falls back to a smaller candidate when the preferred candidate does not fit. These are conservative CPU-only recommendations, not measured laptop throughput or HR-quality guarantees. The smaller releases use GSQ, not GSQ-RCO.

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
