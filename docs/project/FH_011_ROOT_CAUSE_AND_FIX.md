# FH_011 Root Cause and Fix (POST-ANALYSIS)

**Document pattern (general):** career-break lines under/after education; missing experience heading alias.  
**Not mixed into the language-heading fix** — separate KEEP iteration.

## Root cause

| Factor | Finding |
| --- | --- |
| Heading | `Weitere Angaben` was not a section heading → body stayed inside `Bildungsweg` / education |
| Zeitraum | `03/2021 - 11/2022 Elternzeit` matched education date-first parsing |
| Blocknähe | Career note immediately followed the last education row |
| Education fallback | `_parse_education` treated any date+token row as education |
| Career note | No `career_notes` extraction; Elternzeit became `education_extra` hallucination |
| Schema mapping | GT correctly lists Elternzeit under `career_notes` (schema extension), not education |
| Additional | `Berufspraxis` was not an experience alias → jobs never left the prior skills block |

## General rule

Lines matching career-break concepts must not become education when no degree/institution evidence is present:

- Elternzeit / Erziehungszeit / Elternurlaub / Mutterschutz  
- Arbeitslosigkeit / arbeitssuchend  
- Sabbatical / career break  
- Pflegezeit  
- parental / maternity leave / unemployment (EN)

## Fix

1. `Berufspraxis` → `experience` heading (`cv_sections.py`)  
2. `Weitere Angaben` / `Additional information` / `Sonstiges` → `profile`  
3. `_is_career_break_line` filter inside `_parse_education` + post-filter  
4. Emit `career_notes` from profile / dated career-break lines  
5. Date-only education rows may consume the following qualification line (layout fix)

## Tests

`tests/test_career_break_not_education.py` — Elternzeit, Arbeitslosigkeit, Sabbatical, arbeitssuchend, Pflegezeit, Berufspraxis, Weitere Angaben.

## Regression

| Suite | Result |
| --- | --- |
| Career-break unit tests | pass |
| Language unit tests | pass |
| 50-CV POST-ANALYSIS | Overall F1 0.941 · Hallu 0.006 (was 0.805 / 0.071 frozen) |
| 100-CV POST-ANALYSIS | F1 0.998 · Perfect 89 — **unchanged vs prior seal** |

## KEEP/REVERT

**KEEP** — generalizable, improves FH_011-class errors without document IDs; 100-CV not regressed.
