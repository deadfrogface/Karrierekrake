# Mini-30 DET Optimization Log

Post-analysis only. Frozen Phase-A/B values remain immutable:

| Frozen Mini-30 | Value |
|---|---:|
| F1 | 0.8548 |
| Hallucination Rate | 0.0576 |
| Perfect Core | 0/30 |
| Software F1 | 0.193 |
| invented_licence | 5 |

## Iterations

| # | Root cause | Decision | Notes |
|---:|---|---|---|
| 1 | Licence blob (split heading + raw `_parse_driving` fallback) | KEEP | invented_licence → 0 |
| 2 | Software taxonomy + proficiency strip + contextual Applications | KEEP | Software F1 → 1.0 |
| 3 | Fachkompetenzen skills headings + no tool-as-skill recovery | KEEP | Skills F1 → 1.0 |
| 4 | Certificate default dump removed | KEEP | Certs F1 → 1.0, hallu → 0 |
| 5 | Cross-field: Born DOB, Unicode names, Applications context | KEEP | Perfect Core → 26/30 |

## Regression gates (after final KEEP)

| Corpus | F1 | Perfect | Hallu | Phi |
|---|---:|---:|---:|---:|
| Mini-30 post-analysis | 0.9941 | 26/30 | 0.0 | 0 |
| Final-50 post-analysis | 0.9985 | 44/50 | 0.0 | 0 |
| Holdout-100 | 0.9984 | 89/100 | 0.001 | 0 |

Employment / Education / Contact F1 remained 1.0 on Mini-30.

## Phi / LoRA

Not used. `phi_extract_call_count = 0`.
