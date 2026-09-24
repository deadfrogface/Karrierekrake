# Peak-RSS Hard Gate ≤ 3_300_000_000 bytes (PR #62)

**Ship measurement:** Windows **Job Object** `PeakJobMemoryUsed` on real i3 / 8 GB Win laptop.  
**Agent-VM Peak is NOT ship evidence.** Soft ≤12 GB obsolete. **No Phi fallback.**

See `DOCPICK_KILL_OR_SHIP_TARGET_DEVICE.md` and `DOCPICK_KILL_PATH.md`.

## Verdict (ship): **NO SHIP** — Job Object Peak OPEN

### Informational Agent-VM only (not ship)

| Component | Peak |
|-----------|------|
| Combined CV path | **9_130_123_674 bytes** (8707.7 MiB / 8.504 GiB) |
| Gate | **3_300_000_000 bytes** |

### Ship measurement (required)

`scripts/run_docpick_job_object_peak_windows.ps1`

## Code gate

`CV_IMPORT_PEAK_RSS_BYTES_MAX = 3300000000`  
Derived MiB ≈ 3147.125 (`CV_IMPORT_PEAK_RSS_MB_MAX`).
