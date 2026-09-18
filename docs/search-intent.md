# SearchIntent domain model (PR22)

## Separation

| Domain | Question | Storage |
|--------|----------|---------|
| **Profile** (`ApplicationProfile` + `qualifications`) | What can I do? | `application_profile.yaml` + quals in `profile.yaml` |
| **SearchIntent** | What do I want to find *now*? | `profile.yaml` → `search_intent` |
| Legacy `jobs.*` / `filters.*` | Dual-read mirrors | Same file; deprecated |

STRICT (Tester A): `target_roles` drive discovery. Profile work history may later
boost fitness (PR23+) but must **not** inject new role families into the search.

Mandatory skills (Tester B): e.g. `mandatory_skills: [SAP]` — jobs without SAP
are `FILTERED_OUT` by **PR23** (`core/intent_filter.py`). See
`docs/search-intent-filtering.md`.

## Schema version

`SEARCH_INTENT_SCHEMA_VERSION = 1` (`core/search_intent.py`).

Unset scalars stay `null` — **no invented defaults** for `strictness` or
`remote_mode`.

## Fields

Roles: `target_roles`, `required_roles`, `excluded_roles`  
Skills: `mandatory_skills`, `preferred_skills`, `excluded_skills`  
Keywords: `required_keywords`, `excluded_keywords`  
Industries: `preferred_industries`, `excluded_industries`  
`strictness`: `strict` \| `balanced` \| `explore` \| `null`  
`remote_mode`: `remote` \| `hybrid` \| `onsite` \| `flexible` \| `null`  
`employment_types[]`, `working_time[]`, `salary_min`, `countries[]`, `radius_km`

Include/exclude overlaps are flagged in `needs_user_review` (`conflict:…`), not deleted.

## Legacy migration (no guessing)

| Legacy | Intent |
|--------|--------|
| `jobs.desired_titles` | `target_roles` |
| `jobs.unwanted_titles` | `excluded_roles` |
| `jobs.desired_industries` | `preferred_industries` |
| `jobs.excluded_industries` | `excluded_industries` |
| `filters.exclusion_keywords` | `excluded_keywords` |
| `employment.minimum_salary` | `salary_min` |
| `location.country` | `countries[]` |
| `location.max_distance_km` | `radius_km` |
| `full_time` / `part_time` | `working_time[]` |
| exactly one of remote/hybrid/onsite | `remote_mode` |

**Not mapped (flagged):**

- `filters.desired_keywords` → `legacy_desired_keywords_unmapped`
- multiple remote flags → `legacy_remote_flags_ambiguous`
- residual `alternative_titles` → review (normally soft-folded into desired)
- `strictness` → always null until user confirms (`strictness_unset_confirm_with_user`)

Qualifications / CV skills are **never** copied into SearchIntent.

## Deprecation

- UI label "Alternative Berufe" deprecated; list folded into desired / `target_roles`
- Field `jobs.alternative_titles` kept empty for rollback / dual-read
- Commercial rule (post-PR23): legacy fields must not secretly drive search

## Rollback

- Original `jobs` / `filters` remain in YAML alongside `search_intent`
- Failed parse: do not destroy YAML (atomic replace elsewhere)
- Dual-write `sync_legacy_jobs_from_intent` is temporary until full cutover
- Ranking strategy is versioned (`ranking_version`); never soften hard filters
  to “roll back” quality — clear stale scores and rematch instead

## PR23 filtering

Deterministic pipeline + curated payroll/SAP aliases:
[`docs/search-intent-filtering.md`](search-intent-filtering.md).
