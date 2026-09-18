# Deterministic SearchIntent filtering & ranking (PR23)

## Pipeline

```
normalize job
  → hard exclusions (roles / skills / keywords / industries)
  → required roles (HARD)
  → target roles (strictness-aware HARD gate)
  → mandatory skills (HARD)
  → required keywords (HARD)
  → location / employment conditions
  → soft ranking (preferred only)
  → explanation
```

**Critical invariant:** a hard filter stays hard. Ranking never resurrects an
excluded job (`rank_score` stays `0`; soft preferred skills are not evaluated).

Modules: `core/intent_filter.py`, `core/intent_aliases.py`  
Wired from `core/matcher.score_job` after legacy `hard_exclude`.

## Hard vs soft

| Signal | Semantics |
|--------|-----------|
| `excluded_*` | HARD — job out |
| `required_roles` | HARD |
| `target_roles` | HARD when set (see strictness) |
| `mandatory_skills` | HARD — solid evidence only |
| `required_keywords` | HARD |
| `remote_mode` / `employment_types` / `working_time` / `salary_min` / `countries` / `radius_km` | HARD when set (unknown job fields fail-open where noted in code) |
| `preferred_skills` / `preferred_industries` | SOFT ranking only |
| Profile fitness (`matcher.py`) | Soft scoring **after** intent include |

Include/exclude conflicts (`needs_user_review` `conflict:…`): **exclude wins**.

## Strictness

| Mode | Target-role gate |
|------|------------------|
| `STRICT` | Title must match target/required role family (curated aliases) |
| `null` + target_roles | Treated as STRICT for safety (PR22 left unset until user confirms) |
| `BALANCED` | Title first; limited expansion via curated aliases in full text |
| `EXPLORE` | Title or curated alias in full text; excludes + mandatory still HARD |

Profile work history must **not** inject new role families under STRICT
(`alternative_titles` ignored in matcher when STRICT).

## Controlled aliases (no ESCO dump, no LLM)

- **Payroll family:** Lohnbuchhalter, Gehaltsbuchhalter, Lohn- und Gehaltsbuchhalter,
  Payroll Specialist, Entgeltabrechnung, … — curated table only.
- **SAP skill:** solid `SAP` / `S/4HANA` / `SAP FI` / SuccessFactors / …  
  **Not** satisfied by “IT”, “ERP”, “Software”, Dynamics, Oracle, Sapphire, etc.
- RapidFuzz (≥92 full-string ratio) only against curated alias lists — no open
  synonym expansion.

Version tokens: `INTENT_RANKING_STRATEGY_VERSION`, `INTENT_ALIAS_TABLE_VERSION`
→ `ranking_version_token()` e.g. `intent-rank-v1-alias-v1`.

## Explainability

Every job yields an `IntentFilterResult`:

- **Why shown?** `✓ target role…`, `✓ mandatory skill…`, `✓ working time…`, …
- **Why excluded?** `✗ mandatory skill SAP missing`, …

Surfaced via `MatchResult.intent_explanation` / `rejection_reasons` /
`match_reasons`. This is **not** a marketing match percentage.

## Persistence / migration

- `jobs.ranking_version` column (SQLite migrate on open)
- On algorithm change, stale non-empty `ranking_version` rows get
  `match_score=0` cleared so rematch recomputes
- Rollback: bump version or disable intent; **never** soften hard safety/user filters

## Commercial

Hard/soft semantics are documented here. Do not advertise a match % without a
benchmark definition — the 0–100 profile score remains internal fitness, not a
guaranteed “fit rate”.

## Golden cases

- Tester A (`golden_tester_a_payroll_strict`): only payroll family titles
- Tester B (`golden_tester_b_sap_mandatory`): jobs without solid SAP → FILTERED_OUT

## Out of scope (PR23)

DACH cross-border commute filtering is implemented in PR24
(`docs/dach-cross-border.md`). Radius is Haversine-based; borders are not
distance barriers. This document remains the SearchIntent filter/ranking
reference — it does not redefine geo coverage claims.
