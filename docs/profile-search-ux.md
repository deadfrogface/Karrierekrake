# Profile vs Search UX (PR35)

## Mental model

| Surface | Question | Owns |
|---------|----------|------|
| **Profil** | Wer bin ich? | Applicant data, CV, qualifications, experience, home address |
| **Suche** | Was suche ich jetzt? | `SearchIntent` only (`core/search_intent.py`) |

Navigation (primary): Profil → Suche → Jobs → Bewerbungen → Günther → Einstellungen.

Dashboard and Logs remain reachable; Günther maps to the existing lifecycle page
(no lifecycle redesign in this PR).

## Search UI → SearchIntent bindings

| Widget | Field |
|--------|-------|
| Zielberufe | `target_roles` |
| Pflicht-Skills | `mandatory_skills` |
| Ausgeschlossene Berufe/Skills/Keywords | `excluded_*` |
| Keywords (Pflicht) | `required_keywords` |
| Remote / Hybrid / Vor Ort | `remote_mode` (`null` if unset) |
| Radius | `radius_km` (`null` if 0) |
| DE / AT / CH | `countries[]` |
| Vollzeit / Teilzeit | `working_time[]` |
| Beschäftigungsart | `employment_types[]` |
| Gehalt | `salary_min` |
| STRICT / BALANCED / EXPLORE | `strictness` (`null` until chosen) |

**Invariant:** widgets never invent STRICT expansion or copy profile skills into
mandatory/target fields. Save dual-writes clear legacy mirrors via
`sync_legacy_jobs_from_intent` only.

## Wheel / Pendelweg

`desktop/widgets/wheel_guard.py` — SpinBoxes ignore wheel unless focused
(click/tab). Page scroll must not change radius. Regression:
`tests/test_profile_search_ux.py`.

## Rollback

- Env: `KARRIEREKRAKE_LEGACY_PROFILE_SEARCH=1`
- Or settings: `legacy_profile_search_ui: true`

Restores CareerSection + search fields on the Profile page (temporary).

## Out of scope

Ranking changes, lifecycle redesign, mobile, profile storage rewrite.
