# Kill-or-Ship Rule — PR #62 Docpick + Qwen CV (Architecture Owner)

**Verbatim intent:**  
#62 only ships if the **full application flow** on the **real Intel Core i3 (11th gen) / exactly 8 GB RAM Windows laptop** stays within the RAM limit, is stable, and has acceptable quality and wait time. **Every unmeasured gate stays open.**

**#64 stays UI-only** — do not mix UI QA into this PR.

---

## Ship evidence (mandatory)

| Requirement | Ship evidence? |
|-------------|----------------|
| Peak RSS on **real i3 / 8 GB Windows laptop** | **YES — required** |
| Process-group Peak (App + Docling + Qwen), not a single child | **YES — required** |
| Agent-VM / Cursor cloud Peak (~2.6 GB import-only or ~5–8.5 GB combined) | **NO — not ship evidence** |
| Soft ≤12 GB | **NO — obsolete, not a pass** |

Hard Peak: **process-group ≤ 3.3 GB**. Crash, OOM, UI freeze, or unusable runtime under that limit = **NO SHIP / recommend abort**.

---

## Gates (all must close; unmeasured = OPEN)

| ID | Gate | Status if unmeasured |
|----|------|----------------------|
| A | Target-device Peak ≤3.3 GB process-group on real i3/8GB Win laptop | **OPEN** until laptop run |
| B | Process-group Peak + free RAM + crashes + import duration reported | **OPEN** until laptop run |
| C | No crash / OOM / UI freeze / unusable runtime | **OPEN** until laptop run |
| D1 | Peak ≤3.3 GB hard (code constant `CV_IMPORT_PEAK_RSS_MB_MAX=3300`) | Code on; **ship Peak OPEN** |
| D2 | Fail-cases: empty / corrupt / timeout / peak_rss_exceeded | Implemented (Agent-VM demo ≠ ship) |
| D3 | Matching-Contract CV↔Job + Diff on drift | Stable (v1, no drift) |
| D4 | Real extract JSON + cover-letter sample **under** limit | **BLOCKED** until A passes |
| E | E2E Profile → Matching → Cover letter (evaluate separately) | **OPEN** until laptop under limit |

---

## What can be measured now (Agent-VM / this environment)

- Code gates, fail-case demos, contract freeze
- **Informational** process-group RSS while llama.cpp is loaded (see below)
- Quality on known corpora / NV3 post-analysis (**not** a Peak ship claim)

## What requires the physical laptop

- Process-group Peak during full Desktop flow (Profile import → Matching → Cover letter)
- Free RAM, crash/OOM/UI freeze observation
- Acceptable wait time on i3
- Closing gates A, B, C, D4, E for ship

Protocol: `scripts/run_docpick_target_device_peak_windows.ps1` (+ checklist in this doc).

---

## Informational Agent-VM process-group (NOT ship evidence)

Captured while Qwen llama.cpp server was loaded (`n_ctx=2048`):

| Metric | Value |
|--------|-------|
| Host | Agent-VM ~15 GB RAM |
| llama.cpp RSS | ~5.4 GB |
| Process-group (LLM-related) | ~5.4 GB |
| Prior combined import+LLM Peak | **8.50 GB** (`run_docpick_peak_rss_gate.py`, DE_01) |
| Gate | ≤ 3.3 GB |
| Ship evidence | **false** |

Even without Docling/App UI, LLM alone exceeds 3.3 GB → **strong abort signal**, but **final kill-or-ship Peak must still be taken on the Windows laptop**.

---

## Go / No-Go under Kill-or-Ship

| Decision | Reason |
|----------|--------|
| **NO SHIP** | Target-device Peak **unmeasured** (gate A OPEN). Agent-VM combined Peak **8.50 GB ≫ 3.3 GB**. LLM alone ~5.4 GB on Agent-VM. |
| Recommend | Abort Docpick+Qwen3.5-4B as on-device CV parser for i3/8 GB, **or** replace with a footprint that can prove ≤3.3 GB process-group on the real laptop. |

Do not treat any Agent-VM number as ship evidence.
