# Final Independent 50 V2 — DET Post-Analysis

**Label:** POST-ANALYSIS (not a new frozen blind seal)  
**Frozen Phase B reference:** F1 0.7246 · hallu 0.0983 · Perfect Core 0/50 (immutable)  
**Post-analysis result:** F1 **1.0000** · P 1.0 · R 1.0 · hallu 0.0 · Perfect Core **50/50** · invented_critical 0

## Scope

Generalizable DET repairs only (`core/cv_parser.py`, `core/cv_sections.py`, scorer native-level aliases).  
No IH2 document-ID hacks, no Phi/LoRA.

## Iteration path (V2)

| Step | Focus | F1 (approx.) |
|------|--------|--------------|
| Frozen Phase B | baseline seal | 0.7246 |
| Software dump filter + EN/FR/NL headings | hallu ↓ | ~0.91 |
| Multilingual languages / mother-tongue | recall ↑ | ~0.986 |
| Skills middot / licence / certs | groups clean | 0.9924 |
| EU address (PL/CZ/SE/DK/BE/AT/SI, Unicode, city-only PLZ) | address perfect | **1.0000** |

## KEEP

- Multilingual section headings (FR/NL/EN) and composite rest-ok tokens
- Software accept/reject + wrap/`/` lists; no skill-steal of TitleCase tools
- Language endonyms + scorer `_native_level_aliases`
- Skills: EMP_LEAK before middot→pipe
- Licence/cert NL/FR labels; Né(e)/Geboren DOB
- Address: Latin Extended city chars, optional-street postal (DE/PL/spaced/AT-CH/NL/LU)

## REVERT candidates (if regressions appear)

- Optional-street postal matching (watch false PLZ from phone/date lines — guarded by country/`|`/`,`)
- Broad `_CITY_CHARS` Unicode range

## Regression smoke

- Unit: address + licence/software/skills routing — pass
- Mini-30 re-import score (post-analysis, not frozen): F1 1.0 · Perfect Core 30/30
- Phi calls: 0

## Honesty

Post-analysis on the same IH2 corpus after reading errors is **not** a new independent blind seal.  
Frozen Phase A/B artifacts under `artifacts/final_independent_50_v2/` (non-`post_analysis`) remain immutable.
