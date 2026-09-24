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

## Messung A — Einzel-CV DE_01 (vor Blind, nach Prompt-Trim)

| Lauf | Sekunden | Budget |
|------|----------|--------|
| Full cold | **~96 s** | 90 s — **knapp überschritten** |
| Full warm | **~84 s** | 60 s — **nicht erreicht** |

Vorher (Round3 Ø): **~88 s**/CV.

## Messung B — Blind DE/EN v1 Seal (n=4, Freeze `49b16d5`)

| Kennzahl | Wert | Budget |
|----------|------|--------|
| Cold (BL_DE_01) | **75,9 s** | ≤ 90 s — **ok** |
| Warm-Ø (3 Folge-CVs) | **59,5 s** | ≤ 60 s — **ok** |
| Peak RSS | **2,64 GB** | ≤ 3,5 GB — **ok** |

Quelle: `tests/docpick_blind_de_en_v1/PHASE_B_COMPLETE_GT_ONLY_V3_1_RESULTS.json` → `performance_from_seal`.

## Entscheidung

- **Budget bleibt 60 s warm / 90 s cold** (Produktziel), nicht nach oben „wegdefiniert“.
- Blind-v1-Korpus liegt **innerhalb** des Budgets; längere Einzel-CVs (Messung A) können es noch reißen.
- Merge-Gate #62: Blindqualität **und** Laufzeit — Blind-v1 allein reicht nicht als großer 99%-Claim (`n=4`).
- Weitere Architektur für robust ≤60 s auf allen CVs: GPU-Offload, kleineres Modell, oder Zwei-Pass — **nicht DET**.


## Update 2026-09-24 (Round4)

- Server-Empfehlung: ``n_ctx=4096`` (2048 schnitt lange JSON-Ausgaben ab).
- ``max_tokens`` Default **1536**.
- Spot MH_025 nach Fix: Cold **43,6 s** / Warm **45,4 s** (Budget ok).
- Round4-Seal Ø **78,8 s**/CV — Warm-Budget auf längeren CVs weiter riskant.

## Update 2026-09-24 (Round7)

- Hardware: Agent-VM Xeon **4 CPU / ~15 GB** — **nicht** i3/8 GB (Zielgeräte-Gate OFFEN).
- Engpass bleibt LLM (~6 tok/s). Schema-Strip / Compact-JSON / Docling-ohne-Tabellen: **REVERT** (Qualität).
- Round7-Seal (n=40, Log): Ø **88 s**, P95 **111 s**, Peak-RSS ~2,6 GB.
- Spot nach Round7: Cold ~91–95 s / Warm ~65–89 s — Warm-Budget ≤60 s auf dieser VM **nicht** erfüllt.
- Kein Hochrechnen auf i3/8 GB.
