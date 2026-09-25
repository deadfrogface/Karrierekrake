# Kill-or-Ship + Job Object — PR #62 Docpick + Qwen CV

**Verbatim intent:**  
#62 only ships if the **full application flow** on the **real Intel Core i3 (11th gen) / exactly 8 GB RAM Windows laptop** stays within the RAM limit, is stable, and has acceptable quality and wait time. **Every unmeasured gate stays open.**

**#64 stays UI-only** — do not mix UI QA into this PR.  
**NO automatic Phi fallback.**

---

## MEASUREMENT (mandatory for ship)

| Rule | Detail |
|------|--------|
| Method | Windows **Job Object** benchmark runner |
| Contained | Karrierekrake + Docling + Qwen/llama.cpp + **ALL** import child processes |
| Escape | **Forbidden** — do not set `JOB_OBJECT_LIMIT_BREAKAWAY_OK` / `SILENT_BREAKAWAY_OK` |
| Metric | `PeakJobMemoryUsed` |
| Hard gate | **≤ 3_300_000_000 bytes** (process group) |
| Host | Real i3 / 8 GB Windows laptop **only** |
| Agent-VM | **Not ship evidence** |

Script: `scripts/run_docpick_job_object_peak_windows.ps1`  
Legacy name-sampling script is **not** sufficient for ship (`run_docpick_target_device_peak_windows.ps1` = fallback sampling only).

Code: `CV_IMPORT_PEAK_RSS_BYTES_MAX = 3300000000` in `core/cv_docpick_import.py`.

---

## Kill path (after optimization still > gate / OOM / freeze)

1. **First** try a **smaller local model** under the **same** quality/RAM/runtime gates. **No Phi.**
2. If that also fails:  
   **„wird lokales LLM-CV-Parsing auf dieser Hardware gestrichen; der manuelle Profilimport bleibt möglich.“**

Full kill-path doc: `DOCPICK_KILL_PATH.md`.

---

## Status snapshot

| Item | Value |
|------|-------|
| Job Object plan | Ready (script) |
| Job Object on laptop | **OFFEN / UNGEPRÜFT — Messung ausgesetzt** |
| Ship Peak bytes | **unmeasured** (neither pass nor fail) |
| Gate bytes (unchanged) | **3_300_000_000** |
| Agent-VM | **not ship evidence** |
| Kill-path step | Deferred until reliable laptop measurement exists |

Wortlaut: **Laptop-RAM-Gate: OFFEN – Messung ausgesetzt.**
