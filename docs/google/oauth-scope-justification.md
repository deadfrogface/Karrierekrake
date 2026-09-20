# OAuth scope justification (Google Cloud Console)

Copy these justifications into the OAuth consent screen / verification questionnaire.
Do **not** invent additional Restricted scopes.

## Scopes in use

### `https://www.googleapis.com/auth/gmail.readonly` — Restricted

**Feature:** Application email sync and case association.

**Justification:** Karrierekrake reads recruiting-related inbox messages on the
user's device to link employer replies to open applications. The app does not
send, modify, label, or delete mail. Access tokens stay in the OS keyring;
there is no server-side mailbox mirror for Google verification purposes beyond
what the local desktop app stores under the user's control.

**Why not a narrower scope:** Gmail offers no non-Restricted scope that returns
message bodies required for classification. `gmail.metadata` is insufficient.

**Data use / retention:** Local SQLite + AppData only; user can export, delete
mail cache, or disconnect Google (remote revoke) at any time. See
`docs/privacy/data-inventory.md`.

**Security assessment:** Restricted Gmail scopes may require a Google security
assessment / CASA if the app is multi-user production. Track status in the
commercial launch checklist; do not expand scopes to avoid assessment.

### `https://www.googleapis.com/auth/calendar.freebusy` — Sensitive

**Feature:** Interview slot finding.

**Justification:** Query opaque busy intervals only. The app never requests
event titles, attendees, or full calendar contents. Prefer this over
`calendar.readonly`.

### `https://www.googleapis.com/auth/calendar.events` — Sensitive

**Feature:** Create calendar events **after** explicit user approval of a draft.

**Justification:** Write is opt-in (`allow_calendar_write`) and gated behind
approval UI. Not requested at Gmail connect time. Incremental upgrade only when
the user enables the feature.

## Explicitly out of scope (do not add to Console)

- `https://mail.google.com/`
- `gmail.modify` / `gmail.compose` / `gmail.send` / `gmail.insert`
- `https://www.googleapis.com/auth/calendar` (full)
- `calendar.readonly` (superseded by freebusy for our use case)

## Privacy policy & homepage

Production consent requires a public homepage and privacy policy on a verified
domain (`oauth_homepage_url`, `oauth_privacy_policy_url` in settings). Hosted
policy must describe Google user data use consistent with this document and
the DSGVO inventory.
