# Arbeitsprotokoll Docpick #62 (autonome Schleife)

Hardware: Agent-VM Intel Xeon, **4 CPU**, ~15 GB RAM — **nicht** i3/8 GB. Zielgeräte-Gate: **OFFEN**.

## Diagnose R3→R5

- PC 33→28: 5× `heute`→`09/2022` (Repair, bereits deaktiviert) + 3× fehlendes Lizenz-C1 + MH_028 company.
- EN-F1 0,988: MH_024 Positions / MH_025 Software — schon in R3.
- Stage-Timing: Docling kalt 11–22 s (Warm ~0), **LLM ~65–85 s** (~6 tok/s, ~394 completion / ~1440 prompt), Postprocess <0,05 s.
- Warm-Budget ≤60 s: auf dieser VM **strukturell nicht erreichbar** solange LLM allein ~66 s braucht.

## Iterationen

| # | Hypothese | Änderung | Messung | KEEP/REVERT |
|---|-----------|----------|---------|-------------|
| 0 | Repair überschreibt echte heute | Repair default off | Targeted: MH_005/009/017 → heute wieder korrekt | **KEEP** disable |
| 1 | C1 fehlt weil Enrich nur bei leerer Lizenz | Merge Führerschein-Zeilen immer | Targeted DE_03/MH_008/MH_020: `B`→`B C1` | **KEEP** |
| 2a | Schema-Strip spart Prefill | Env STRIP=1 | MH_025 −5 s; EN_02 −27 s, aber DOB verloren | **REVERT** |
| 2b | Tabellen-Pipeline abschalten | `do_table_structure=False` | EN_02 2433→1581 Chars | **REVERT** |
| 2c | pypdf-first | Heuristik | EN Zwei-Spalten Ratio 0,31–0,33 | **REVERT** (Qualitätsrisiko) |
| 2d | Compact JSON | (Messung) | folgt | … |

## Nächste Schritte

1. Round6 Seal+Score (Lizenz-Merge + ohne heute-Repair) auf 40 bekannten CVs.
2. Compact-JSON nur bei messbarem Laufzeitgewinn ohne Qualitätsverlust.
3. Blind-v2 und i3/8GB-Messung blockiert — Stoppregel.
