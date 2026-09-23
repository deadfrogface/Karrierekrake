# Final-50 Remaining Failures (POST-ANALYSIS)

After optimization (F1 0.9985, Perfect Core 44/50, Hallu 0.0).

| Document | Field | Class | Root Cause | Severity | Next step |
| --- | --- | --- | --- | --- | --- |
| FH_002, FH_022, FH_042 | language duplicate Englisch B1 | SCHEMA / GT | GT lists two Englisch levels; DET emits one paired line | low | Do not invent duplicate languages; optional GT cleanup in future holdout |
| FH_012, FH_032 | language duplicate Englisch C1 | SCHEMA / GT | Same language listed twice at same level | low | Same |
| FH_020 | email | AMBIGUOUS_SOURCE | GT email contains a space (`veit.van dijk@…`); PDF contact line ambiguous | low | Do not invent spaces in emails; leave UNCERTAIN |

No critical hallucinations remain. No productive Phi path.
