# Final Independent 50 V2 — Remaining Failures (Frozen Phase B)

Frozen evaluation of DET ancestor `3c9f5bd` on `IH2_001`–`IH2_050`.

## Headline

| Metric | Value |
|---|---:|
| F1 | **0.7246** |
| Hallucination Rate | **0.0983** |
| Perfect Core | **0 / 50** |
| Critical invented | **163** (software 150, employment 13) |

## Pareto-style classes (by volume)

1. **Skills missing** (~206) — skill sections/entries not extracted
2. **Software extras** (~150) — headings / non-tools as software (e.g. `Kompetenzprofil`)
3. **Languages missing** (~107) — language rows not recovered
4. **Software missing** (~95)
5. **Employment missing / invented** (~50 missing + 13 invented)
6. **Education missing** (~41)
7. **Address gaps** (~24 missing + 4 wrong)
8. **Licence missing** (~10)
9. **Certificate missing** (~5)

## Stable

- Contact F1 1.0
- Personal F1 ≈ 0.96
- Certificates / Licenses / Address relatively strong vs Kenntnisse

## Do not treat as

- Mini-30 post-analysis success (F1 0.994) — different corpus, not this seal
- Permission to silently patch against IH2 IDs

Any fix campaign must stay general and finish with a **new** independent blind holdout.
