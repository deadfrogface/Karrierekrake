# Docpick CV-Import – Laufzeit- und Peak-RSS-Budget (vor Blindtest)

**Zielgerät (Merge-Gate):** Intel Core i3 (11th gen), **genau 8 GB RAM**, kein CUDA.  
Agent-VM (Xeon / ~15 GB) ist **nicht** das Zielgerät — Zahlen dort dürfen das 8‑GB-Gate nicht ersetzen.

## Festgelegte Obergrenzen (Merge-Gate für #62)

| Kennzahl | Budget | Art |
|----------|--------|-----|
| **Peak RSS CV-Pfad** (Import-Prozess **+** lokaler LLM-Server) | **≤ 3,3 GB (3300 MB)** | **HARD FAIL** darüber |
| Warm-Extract (Folge-CV) | ≤ 60 s | sekundär |
| Cold-Extract (erster PDF) | ≤ 90 s | sekundär |

Konstante: `CV_IMPORT_PEAK_RSS_MB_MAX = 3300` in `core/cv_docpick_import.py`.

**Obsolete Soft-Gates (kein Pass):** Peak ≤ 12 GB / ≤ 12000 MB / ≤ 3,5 GB. Soft ≤12 GB ist **kein** Erfolg und kein Merge-Kriterium.

## Messung

Siehe `scripts/run_docpick_peak_rss_gate.py` und `docs/project/DOCPICK_PEAK_RSS_GATE_3_3GB.md`.

Messung muss Import-Prozess **und** llama.cpp-Server erfassen. `RUSAGE_SELF` allein (nur Python) ist unzureichend, wenn das Modell in einem zweiten Prozess läuft.

## Entscheidung

- Merge #62 nur bei **gemessenem** Peak ≤ 3,3 GB auf Zielgeräte-Constraints.
- Liegt Peak darüber: Feature-Ausbau stoppen; Memory shrinken (Quantisierung, Docling unload, kein zweites LLM, kleinerer `n_ctx`) oder Ansatz für 8 GB abbrechen.
