# Docpick CV-Import – Laufzeit- und Peak-RSS-Budget (vor Blindtest)

**Zielgerät (Merge-Gate):** Intel Core i3 (11th gen), **genau 8 GB RAM**, kein CUDA.  
Agent-VM ist **nicht** das Zielgerät — Zahlen dort sind **kein Ship-Evidence**.

## Festgelegte Obergrenzen (Merge-Gate für #62)

| Kennzahl | Budget | Art |
|----------|--------|-----|
| **PeakJobMemoryUsed** (Windows Job Object: App + Docling + Qwen + alle Import-Kinder) | **≤ 3_300_000_000 Bytes** | **HARD FAIL** darüber |
| Warm-Extract (Folge-CV) | ≤ 60 s | sekundär |
| Cold-Extract (erster PDF) | ≤ 90 s | sekundär |

Konstante: `CV_IMPORT_PEAK_RSS_BYTES_MAX = 3300000000` in `core/cv_docpick_import.py`.

**Obsolete Soft-Gates (kein Pass):** Peak ≤ 12 GB / ≤ 12000 MB / ≤ 3,5 GB / „3300 MB“ ohne Byte-Gate.

## Messung (Ship)

**Pflicht:** `scripts/run_docpick_job_object_peak_windows.ps1` auf dem echten i3/8‑GB-Windows-Laptop.  
Kein Kind darf dem Job Object entkommen. Agent-VM `/proc`-Summen = nur informativ.

## Kill-Pfad

Siehe `DOCPICK_KILL_PATH.md`. Kein automatischer Phi-Fallback.

## Entscheidung

- Merge #62 nur bei **gemessenem** Job-Object-Peak ≤ 3_300_000_000 Bytes auf dem Zielgerät.
- Liegt Peak darüber nach Optimierung: Step 1 kleineres lokales Modell; sonst Step 2 — lokales LLM-CV-Parsing auf dieser Hardware streichen; manueller Profilimport bleibt.
