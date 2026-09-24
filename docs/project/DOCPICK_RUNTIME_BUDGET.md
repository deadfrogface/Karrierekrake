# Docpick CV-Import – Laufzeitbudget (vor Blindtest)

**Hardware-Referenz:** Agent-VM, 4 CPU-Kerne, Qwen3.5-4B-Q4_K_M via llama.cpp, `n_ctx=2048`, CPU-only.

## Festgelegte Obergrenzen (Merge-Gate für #62)

| Kennzahl | Budget | Begründung |
|----------|--------|------------|
| Warm-Extract (Folge-CV, Docling-Cache hit) | **≤ 60 s** | Spürbare Desktop-Nutzung; UI bleibt async, aber Wartezeit muss praktikabel sein |
| Cold-Extract (erster PDF im Prozess) | **≤ 90 s** | inkl. Docling/OCR-Kaltstart |
| Peak RSS Import | **≤ 3,5 GB** | Round2/3 Peak ~3,2–3,3 GB |

Konstanten in Code: `CV_IMPORT_BUDGET_WARM_S` / `CV_IMPORT_BUDGET_COLD_S` (`core/cv_docpick_import.py`), override via Env.

## Modellaufruf – gezielte Maßnahmen

| Hebel | Vorher | Nachher | Effekt |
|-------|--------|---------|--------|
| Prompt-Schema | ~4800 Zeichen inkl. Descriptions | ~2000 Zeichen (Descriptions strip) | Prefill kürzer |
| System-Prompt | lang | kompakt | weniger Tokens |
| `max_tokens` | 2048 | **1024** | Cap gegen Runaways |
| llama `n_ctx` | 4096 | **2048** | schnellere Attention bei kurzen CVs |

## Messung (DE_01, nach Optimierung)

| Lauf | Sekunden | Budget |
|------|----------|--------|
| Full cold | **~96 s** | 90 s — **knapp überschritten** |
| Full warm | **~84 s** | 60 s — **nicht erreicht** |

Vorher (Round3 Ø): **~88 s**/CV. Prompt-Trim: Warm **~84 s** (−~5–15 % je nach Messung).

## Entscheidung

- **Budget bleibt 60 s warm / 90 s cold** (Produktziel), nicht nach oben „wegdefiniert“.
- Aktueller CPU-Pfad **verfehlt** das Warm-Budget → Merge #62 zusätzlich zu Blindqualität durch Laufzeit blockiert.
- Nächster Architektur-Schritt für ≤60 s: GPU-Offload, kleineres Modell, oder Zwei-Pass mit weniger Prefill — **nicht DET**.
