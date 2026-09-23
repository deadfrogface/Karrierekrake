# Final-50 Optimization Log (POST-ANALYSIS)

## Baseline (fb8be36 reproduced)

| Metric | Value |
| --- | ---: |
| F1 | 0.941 |
| Hallucination Rate | 0.006 |
| Perfect Core | 0/50 |
| Languages F1 | 0.974 |
| 100-CV F1 | 0.998 / Perfect 89 |

## Iteration 1 — Address country after `|` / `·`

- **Hypothesis:** Country always missing because postal regex required comma before country; headers use `Street | PLZ City | Country · email`.
- **Fix:** Allow `|,·` as country separators; accept `|` for AT/CH 4-digit; NL (`7511 AB`) + LU (`L-1616`) patterns; country tokens Niederlande/Luxemburg; city|country-only lines.
- **Tests:** `tests/test_address_country_pipe.py`
- **Before → After:** F1 0.941→0.963 (partial) → with NL/LU ~0.980; Perfect Core 0→14 (with employment iter overlapping)
- **100-CV:** unchanged 0.998 / 89
- **Decision:** **KEEP**

## Iteration 2 — Employment date-first duty lines

- **Hypothesis:** Middot duty lines before the next date were treated as title-first next jobs → wrong titles (59 wrong).
- **Fix:** `opened_by_date` flag; skip title-first peek for date-first records.
- **Before → After:** Employment wrong 59→0; F1 → 0.980; Perfect Core → 14
- **Decision:** **KEEP**

## Iteration 3 — Split dates + profile certificates + Competencies

- **Hypothesis:** (a) Dates on separate lines not a period; (b) `Zertifikate:` under Weitere Angaben ignored; (c) `Competencies` not a skills heading → tools leaked into skills.
- **Fix:** `_DATE_ONLY_LINE` pairs; route labeled lines from profile; add `competencies` heading.
- **Before → After:** F1 0.980→0.996; Perfect Core 14→39; Hallu → 0.0
- **Decision:** **KEEP**

## Iteration 4 — Unicode names/emails + software `R` fragment

- **Hypothesis:** Names with á/ø/ç rejected by `_NAME_RE`; email local-part ASCII-only; bare `R` dropped as substring of `ProTool`.
- **Fix:** Latin-1 letters in name/email regex; fragment drop requires length ≥ 3.
- **Before → After:** F1 0.996→**0.9985**; Perfect Core 39→**44**; residual 6 errors (5 GT language duplicates + 1 spaced email)
- **100-CV:** 0.998 / 89 unchanged
- **Decision:** **KEEP**

## Stop

**Stop condition A met:** F1 ≥ 0.99, Hallu ≤ 0.01, no critical hallucinations, Perfect Core 44/50, 100-CV green, old tests green.
