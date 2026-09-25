# Docpick Blind DE/EN v3 — Vorbereitung (≥50, ungesehen)

**Status:** Scaffold only — **kein** Dataset geliefert.  
**Kein 99-%-Claim** möglich, bis Phase A+B auf neuem Korpus laufen.

Round8 F1 **0,999** = Post-Analysis auf bekannten CVs (nicht Blind).  
NV3 Frozen Blind F1 **0,980** bleibt der letzte verbindliche Blindwert.  
DOB-Audit 0,990 ist kein unabhängiger 99-%-Nachweis.

## Gate (vor Extract festlegen)

| Metric | Gate |
|--------|------|
| COMPLETE_GT_ONLY_V3_1_DATE_NORM F1 | ≥ **0,99** für 99%-Claim |
| n | ≥ **50** DE/EN CVs (bisher ungesehen; nicht NV3/MH/Smoke/Round*) |
| Protocol | Freeze → Phase A seal (ohne GT) → Phase B once |

## Benötigte Lieferung (Blocker)

1. `PHASE_A_PDFS.zip` mit ≥50 neuen DE/EN PDFs + `PDF_SHA256_MANIFEST.json`
2. IDs z. B. `NV4_001`… (keine Wiederverwendung von NV3/MH/Smoke)
3. Nach Phase-A-Seal: `PHASE_B_SOLUTIONS.zip` mit vollständiger SOLUTION_SHEET (V3-Felder)
4. Bestätigung: CVs waren dem Parser-Team vor Freeze ungesehen

## Commands (nach Daten)

```bash
python scripts/freeze_docpick_parser_for_blind_v3.py
python scripts/run_docpick_blind_de_en_v3_sealed_extract.py   # exit 2 ohne PDFs
# nach Solutions:
python scripts/run_docpick_blind_de_en_v3_sealed_score.py
```

`phase_b_solutions/` muss während Phase A fehlen/leer sein.
