# Blindtest-Blocker – Docpick Phase 3

Stand Tip: `82ad289` (PR #62). Round3-Regression auf bekannten CVs läuft; **kein** unabhängiger Blindnachweis.
Konsistent mit `ABSCHLUSSBERICHT_DOCPICK_PHASEN.md` und `PHASE3_PARSER_STATUS.md`.

## Anforderung für unabhängigen Blind-F1≥0,99

1. Parser/Modell/Prompt/Scorer eingefroren
2. **Unberührter** DE/EN-Korpus (nicht Round2 / Mini-Holdout / bereits für DET/Phi/Docpick gesehene Sets)
3. Vollständige GT (Complete-GT V3.1-fähig)
4. Protokoll: erst PDFs → versiegelte Predictions (`gt_not_loaded`), dann GT laden + Score

## Geprüft / nicht geeignet als „neu & blind“

| Kandidat | Warum kein Blind-Claim |
|----------|------------------------|
| `regression_known_cvs` / Round2 / Round3 (40) | bekannte Entwicklungs-CVs |
| `MINI_HOLDOUT_30` / `FINAL_HOLDOUT_50` / `FINAL_INDEPENDENT_50_V2` | Phase-A-Zips vorhanden; Sets bereits in DET/Phi/Optimierungspfaden verwendet → kontaminiert für „unabhängig“ |
| `Fake_Lebenslauf_Neuer_Blindtest_Leonie_Brandt` | 1 PDF + TXT; keine vollständige DE/EN-Korpus-GT, kein Seal-Protokoll |

## Blocker

**Kein versiegelter, unberührter DE/EN-Korpus mit vollständiger GT liegt bereit.**

Daher: F1≥0,99 Blind = **nicht erreicht / nicht behauptet**.

## Nächster Architektur-Schritt (nicht DET)

1. Neuen DE/EN-Blindkorpus (≥30–50) mit vollständiger GT extern erstellen und versiegelt halten
2. Auf eingefrorenem Docpick+Qwen3.5-4B Phase-A→B nach Protokoll
3. Falls Blind-F1 < 0,99: stärkeres/quantisiertes Modell **oder** Zwei-Pass (Titel/Daten) — **kein DET-Fallback**
