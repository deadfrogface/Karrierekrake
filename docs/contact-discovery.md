# Recruiting Contact Discovery — Source & Retention Policy (PR25)

Provenance-backed discovery of a **named recruiting contact** for a concrete
job. Generic mailboxes (`info@`, `jobs@`, …) are never promoted to a person.
`NOT_FOUND` is a **successful** outcome, not an error.

## Source priority

| Rank | `source_type` | Input |
|------|---------------|--------|
| 1 | `job_posting_text` | Visible text of the job posting |
| 2 | `job_posting_jsonld` | schema.org `JobPosting` / `applicationContact` / `contactPoint` |
| 3 | `ats_metadata` | ATS adapter fields (recruiter name/email) |
| 4 | `company_career_page` | Public company career page (opt-in fetch) |
| 5 | `company_contact_page` | Public recruiting/contact page (opt-in fetch) |
| 6 | `recruiter_signature` | Signature from an **already correctly associated** email thread |
| 7 | `not_found` | No usable person contact |

Higher-priority sources win when multiple usable persons exist.

## Evidence rules

- Every populated field on `ContactCandidate` (`name`, `role`, `department`,
  `email`, `phone`) **must** have at least one `ContactEvidence` quote.
- No invented names, no gender/salutation inference, no LinkedIn-as-required.
- Raw HTML is **not** persisted — only short evidence quotes and structured
  payload JSON.
- Schema version: `CONTACT_SCHEMA_VERSION` (currently `1`).

## Feature toggle & controls

Settings (`SettingsConfig` / `config/settings.yaml.example`):

| Key | Default | Meaning |
|-----|---------|---------|
| `contact_discovery_enabled` | `false` | Master switch |
| `contact_discovery_max_fetches_per_run` | `20` | Network fetch budget |
| `contact_discovery_min_interval_seconds` | `1.0` | Rate limit between fetches |
| `contact_discovery_cache_ttl_hours` | `168` | Cache TTL (7 days) |
| `contact_discovery_stale_after_days` | `90` | Flag contacts from old page timestamps |
| `contact_discovery_allow_retro_crawl` | `false` | Mass historical web crawl — **off** |

API: `core.contacts.api.format_discovery_status` / `discover_for_job_payload`.
Invalidate/delete: `ContactDiscoveryService.invalidate` / `.delete` and
`Database.invalidate_recruiting_contacts` / `delete_recruiting_contacts`.

## Network / ToS stop conditions

Do **not** bypass:

- Login / SSO walls
- Paywalls
- Anti-bot challenges
- Unclear site ToS for automated extraction

On `401` / `403` / login/paywall signals the pipeline returns `BLOCKED` and
stops. LinkedIn scraping is **not** a required source.

Optional libraries (clear OSS licenses; bs4/lxml fallback always works):

- [extruct](https://github.com/scrapinghub/extruct) (BSD)
- [selectolax](https://github.com/rushter/selectolax) (MIT)
- [trafilatura](https://github.com/adbar/trafilatura) (Apache-2.0 / GPL-3.0+)
- [schema.org JobPosting](https://schema.org/JobPosting)

## Retention (PR42 finalizes enforcement)

Recruiting contacts are **third-party personal data**. This PR documents intent;
hard retention jobs land in PR42.

| Rule | Intent |
|------|--------|
| Necessity | Store only fields needed to contact / attribute provenance |
| Cache TTL | Default 7 days for discovery cache rows |
| Stale flag | Page timestamps older than 90 days → `STALE` status |
| User delete | Invalidate or hard-delete per job/case/contact id |
| Feature off | Toggle disables new discovery; existing rows remain until deleted |
| No mass retro | No bulk re-crawl of historical jobs without `allow_retro_crawl` |
| Packaging | Fixtures stay under `tests/`; not in EXE allowlist |

## Rollback

1. Set `contact_discovery_enabled: false`.
2. `DELETE FROM recruiting_contacts` or call `delete_recruiting_contacts`.
3. Remove/ignore `core/contacts` usage; schema table is inert when unused.

## Acceptance mapping

| Gate | Check |
|------|--------|
| UNIT | No field without evidence (`validate_evidence()` empty) |
| E2E | Job-specific contact exact; none → `NOT_FOUND` |
| BETA | UI/API shows only evidenced `format_discovery_status` payload |
| COMMERCIAL | Every usable person has provenance + timestamp |
