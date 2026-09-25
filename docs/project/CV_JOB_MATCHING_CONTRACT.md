# CV ↔ Job / Profile Matching Contract (Docpick import)

**Contract version:** `PARSED_CV_CONTRACT_VERSION = 1`  
**Source of truth:** `core.cv_docpick_import.suggestion_to_parsed` → profile merge / matching.

## Frozen top-level keys (no silent drift)

| Key | Type (logical) | Consumer |
|-----|----------------|----------|
| `personal` | object | profile applicant fields |
| `emails` | list[str] | profile email |
| `phones` | list[str] | profile phone |
| `languages` | list[{language, level}] | qualifications / matching language filters |
| `driving_license` | str (space-joined classes) | qualifications / hard filters |
| `education` | list[{institution, qualification, start_date, end_date}] | qualifications |
| `work_experience` | list[{title, company, start_date, end_date, responsibilities}] | qualifications / matching experience |
| `skills` | list[str] | qualifications / matching skills |
| `software` | list[str] | qualifications / matching tools |
| `certificates` | list[{name, issuer, year}] | qualifications |

### `personal` keys

`first_name`, `last_name`, `street`, `house_number`, `postal_code`, `city`, `country`, `date_of_birth`

## Diff vs previous (this PR)

| Change | Justification |
|--------|----------------|
| **None** to field names/types | Round8 quality fixes only postprocess values (`heute` repair, education enrich). Shape unchanged. |
| Additive metadata only | `parsed_cv_contract_version`, `peak_rss_mb_at_end` — not matching inputs |

If a future change renames/removes a key or changes list/object types, bump `PARSED_CV_CONTRACT_VERSION` and append an explicit Diff here.

## Guards

- `import_cv_docpick` raises `contract_drift` if any frozen top-level key is missing.
- Unit test `test_parsed_cv_matching_contract_stable` locks the set.
