# Qwen 3.5 9B / GSQ-RCO migration status (2026-10-10)

Requested target: one local Qwen 3.5 9B model compressed with GSQ **and** RCO,
for CV extraction and writing, with Fujitsu i3 / 16 GB as the minimum target
and ThinkPad T14 Ryzen 5 PRO 4650U / 24 GB as the second target.

## Verified available artifact

- Source: https://huggingface.co/d-alistarh/Qwen3.5-9B-GSQ-Q3_K_M-GGUF
- Immutable revision: `a357677adaa334316334b4efec461da3b0bb6ed0`
- File: `qwen35-9b-gsq-q3km.gguf`, 4,259,406,816 bytes.
- SHA-256: `fec779ef5deb0cf2d1772fc0e2d0b8c33510262da5c10791bebf508fe5776d47`
- Metadata verified through the Hugging Face model API with `blobs=true`.
- GSQ optimizes 80 of 248 weight tensors (MLP/full attention); SSM projections
  retain standard quantization. The card does **not** claim RCO.
- Published WikiText2 PPL: GSQ 9.97, BF16 8.74, Unsloth Dynamic Q3_K_M 8.56.
  This metric is not a CV or cover-letter quality test and does not establish
  GSQ superiority over the available alternative.

A ready-made Qwen 3.5 9B GSQ-RCO artifact was not verified. This GSQ-only file
is a research candidate, not fulfillment of the requested compression target.
The production model, release download, and existing frozen benchmark records
are unchanged.

## Reproducible preparation

Run from the repository root on Windows or Linux (Python; no Ollama required):

```sh
python scripts/prepare_qwen9b_gsq_candidate.py --require-rco
```

This intentionally exits with code 2: the requested RCO artifact is missing.
To explicitly prepare the **GSQ-only** comparison candidate:

```sh
python scripts/prepare_qwen9b_gsq_candidate.py --download
```

The download uses the pinned revision, checks exact length, GGUF magic and
SHA-256, and atomically publishes the verified file. Without `--download` it
only verifies an existing local file. It never edits user settings or installs
weights into the production model folder.

## Outstanding work before activation

1. Obtain or build a genuine GSQ-RCO 9B artifact. Reference code:
   https://github.com/IST-DASLab/GSQ and https://github.com/IST-DASLab/RCO.
   The public RCO pipeline documents GPTQ-database search and HF checkpoint
   assembly; a working GSQ-to-RCO-to-GGUF 9B pipeline must be verified rather
   than assuming these scripts compose automatically. This environment has no
   available CUDA GPU and no installed llama-cpp-python runtime.
2. Pin final source revision, file size, hash, quantization provenance and
   license in the production catalog **after** the artifact exists.
3. Test the packaged llama.cpp runtime with the artifact's architecture and
   embedded chat template. Do not treat a download or load-only smoke as a
   successful CV/writing test.
4. Revisit the existing 3,300,000,000-byte CV process budget in
   `core/cv_docpick_import.py`. The GSQ-only file already exceeds that value;
   mapped file size and private commit are different measurements, so measure
   actual Windows process-group peak private commit rather than simply adding
   file bytes. A new budget must leave room for Windows, the app and context.
5. Compare the production 4B baseline, normal 9B and the final GSQ-RCO 9B
   using the same prompts, schemas, context/token budgets and validators.
   Separate extraction and writing. Reuse known fixtures for regression;
   preserve untouched blind fixtures for the final comparison. Record exact
   artifact hashes, runtime version, success/errors and actual timings.
6. Run on both physical laptops. Record cold/warm extraction time, writing
   time, prompt/generation token rates and Windows job peak memory. Host/VM
   numbers cannot establish i3 or T14 performance. Agree on acceptable wait
   times before calling it the default.
7. Update model-manager/config normalization, CV runtime paths, native
   download, bundled preparation, release/update paths and visible model
   labels together. Retain the verified 4B recovery option and test upgrade
   from existing installations. Do not relabel historical 4B results as 9B.

No 9B inference, physical-laptop performance test or RCO compression was
performed by this preparation change. Automated tests verify download
integrity and the explicit RCO guard only.
