# EXTRACTION_OPTIMIZATION_LOG

Corpus: **Post-Analysis Development and Regression Corpus** (100 CVs)  
Scorer: V2 · Branch `cursor/holdout-100-d85b`

| Iter | Root Cause | Decision | Acc | F1 | Perfect | Hallu | Commit |
| ---: | ---------- | -------- | --: | -: | ------: | ----: | ------ |
| 0 | Baseline DET+Kenntnisse | — | 0.698 | 0.822 | 17 | 0.137 | c8d9736 |
| 1 | Kenntnisse verschluckt Praxis/Bildungsweg/… | **KEEP** | 0.887 | 0.940 | 39 | 0.017 | e1f9700 |
| 2 | Skills←Software/Language Nachbereinigung | **KEEP** | 0.902 | 0.949 | 57 | 0.003 | 5f32e6c |
| 3 | Überschrift `Werkzeuge` unrecognized | **KEEP** | 0.973 | 0.986 | 67 | 0.005 | fbc1c7b |
| 4 | Adresse (Klammern/AT-PLZ/FR) + Wrap-Fragmente | **KEEP** | 0.997 | 0.998 | 89 | 0.001 | *(dieser Commit)* |

Aggressive always-on list-continuation (Iter4 Versuch) → Hallu↑ → **REVERT** zugunsten gezielter Adress-/Fragment-Fixes.

## C1/Phi nach DET-Verbesserung

- Thin-Routing feuert auf **0/100** Docs
- Empfehlung: **DISABLE_C1_FALLBACK**
- Phi: kein Default
