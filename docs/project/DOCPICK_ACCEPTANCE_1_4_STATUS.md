# Acceptance + Kill-or-Ship status (PR #62)

**#64 = UI-only.** **NO automatic Phi fallback.** DET is not a productive fallback.

## Laptop-RAM-Gate — **OFFEN / UNGEPRÜFT** (Messung ausgesetzt)

| Feld | Wert |
|------|------|
| Hard gate (unchanged) | ≤ **3_300_000_000** Bytes Job-Object Peak |
| Target device measurement | **suspended** — no reliable Job Object run |
| Verdict | **neither pass nor fail** |
| Agent-VM | **not ship evidence** |

Wortlaut: **Laptop-RAM-Gate: OFFEN – Messung ausgesetzt.**  
Do not re-request the laptop test until a reliable measurement path exists.  
See `DOCPICK_LAPTOP_RAM_GATE_STATUS.md`.

## Independently testable gates (this pass)

| Gate | Status |
|------|--------|
| Education empty + invented `heute` (general rules) | See post-analysis report |
| Unconfirmed extract → Matching/Cover letter blocked | See extract confirmation gate |
| Fail-cases empty/corrupt/timeout/OOM | Code present |
| Matching-Contract + Diff | v1 frozen |
| CI on #62 head | Track separately |

## Kill path (only after measured Peak > gate / OOM / freeze)

1. Smaller local model under same gates — **no Phi**
2. *„wird lokales LLM-CV-Parsing auf dieser Hardware gestrichen; der manuelle Profilimport bleibt möglich.“*

Frozen NV3 blind F1 **0,980** remains binding. DOB audit 0,990 is not an independent 99% proof.
