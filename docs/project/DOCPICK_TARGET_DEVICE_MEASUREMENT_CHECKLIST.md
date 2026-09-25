# Target-device Peak checklist (Windows i3 / 8 GB) — Job Object

Run **on the physical Intel Core i3 (11th gen) / 8 GB RAM Windows laptop only**.  
Agent-VM results are **not** ship evidence. Soft ≤12 GB obsolete. **No Phi fallback.**

## Mandatory measurement

1. Close browsers and other heavy apps.
2. Confirm Task Manager → Memory total ≈ 8 GB.
3. Run **Job Object** benchmark (children must start inside the job — no escape):

```powershell
.\scripts\run_docpick_job_object_peak_windows.ps1 `
  -LlamaServerCmd '.venv\Scripts\python.exe -m llama_cpp.server --model MODEL.gguf --n_ctx 2048 --host 127.0.0.1 --port 8080' `
  -ImportCmd '.venv\Scripts\python.exe -c "from core.cv_docpick_import import import_cv_docpick; from pathlib import Path; import_cv_docpick(Path(r''tests\fixtures\cv_corpus\DE_01_Klassisch.pdf''))"' `
  -SampleSeconds 180
```

4. Record from `JOB_OBJECT_PEAK_RSS_RESULT.json`:
   - `peak_job_memory_used_bytes` vs gate **3_300_000_000**
   - free RAM before/after
   - crashes / OOM / UI freeze
   - import/parse duration

## If Peak > 3_300_000_000 / OOM / freeze after optimization

1. Try a **smaller local model** under the same quality/RAM/runtime gates (**no Phi**).
2. If that fails: *„wird lokales LLM-CV-Parsing auf dieser Hardware gestrichen; der manuelle Profilimport bleibt möglich.“*

## E2E under limit (only if Peak ≤ gate)

Evaluate separately: Profile extract → Matching → Cover letter. Do not mix #64 UI QA.
