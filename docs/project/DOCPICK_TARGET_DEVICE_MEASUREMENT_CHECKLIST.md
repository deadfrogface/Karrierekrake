# Target-device Peak checklist (Windows i3 / 8 GB)

Run **on the physical Intel Core i3 (11th gen) / 8 GB RAM Windows laptop only**.  
Agent-VM results are **not** ship evidence.

## Before

1. Close browsers and other heavy apps.
2. Note Windows Task Manager → Performance → Memory (total = 8 GB).
3. Start Karrierekrake Desktop + local Qwen llama.cpp as used in production for #62.
4. Open Task Manager → Details: note PIDs for app, Docling workers (if any), llama server.

## Measure (process group)

Preferred: run `scripts/run_docpick_target_device_peak_windows.ps1` from an elevated PowerShell in the repo.

Record:

- Process-group Peak Working Set (App + Docling + Qwen) in GB
- Free RAM before / during / after import
- Import/parse duration (seconds)
- Crashes / OOM / UI freeze (yes/no)
- Whether Peak ≤ 3.3 GB

## E2E under limit (only if Peak ≤ 3.3 GB)

Evaluate separately:

1. **Profile** — CV import extract JSON saved
2. **Matching** — job match uses contract fields (no schema drift)
3. **Cover letter** — one generated sample from that profile + fixture job

If Peak cannot stay ≤ 3.3 GB: **NO SHIP / abort recommendation**. Do not mix #64 UI QA into this run.
