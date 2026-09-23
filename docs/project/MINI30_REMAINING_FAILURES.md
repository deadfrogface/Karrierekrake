# Mini-30 Remaining Failures (Post-Analysis)

After DET root-cause fixes (post-analysis F1 0.9941, hallu 0, Perfect Core 26/30).

## Remaining imperfect documents (4)

| Document | Errors |
|---|---|
| MH_011 | FR address components missing (Rue du Rhône / Genève) |
| MH_012 | BE address components missing (Quai de la Goffe / Liège) |
| MH_026 | city Genève missing |
| MH_027 | BE address components missing + related gaps |

## Character

These are **address/geo parsing** gaps for French/Belgian street formats, not
licence/software/skills/certificate routing failures.

## Explicitly resolved classes

- invented_licence: **0**
- Software missing / wrong category: **0** on this corpus
- Skills missing under Fachkompetenzen/Core Skills: **0**
- Certificate hallucinations from tool/skill dumps: **0**

## Non-actions

No further fragile address hacks in this mandate. A dedicated address iteration
or a new independent holdout should follow product priority.
