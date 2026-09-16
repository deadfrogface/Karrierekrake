# Günther die Krake — Phase 1: Reuse / License Audit

**Date:** 2026-09-15  
**Base main:** `8c1e81c9653789251e2500b249a9abbf3d7d3175`  
**Branch:** `cursor/guenther-local-ai-megapass-d85b`  
**Rule:** Code license ≠ model license. When unsure → **REVIEW REQUIRED**. Prefer COPY/ADAPT/WRAP over rewrite.

Karrierekrake is **GPL-3.0**. Optional local AI must stay commercially redistributable with the EXE: MIT/Apache-2.0 runtimes preferred; model weights downloaded by the user into AppData (never committed).

---

## Decision legend

| Verdict | Meaning |
|---------|---------|
| **COPY** | Vendor file with attribution |
| **ADAPT** | Rewrite into Karrierekrake types using algorithm |
| **WRAP** | Thin adapter around dependency; no fork |
| **REFERENCE** | Design ideas only |
| **REJECT** | Do not ship / do not depend |
| **EXISTING** | Already in Karrierekrake |
| **ORIGINAL** | Write after reuse exhausted |
| **REVIEW REQUIRED** | Legal/product review before shipping as default |

---

## Runtime & library matrix

| Component | License (verified) | Stack notes | Verdict | Why |
|-----------|-------------------|-------------|---------|-----|
| **llama.cpp** (ggerganov) | **MIT** | C++ GGUF inference; Windows CPU/Vulkan/CUDA builds | **WRAP** (via Python binding) | Best-fit embedded runtime for EXE; replaceable |
| **llama-cpp-python** (abetlen) | **MIT** (PyPI + LICENSE.md) | Python bindings; optional native build | **WRAP** — primary embedded provider | MIT + structured JSON / grammar support; lazy import |
| **Ollama** | Product MIT; models separate | Local HTTP server | **WRAP** optional **dev/benchmark only** | Convenient for contribs; **not** required for end users / EXE |
| **GGUF format** | Format/spec community; weights separate | On-disk model container | **REFERENCE** + use | Standard offline weight format |
| **Constrained / JSON grammar decoding** | Via llama.cpp grammars (MIT) | Forces JSON-ish tokens | **WRAP** | Structured output without trusting free text |
| **Pydantic v2** | **MIT** | Already in `requirements-runtime.txt` | **EXISTING** | Validation contracts for all LLM outputs |
| **OpenAI Python SDK / HTTP cloud** | Apache-2.0 SDK; cloud ToS | Sends user data off-box | **REJECT** as Günther path | Violates local-first / no user data to external AI |
| **Anthropic SDK / Claude** | Proprietary API | Cloud | **REJECT** | Same |
| **Hugging Face `transformers` + torch** | Apache-2.0 / BSD | Heavy; multi-GB torch | **REJECT** as EXE default | Too heavy for low-end Windows; optional research only |
| **outlines / instructor / guidance** | Apache-2.0 / MIT (varies) | Structured LLM wrappers | **REFERENCE** now; **REVIEW** before dep | Prefer minimal Pydantic+grammar; avoid extra stack unless needed |
| **jsonschema** | MIT | Schema validation | **WRAP** optional | Pydantic already covers; add only if needed |
| **httpx** | BSD | Already runtime | **EXISTING** | Ollama optional client only |
| **keyring / DPAPI patterns** | MIT / OS | Token store exists for Gmail | **EXISTING** | Not for model files; models use AppData paths |

---

## Model-weight license matrix (separate from code)

| Model family | Weight license | Commercial redistribute of *app that downloads* | Bundle weights in git/EXE? | Verdict for **default Auto** |
|--------------|----------------|--------------------------------------------------|----------------------------|------------------------------|
| **Qwen3 1.7B / 4B** (Alibaba) | **Apache-2.0** (HF model cards) | Yes with Apache notice | **NO** — user download | **PRIMARY candidates** |
| **Phi-4-mini-instruct** (Microsoft) | **MIT** | Yes with MIT notice | **NO** | **Strong alternate** |
| **Gemma 3 4B** (Google) | **Gemma Terms of Use** (not Apache for Gemma 3) — flow-down + Prohibited Use Policy + unilateral termination | Commercial use allowed but **contractual flow-down** to downstream users | **NO** | **REJECT as default ship**; **REVIEW REQUIRED** if offered as optional catalog entry |
| Third-party GGUF requant forks | Inherit base + quantizer terms | Case-by-case | **NO** | Prefer **official** GGUF repos (e.g. `Qwen/Qwen3-*-GGUF`) |

**Hard rule:** Never commit `.gguf` / weight blobs. Model manager downloads to `%LOCALAPPDATA%\Karrierekrake\models\` with checksum, progress, disk check, atomic replace, uninstall.

---

## Karrierekrake EXISTING reuse (do not rebuild)

| Area | Module | Günther integration |
|------|--------|---------------------|
| Evidence taxonomy | `core/matcher.py` DIRECT/RELATED/NOT_SUPPORTED | Claim guards; LLM cannot invent DIRECT |
| CV parse | `core/cv_parser.py` | Manual/profile wins; LLM assist only |
| Cover letter | `core/cover_letter.py` | Constrained rewrite over template |
| Email classify | `integrations/email_classify.py` | Deterministic first; LLM second opinion |
| Email associate | `integrations/email_associate.py` | Threshold + recruiter ambiguity unchanged |
| Case pipeline / STATUS_RANK | `core/case_pipeline.py`, `lifecycle.py` | Suggestions only; rank prevents demotion |
| Reply drafts / send gate | `reply_draft.py`, settings `email_draft_only` | LLM may draft; user approves |
| Interview prep | `interview_prep.py` | Enrich from evidence anchors only |
| Submit gate / dry_run | `apply/manager.py`, `apply/base.py` | **No tool rights** for submit |
| AppData paths | `desktop/paths.py` | Extend with `models/` |
| Workers / cancel | `desktop/workers.py` | Pattern for non-blocking inference |
| Pydantic | runtime dep | Structured contracts |

---

## Upstream AI-assistant patterns (product ideas only)

| Source | License | Verdict | Note |
|--------|---------|---------|------|
| PBP Claude/Ollama MCP assistant | MIT code; cloud path | **REJECT** cloud; **REFERENCE** local-optional shape already rejected as core in lifecycle audit | Do not copy Claude prompts into product path |
| CareerSync Gradio HF classify | MIT | **REJECT** cloud classify | Already rejected in lifecycle audit |
| ejobtrack Xenova browser ML | Apache-2.0 | **REJECT** as required dep | Optional later only if offline+license clear |
| ai-job-tracker Claude Gmail classify | MIT | **REJECT** Claude | Already rejected |

---

## Planned ORIGINAL modules (after reuse)

| Module | Role |
|--------|------|
| `guenther/provider.py` | Abstract `LocalAIProvider` |
| `guenther/runtime/llama_cpp_provider.py` | WRAP llama-cpp-python |
| `guenther/runtime/ollama_provider.py` | Optional WRAP |
| `guenther/runtime/null_provider.py` | Fail-closed offline stub |
| `guenther/contracts.py` | Pydantic I/O schemas |
| `guenther/validation.py` | Untrusted-output pipeline + claim guards |
| `guenther/prompts.py` | SYSTEM / TRUSTED / UNTRUSTED separation |
| `guenther/model_manager.py` | Download/checksum/atomic/uninstall |
| `guenther/hardware.py` | LIGHT/STANDARD/POWER detection |
| `guenther/inference.py` | Non-blocking job + cancel + idle unload |
| `guenther/intelligence/*` | CV/Job/Evidence/Email/Assoc/Writing/Interview facades |
| `benchmark/` | Fictional DE corpus + metrics |

---

## NOTICE / attribution plan

When shipping WRAP of llama-cpp-python / llama.cpp:

1. Add MIT copyright lines to `NOTICE`.
2. Document model licenses in `docs/guenther-model-candidates.md` and in-app model manager (German user copy).
3. Do **not** relicense model weights as GPL; weights remain under their own terms in AppData.

---

## Rejects (summary)

- Cloud OpenAI/Anthropic/Gemini as Günther backend  
- Required Ollama for end users  
- HuggingFace+torch as EXE default  
- Gemma 3 as **default Auto** model (custom ToU flow-down)  
- Shipping GGUF in git  
- Giving the LLM tools that submit/send/finalize  

---

## Phase 1 exit

Reuse path clear: **WRAP** llama-cpp-python + **EXISTING** Pydantic + **EXISTING** lifecycle/matcher gates; **ORIGINAL** abstraction, validation, manager, UX. Model Autopick favors **Qwen3** (Apache-2.0) / **Phi-4-mini** (MIT). Gemma 3 catalog optional only after **REVIEW REQUIRED**.
