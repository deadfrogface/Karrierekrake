# Final-50 Remaining Error Pareto (POST-ANALYSIS)

**Commit baseline:** `fb8be36`  
**Corpus:** 50-CV POST-ANALYSIS development/regression  
**Frozen (immutable):** F1 0.805 · Languages F1 0.000 · Perfect Core 0/50  

## Reproduced baseline

| Metric | Value |
| --- | ---: |
| Languages F1 | 0.974 |
| Gesamt-F1 | 0.941 |
| Hallucination Rate | 0.006 |
| Perfect Core | **0/50** |
| Zeit/CV | ~15 ms |
| Peak RAM | ~43 MB |

## Error-count distribution (Perfect Core blockers)

```text
0 Fehler: 0
1 Fehler: 4
2 Fehler: 10
3–5 Fehler: 24
6–10 Fehler: 12
>10 Fehler: 0
```

**Warum 0 Perfect Cores trotz F1 0.941?**  
`address.country` ist in **allen 50** Dokumenten `missing`. Allein dieser eine Feldfehler verhindert jedes Perfect Core Profile. Vier Dokumente haben sonst keinen weiteren Fehler.

## Top root causes (ranked)

| Rang | Root Cause | Feldgruppe | FP | FN | Wrong | Dokumente | verhinderte Perfect Profiles | Schweregrad | allgemeiner Fix |
| ---- | ---------- | ---------- | -: | -: | ----: | --------: | ---------------------------: | ----------- | --------------- |
| 1 | address_country_missing (pipe/`·`-Separator statt Komma) | address | 0 | 50 | 0 | 50 | 50 | critical | Ja — Country-Token nach `\|`/`·` |
| 2 | employment_title_wrong | employment | 0 | 0 | 59 | 30 | 30 | high | Ja — Record linking |
| 3 | certificate_missing | certificates | 0 | 17 | 0 | 17 | 17 | medium | Prüfen |
| 4 | employment_entry_missing | employment | 0 | 24 | 0 | 10 | 10 | high | Ja — Boundaries |
| 5 | address_street/hn/postal/city missing | address | 0 | 28 | 0 | 7 | 7 | high | Ja — AT/CH 4-digit + `\|` |
| 6 | skills_extra | skills | 11 | 0 | 0 | 5 | 5 | medium | Ja — duty fragments |
| 7 | software_missing | software | 0 | 7 | 0 | 5 | 5 | low | Prüfen |
| 8 | language_duplicate_gt | languages | 0 | 5 | 0 | 5 | 5 | low | GT-Duplikate |
| 9 | personal_missing | personal | 0 | 6 | 0 | 3 | 3 | medium | Prüfen |
| 10 | contact_wrong_normalization | contact | 0 | 0 | 3 | 3 | 3 | low | Prüfen |

## Field-group ranking (improvement potential)

1. **Address** — F1 0.807, 50/50 affected (country everywhere; full address gaps on CH/AT layouts)
2. **Employment** — F1 0.913, 40 affected (title wrong + missing entries)
3. **Certificates** — F1 0.795, 17 affected
4. Skills / Software / Languages — smaller residual

## Top 5 Perfect-Core blockers

1. `address_country_missing`
2. `employment_title_wrong`
3. `certificate_missing`
4. `employment_entry_missing`
5. full address missing (street/hn/postal/city) on 4-digit postal layouts

## Iteration priority

**Iteration 1:** address country (+ AT/CH `|` acceptance) — unblocks all 50 for country; unlocks ~4 single-error Perfect Cores immediately.
