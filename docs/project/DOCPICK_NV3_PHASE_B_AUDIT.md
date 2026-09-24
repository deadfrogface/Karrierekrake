# NV3 Blindscore — nachträglicher Audit (kein Blindnachweis)

**Frozen Blindscore unverändert:** F1 **0,980** (Phase B, Seal `169624a3…`, Commit `2d0d610`).  
Parser, Predictions, GT und Original-Score wurden für diesen Audit **nicht** geändert.  
**Kein 99-%-Claim** aus dem Audit. **Kein erneuter Blindtest** auf NV3.

## 1. DOB-Wrongs (25)

| Klasse | n | Bedeutung |
|--------|---|-----------|
| Format only (gleicher Kalendertag; Pred steht im PDF) | **25** | Kein Extraktionsfehler |

**Beleg (alle 25 EN-Docs NV3_026–050):** PDF z. B. `Born: 1978-11-23`; Pred `23.11.1978`; GT-Sheet ISO `1978-11-23`. Kalendertag identisch. Der Frozen-Scorer vergleicht DOB als String ohne Tages-Äquivalenz.

## 2. Education-Misses (11) + 1 Hallu

| Klasse | n | Docs | Beleg |
|--------|---|------|-------|
| Echter Miss: Pred `education=[]`, Text im PDF | **10** | NV3_005,011,014,015,018,019,031,034,043,049 | z. B. NV3_005: `Ausbildung M.Sc. Umweltwissenschaften, Universität Freiburg` |
| Semantik/Schema: EN-Dropout ↔ DE-Normalform | **1+1** | NV3_033 | PDF `Left school at 16 without qualifications`; Pred `Schule ohne Abschluss` → Missing + Hallu unter Exact-Match |

## 3. Nicht bewertbar wegen leerer Listen (28)

| Klasse | n | Gruppe |
|--------|---|--------|
| GT `[]` und Pred `[]` — Scorer V3 behandelt leere Liste als „absent“ statt `expect_absent` | **28** | Software 17, Certificates 11 |

Kein Extraktionsfehler; Schema-/Scorer-Artefakt bei leeren Listen ohne Count-Feld.

## 4. Übrige Frozen-Fehler (Kurz)

| Klasse | n | Typ |
|--------|---|-----|
| `heute` trotz datiertem Ende im PDF | 5 | Extraktion (NV3_007/014/021/035/049) |
| Jobtitel = Description statt Title | 1 | Extraktion (NV3_001) |
| Software als Certificate / Skill fehlt | 2+2 | Extraktion (NV3_008, NV3_034) |
| `Self-employed` im Title-Pipe, Company leer | 1 | Extraktion (NV3_050) |
| Apostroph `’` vs `'` | 1 | Format (NV3_041) |

## 5. Scores (getrennt)

| Score | F1 | DE-F1 | EN-F1 | Perfect Core | Hinweis |
|-------|-----|-------|-------|--------------|---------|
| **Frozen Blind** | **0,980** | 0,990 | 0,971 | 14/50 | verbindlich |
| **Audit (nur DOB-Tagesnorm)** | 0,990 | 0,990 | 0,991 | 31/50 | nachträglich; **kein** Blind-/99-%-Claim |

Audit flippt ausschließlich die 25 DOB-Wrongs → correct bei gleichem Kalendertag.

## 6. Echte Parserfehler (Priorität)

1. **Ausbildung oft leer** trotz sichtbarer Education-Zeile (10 Docs) — größter systematischer Gap  
2. **`heute` erfunden**, obwohl PDF `… - 2025-08` / `08/2024` zeigt (5)  
3. Titel/Description-Vertauschung; Software↔Zertifikat; Self-employed nicht als Company

## 7. Kleinster allgemeiner Fix (Vorschlag, nicht umgesetzt)

**Gezielte `heute`-Korrektur aus derselben Beschäftigungszeile:** Wenn Pred `end_date=heute`, aber im Quelltext zur selben Jobzeile ein explizites datiertes Ende steht (`YYYY-MM` / `MM/YYYY`), dieses Ende setzen — **nur** gleiche Zeile/Range, nicht Nachbarjobs (vermeidet Round5-Overcorrection).

Begründung: klar abgegrenzt, messbar auf den 5 Fällen, ohne DOB-Scorer oder Education-Sonderregeln. Education-Leer bleibt der größere Qualitätshebel, braucht aber eine eigene, vorsichtigere Iteration.


## 8. Round8 Fix-Ergebnis (Post-Analysis, kein Blind)

Frozen Blind F1 **0,980** unverändert. Fixes: Section-Enrich Education, `_PRESENT_END_RE`, enger same-block+start_match `heute`-Repair.
Offline Postprocess auf Frozen Preds: F1 **0,986**, Education-Misses 10/10 und erfundenes `heute` 5/5 behoben.
Known DE/EN Round8: F1 **0,999** PC 38/40 (vs Round7 0,997 / 37/40) — **KEEP**.
Kein DET. Kein 99-%-Blindclaim.
