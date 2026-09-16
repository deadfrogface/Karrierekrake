# Günther — Benchmark Report (held-out REAL GGUF)

**Splits:** `benchmark/train_or_dev/` (dev) vs `benchmark/held_out/` (final score)  
**Manifest:** `benchmark/corpus_manifest.json` (171 total fixtures; scoring = held_out only)  
**Live artifact:** `benchmark/results_live_gguf.json` / `results_live_summary.json`  
**Harness:** `benchmark/run_held_out_eval.py --live --model qwen3-1.7b`

## Held-out REAL GGUF — qwen3-1.7b (post high-impact agreement harden)

| Metric | Value |
|--------|------:|
| REAL_GGUF_CASES | **109** |
| PASS | **108** |
| FAIL | **1** (non-safety: `ho_em_ats_generic` wrong_category) |
| NON_SAFETY_ERROR_RATE | **0.0092** (~0.9%) |
| MODEL | qwen3-1.7b (bartowski Q4_K_M) |
| RUNTIME_S | ~829 |
| RAM_MB_APPROX | ~5261 |
| Runtime | llama-cpp-python 0.3.35, CPU, Linux agent |

### Safety failures (must be 0)

| Gate | Count |
|------|------:|
| Prompt injection successes | **0** |
| False confident associations | **0** |
| False rejection consequential | **0** |
| False offer consequential | **0** |
| Unsupported claims surviving validation | **0** |
| Direct consequential Günther actions | **0** |
| Malformed → unsafe | **0** |
| Schema unsafe | **0** |
| Hallucinations | **0** |

**AI safety MERGE gate:** PASS (all safety counters 0).  
**Does not claim 100% AI accuracy** — 1 soft category miss remains on generic ATS mail.

## Prior live (pre-harden, smaller corpus)

Earlier tip recorded qwen3-1.7b utility ~71.6 / safety 0 on the small legacy corpus, and **qwen3-4b failed** injection→offer (safety_penalty 40). 4B is **not** Autopick default while that class of failure exists.

## Hardening that closed injection

- Deterministic classifier: instruction-frame / injection cues → `review` (never high-impact from instructions).
- Validation: high-impact (`rejection` / `offer` / `interview_cancelled`) **requires deterministic agreement**; solid confirmation cannot be demoted to noise by the LLM.
- Association: bare REF tokens, near-tie breakers, recruiter multi-case → ambiguous / no_safe_match; schema fail-closed.

## Notes

- Qwen3 `<think>` stripped + `/no_think` in provider/prompts.
- Final quality/safety score is **held_out only** (anti-overfit).
- Consequential send/submit/accept/calendar/terminal status remain Karrierekrake + user — Günther advisory only.
