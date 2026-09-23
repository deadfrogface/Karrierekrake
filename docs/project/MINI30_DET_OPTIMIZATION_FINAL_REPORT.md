# Mini-30 DET Optimization — Final Report

## Ausgangspunkt (Frozen Mini-30, immutable)

| Metric | Value |
|---|---:|
| F1 | **0.8548** |
| Hallucination Rate | **0.0576** |
| Perfect Core | **0/30** |
| Software F1 | **0.193** |
| invented_licence | **5** |

Parser commit under test at freeze: `918998c`.

## Licence-Blobs

- **Root cause:** wrapped `Sprachkenntnisse &` / `Führerschein` + raw-line fallback in `_parse_driving`.
- **Fix:** heading join + validated licence tokens only + section context for bare `C1`.
- **After:** invented_licence **0**; Licences F1 **1.0**.

## Software

- **Root cause:** missing `Programme und Werkzeuge` / contextual `Applications`; proficiency glued to names; unknown tools stolen as skills/certs.
- **Fix:** taxonomy + contextual Applications + proficiency strip + CamelCase product routing.
- **After:** Software F1 **1.0**.

## Skills

- **Root cause:** missing `Fachkompetenzen`; certificate default dump.
- **Fix:** skills headings + no unsafe recovery from software bodies.
- **After:** Skills F1 **1.0**.

## Certificates

- **Root cause:** `classify_non_language_token` default → certificate.
- **Fix:** uncertain instead; labelled `Zertifikate:` only.
- **After:** Certificates F1 **1.0**; hallu **0.0**.

## Regressionen

| Suite | Result |
|---|---|
| New routing unit tests | pass |
| Language / software / skills / sections | pass |
| Final-50 post-analysis | F1 0.9985, Perfect Core 44/50 |
| Holdout-100 | F1 0.9984, Perfect 89/100 |
| Employment / Education / Contact (Mini-30) | F1 1.0 |

## Finale Post-Analysis Metriken (Mini-30)

| Metric | Before (frozen) | After (post-analysis) |
|---|---:|---:|
| Normalized Accuracy | 0.7463 | **0.9884** |
| Precision | 0.9283 | **1.0000** |
| Recall | 0.7920 | **0.9884** |
| F1 | 0.8548 | **0.9941** |
| Hallucination Rate | 0.0576 | **0.0000** |
| Perfect Core | 0/30 | **26/30** |
| invented_licence | 5 | **0** |
| Software F1 | 0.193 | **1.000** |
| Skills F1 | 0.378 | **1.000** |
| Certificates F1 | 0.326 | **1.000** |
| Phi calls | 0 | **0** |
| Avg ms/CV | 17.3 | ~15.4 |
| Peak RSS | ~42 MB | ~42 MB |

Remaining errors: foreign-address parsing gaps (Rue du Rhône / Quai de la Goffe / Genève) on 4 documents — out of scope for this Kenntnisse/Licence pass.

## Ehrliche Einordnung

1. **Frozen Mini-30 remains F1 0.8548** — that independent sealed result is unchanged.
2. New numbers are **POST-ANALYSIS** on the same PDFs after DET fixes.
3. No Phi, no LoRA, no scorer/GT edits, no frozen overwrite.
4. Next step: a **new independent holdout** to confirm generalisation.

```text
RESULT: DET ROOT-CAUSE FIXES COMPLETE – READY FOR INDEPENDENT RECHECK
```
