# Profile Data Integrity (PR20)

## Source of truth

Persisted YAML under AppData (`config/application_profile.yaml`, `config/profile.yaml`,
`config/settings.yaml`) is the **source of truth**. The UI loads from storage, applies an
explicit `ProfilePatch`, validates, saves atomically, then reloads for display.

```
UI → ProfilePatch → validate → atomic save_config → disk → reload → UI
```

## Patch operations

| Op | Meaning |
|----|---------|
| `UNCHANGED` | Leave persisted value alone (missing key or explicit no-op) |
| `SET(value)` | Write a non-empty normalized value; origin → `manual` |
| `CLEAR` | Write empty/default for that field; origin → `manual` |
| `DELETE_SECTION` | Empty one qualifications list (skills, languages, …) |
| `DELETE_PROFILE` | Wipe applicant + qualifications in memory (caller persists) |

Semantics that must never be conflated:

- `None` / absent key → `UNCHANGED`
- `""` / whitespace-only text → `CLEAR` (not `SET("")`, not `UNCHANGED`)
- Explicit user clear sets `field_origins[name] = manual` so CV summary sync cannot resurrect

`PATCH_SCHEMA_VERSION` (in `desktop/services/profile_patch.py`) is stored in `meta.json`
as `profile_patch_schema` after reset/wipe for diagnostics.

## Anti-resurrection (CV vs manual)

`sync_application_summaries(..., fill_empty=False)` on normal profile save:

- `SOURCE_MANUAL` summaries are never overwritten (includes explicit CLEAR)
- `SOURCE_CV` may refresh from structured qualifications
- Untagged empty fields stay empty unless `fill_empty=True` (CV import only)

CV import calls `fill_empty=True`. Manual clear after CV import must survive save/restart.

## Reset / delete scopes (UX must match)

| Scope | Removes | Keeps |
|-------|---------|-------|
| Nur CV-Daten | CV-sourced quals/personal fields + CV files | Manual entries, search prefs, settings, job DB |
| Profil + Dokumente | Applicant PII, quals, answers, CV files | Search prefs (PR22), settings, job history |
| Alle lokalen Daten | Config, search prefs, settings, job DB, logs, CVs, cache | Install dir; optional `.wipe_backup_*` under AppData |

Search preferences are **not** cleared by profile reset (reserved for PR22 SearchIntent).

## Atomic persistence & crash safety

`core.config._dump_yaml` writes `*.tmp`, `fsync`s, then `os.replace`. A crash mid-replace
keeps the previous good YAML. Failed migrations / wipes must not destroy the only copy:
`delete_all_local_data` best-effort copies `config/` to `.wipe_backup_<stamp>/` first.

## Migration

- No destructive YAML schema rewrite in PR20; patch semantics are additive.
- Legacy profiles without `field_origins` load normally; untagged non-empty summary fields
  remain CV-like for sync; empty fields are not filled on save.
- AppData folder rename still uses `desktop/legacy_migration.py` (copy, leave legacy intact).
- If a future schema bump is required: raise `PATCH_SCHEMA_VERSION`, backup before mutate,
  keep fixtures under `tests/fixtures/profile_migration/`, abort without destroying originals.

## Rollback

- Failed wipe: restore from `.wipe_backup_*` if present
- Failed save: prior YAML remains via atomic replace
- New patch semantics are versioned; do not mass-mutate legacy profiles in place

## Out of scope

SearchIntent redesign (PR22), DACH, production sanitization, UI redesign, Günther tuning.
