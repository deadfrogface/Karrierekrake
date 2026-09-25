# Kill-Pfad — lokales LLM-CV-Parsing (PR #62)

**Measurement (mandatory for ship):** Windows **Job Object** runner containing
Karrierekrake + Docling + Qwen/llama.cpp + **ALL** import child processes.
**No child may escape** the Job Object (`BREAKAWAY` flags must not be set;
`KILL_ON_JOB_CLOSE` on).

**Hard gate:** `PeakJobMemoryUsed ≤ 3_300_000_000` bytes (process group).  
**Host:** real Intel Core i3 (11th gen) / exactly 8 GB RAM Windows laptop only.  
**Agent-VM numbers are NOT ship evidence.** Soft ≤12 GB is obsolete.  
**NO automatic Phi fallback.**

Runner: `scripts/run_docpick_job_object_peak_windows.ps1`  
Code constant: `CV_IMPORT_PEAK_RSS_BYTES_MAX = 3300000000`

---

## Kill path (if Peak > 3.3 GB / OOM / freeze after optimization)

| Step | Action |
|------|--------|
| **1** | First try a **smaller local model** under the **same** quality / RAM / runtime gates. **No Phi fallback.** |
| **2** | If that also fails: remove local LLM CV parsing on this hardware; manual profile import remains. |

**Exact Step-2 wording (must use verbatim):**

> wird lokales LLM-CV-Parsing auf dieser Hardware gestrichen; der manuelle Profilimport bleibt möglich.

---

## Current status (this agent environment)

| Item | Status |
|------|--------|
| Job Object measurement plan | **Ready** (script + checklist) |
| Job Object run on target laptop | **NOT RUN** — cannot execute Windows Job Object here |
| Ship Peak bytes | **unmeasured** (gate OPEN) |
| Informational Agent-VM combined Peak | **9_130_123_674 bytes** (≈ 8707.7 MiB / 8.504 GiB) — **NOT ship evidence** |
| Informational Agent-VM LLM-only | **~5_675_000_000+ bytes** (~5.4 GiB @ n_ctx=2048) — **NOT ship evidence** |
| Gate | **3_300_000_000** bytes |
| Kill-path step | **Step 1 pending** — Job Object on laptop still required; Agent-VM already ≫ gate → enter Step 1 (smaller local model) as soon as laptop confirms over-limit / after failed optimization. **Not Step 2 yet.** No Phi. |

When laptop Job Object Peak ≤ 3_300_000_000 and E2E is stable → Step 1 not needed.  
When laptop Job Object Peak > gate after optimization → execute Step 1.  
When Step 1 also fails → Step 2 with the exact wording above.
