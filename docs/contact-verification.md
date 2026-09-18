# Contact Verification & Writer Integration (PR26)

Discovered `ContactCandidate`s (PR25) are **never** used automatically in
applications. Pipeline:

```
Discovery → Verification → Usage Policy → Writer
```

## Verification status

| Status | Meaning |
|--------|---------|
| `VERIFIED` | Strong job/ATS evidence, no conflict, not stale — writer may use person |
| `UNVERIFIED` | Default (migration) / weak company-page contact / incomplete |
| `REVIEW` | Conflicts, homonyms, ambiguous strong persons — neutral fallback |
| `REJECTED` | Generic mailbox, missing name, gender/salutation inference |
| `STALE` | Page/contact older than `contact_discovery_stale_after_days` |
| `DISABLED` | `contact_verification_enabled: false` |

## Evidence strength

| Strength | Sources | Writer person use |
|----------|---------|-------------------|
| `STRONG` | `job_posting_text`, `job_posting_jsonld`, `ats_metadata` | Allowed when `VERIFIED` |
| `WEAK` | `company_career_page`, `company_contact_page`, `recruiter_signature` | Display only — **not** job-specific |
| `NONE` | unknown / not found | Never |

## Salutation

- `SALUTATION_ALLOWED` only with **explicit** evidence (`Frau`/`Herr`/… in quote).
- No gender guessing from first names.
- Neutral product fallback: `Sehr geehrte Damen und Herren`.

## Writer contract (`WriterContactClaims`)

| Field | Rule |
|-------|------|
| `CONTACT_VERIFIED` | true only for strong + verified + binding on |
| `CONTACT_NAME` / `CONTACT_ROLE` / `CONTACT_SOURCE` | empty when not verified |
| `SALUTATION_ALLOWED` | true only with explicit salutation evidence |

If `CONTACT_VERIFIED` is false, the writer **must not** add a person.

## Feature toggles

| Key | Default | Effect |
|-----|---------|--------|
| `contact_verification_enabled` | `true` | Master verification switch |
| `contact_writer_binding_enabled` | `true` | Writer consumes verified claims; set `false` to rollback binding |

Discovery toggle (`contact_discovery_enabled`) remains independent (PR25).

## Migration

Existing recruiting contacts default to `UNVERIFIED`. Provenance JSON is kept.

## Rollback

1. Set `contact_writer_binding_enabled: false` — writer ignores person claims; provenance remains.
2. Optionally set `contact_verification_enabled: false` — status becomes `DISABLED`.
3. Discovery cache / `recruiting_contacts` rows are untouched.

## Acceptance

| Gate | Check |
|------|-------|
| UNIT | 0 invented contacts/salutations |
| E2E | Discovery→Verification→Plan→Cover only verified contact |
| BETA | Uncertainty visible when not verified |
| COMMERCIAL | 0 unchecked persons auto-inserted into applications |
