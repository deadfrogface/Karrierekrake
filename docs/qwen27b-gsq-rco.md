# Local Qwen 3.8 27B GSQ-RCO integration

The CV importer and writing service now target the same DASLab IQ2_XS GGUF.
Existing model preferences (including Qwen 3.5 4B) migrate to the new model
when loading settings. User profile data and existing model files are kept.

## Artifact

- Publisher: ISTA-DASLab, https://huggingface.co/ISTA-DASLab/Qwen3.8-27B-GSQ-RCO-GGUF
- Revision: `d562806dbafae37109975e970aae91b43e73b440`
- File: `Qwen3.8-27B-GSQ-RCO-IQ2_XS.gguf`
- Exact bytes: 8,422,841,472
- SHA-256: `f0ae5006da0ce6225935339e4e989369f94de95d2263cf969519f8420c9ae02c`
- Catalog ID/directory: `qwen3.8-27b-gsq-rco`
- Base model: Qwen/Qwen3.8-27B; Apache-2.0

The complete real file was downloaded and hash-verified on 2026-10-10.
Weights are not committed. Build preparation and the in-app downloader use
the same artifact. Component updates permit up to 16 GB / 16 bounded parts
(the artifact requires nine 1 GB-or-smaller parts).

## Runtime and packaging

The pinned `llama-cpp-python==0.3.35` CPU wheel loaded the actual artifact and
returned a chat completion. `/no_think` alone did not disable reasoning.
Both local runtime paths now bind `enable_thinking=false` in the embedded
model template; CV prompt counting and prefill use the identical template.
With that binding the smoke prompt returned exactly `OK`, finish reason
`stop`, one completion token. This is compatibility evidence only, not a
CV accuracy, writing-quality or laptop performance result.

Windows ZIPs include the verified model beside the executable under `models/`.
Extract the entire folder; moving just the EXE loses the offline model.
The model stays outside the EXE to avoid unpacking 8.42 GB at each cold start.
The staged-install smoke and artifact scanner validate the sidecar layout.
Other native platforms keep their existing separate model delivery.

An already-installed old updater validates its old fixed model path and
eight-part limit. It cannot validate this new model's manifest. The first
upgrade to this generation therefore requires the new complete installation
package (or new application package followed by its model download). Future
updates use the expanded model limits. Do not claim seamless migration by
the previous updater. No release is published by this code change.

## Hardware qualification still required

The intended minimum is 16 GB installed RAM (catalog threshold 15 GiB total
usable), with T14 Ryzen 5 PRO 4650U / 24 GB as the second target. This is a
capacity target, not a latency guarantee. No discrete CUDA GPU is needed to
run the already-compressed artifact.

The CV runtime's provisional private-commit cap is 4,500,000,000 bytes,
overridable through the existing `KARRIEREKRAKE_CV_PEAK_RSS_BYTES_MAX` setting.
Mapped GGUF residency is additional: measure total memory and paging as well
as private commit. The historical i3/8 GB harness retains its original 3.3 GB
gate and does not qualify this new model. Existing deadline heuristics and
the minimum-load estimate came from the previous 4B model; they must be
recalibrated from physical-device measurements before promising timings.

Packaged Windows/macOS/Linux offline acceptance runs remain required in CI.
Run extraction and writing quality comparisons on the existing frozen cases
and test both physical laptops; historical 4B predictions are unchanged and
must not be presented as 27B results.
