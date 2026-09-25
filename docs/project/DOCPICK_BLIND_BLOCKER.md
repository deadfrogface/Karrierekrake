# Blindtest-Status – Docpick

Stand 2026-09-25.

## Verbindliche Blindwerte

| Test | F1 | Hinweis |
|------|-----|---------|
| **NV3 Frozen Blind** | **0,980** | verbindlich |
| DOB-Audit | 0,990 | nachträglich, **kein** 99%-Nachweis |
| Round8 known | 0,999 | **Post-Analysis**, kein Blind |
| Blind DE/EN v1 (n=4) | 0,996 | informativ |

## Blind v3 (≥50 ungesehen)

| Item | Status |
|------|--------|
| Scaffold + Freeze-Skript | bereit |
| PHASE_A_PDFS.zip (≥50 neu) | **FEHLT** |
| PHASE_B_SOLUTIONS.zip | **FEHLT** (erst nach Phase-A-Seal) |
| 99%-Claim | **nicht zulässig** bis Gate auf versiegeltem Blind v3 |

### Freeze vs. PR-Head (Klarstellung)

- `PARSER_FREEZE.json` → Feld `commit` = **getesteter Code-Stand** (Parser/Modell/Config/Scorer-Hashes).
- Der PR-Head darf ein reiner Freeze-/Docs-Commit **darüber** sein; der Freeze zeigt dann auf den Parent mit dem geprüften Code.
- Historisch: `e79d69a` = Docs/Blind-Blocker; `0694feb` = Freeze-Pointer auf `e79d69a` ohne neuen Parser-Code. Nach Evidence-Verdrahtung (`source_text`→Anschreiben) wird neu eingefroren.

## Benötigt

Siehe `tests/docpick_blind_de_en_v3/README.md`.
