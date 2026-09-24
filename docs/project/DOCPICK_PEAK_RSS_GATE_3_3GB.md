# Peak-RSS Hard Gate ≤ 3.3 GB (PR #62)

**Kill-or-Ship:** #62 only ships if the full app flow on the **real Intel Core i3 / 8 GB Windows laptop** stays within RAM, is stable, and has acceptable quality/wait. **Unmeasured gates stay open.**  
**Agent-VM Peak is NOT ship evidence.**

See `DOCPICK_KILL_OR_SHIP_TARGET_DEVICE.md`.

## Verdict (ship): **NO SHIP** — target-device Peak OPEN

### Informational Agent-VM only (not ship)

| Component | Peak RSS |
|-----------|----------|
| Import process (Docling) | 1.81 GB |
| llama.cpp Qwen3.5-4B-Q4 | 6.89 GB (`n_ctx=4096`) / ~5.4 GB (`n_ctx=2048`) |
| Combined CV path | **8.50 GB** |
| Hard gate | ≤ **3.3 GB** |

Command (Agent-VM, informational): `.venv/bin/python scripts/run_docpick_peak_rss_gate.py`  
Fixture: `tests/fixtures/cv_corpus/DE_01_Klassisch.pdf`

### Ship measurement (required)

Windows laptop: `scripts/run_docpick_target_device_peak_windows.ps1`  
Checklist: `docs/project/DOCPICK_TARGET_DEVICE_MEASUREMENT_CHECKLIST.md`

## Gates changed (code)

| Location | Old | New |
|----------|-----|-----|
| `CV_IMPORT_PEAK_RSS_MB_MAX` | soft 12 GB elsewhere | **3300** hard |
| `run_docpick_qwen35_compare.py` | 12000 | **3300** |
| Pre-run / runtime docs | ≤12 GB / ≤3.5 GB | ≤3.3 GB hard + target-device rule |
