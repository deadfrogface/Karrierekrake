# Docpick Blind DE/EN v1 – Ergebnis

**Testtyp:** `INDEPENDENT_BLIND_DE_EN`  
**Korpus:** 2 DE + 2 EN synthetische CVs (`tests/docpick_blind_de_en_v1/`), **nicht** in Round2/3 verwendet.  
**Protokoll:** Freeze → versiegelte Predictions (`gt_not_loaded`) → erst danach GT + V3.1-Score.

## Laufzeitbudget (vorab festgelegt)

| Budget | Ergebnis Blind |
|--------|----------------|
| Warm ≤ **60 s** | Warm-Ø **59,5 s** → **eingehalten** |
| Cold ≤ **90 s** | Cold **75,9 s** → **eingehalten** |
| Peak ≤ **3,3 GB** (hard) | Prior note ~2,6 GB was **import-process only** — soft ≤12 GB obsolete; see Peak-RSS gate report |

Details Optimierung: `DOCPICK_RUNTIME_BUDGET.md`.

## Qualität (Blind)

| Metrik | Wert |
|--------|------|
| F1 (COMPLETE_GT_ONLY_V3_1) | **0,996** |
| Perfect Core | **3/4** |
| DE F1 | **0,992** |
| EN F1 | **1,000** |
| missing / wrong / hallucinated | **1 / 0 / 0** |
| einziger Fehler | `BL_DE_01` license `BE` missing (nur `B`) |

## 99%-Aussage

Auf **diesem** vorab definierten Blindkorpus mit voller GT gilt F1 ≥ 0,99.  
**Einschränkung:** n=4 ist klein — für Merge nach main zusätzlich größeren Blindkorpus empfohlen.  
Round2/3-Zahlen bleiben getrennt (Regression).

## Merge-Empfehlung #62

- Qualität auf Blind v1: **bestanden** (F1 0,996) bei kleinem n  
- Laufzeitbudget: **bestanden** auf diesem Lauf  
- main weiterhin DET bis Maintainer merged  
- Empfohlen: größeren Blind (≥20–40) nachziehen, dann Draft #62 ready + Merge
