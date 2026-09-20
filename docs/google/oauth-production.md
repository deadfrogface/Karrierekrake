# Google OAuth — feature → scope matrix & verification (PR43)

Official references:

- [OAuth 2.0 Policies](https://developers.google.com/identity/protocols/oauth2/policies)
- [Gmail API scopes](https://developers.google.com/workspace/gmail/api/auth/scopes)
- [Calendar API scopes](https://developers.google.com/workspace/calendar/api/auth)
- [google-auth-library-python](https://github.com/googleapis/google-auth-library-python)
- [google-api-python-client](https://github.com/googleapis/google-api-python-client)

## Feature → scope matrix (production allowlist)

| Product feature | Scope | Sensitivity | When requested |
|-----------------|-------|-------------|----------------|
| Mail lesen / Sync | `gmail.readonly` | **Restricted** | Only if user connects Gmail / `gmail_sync_enabled` |
| Calendar Slot Finding | `calendar.freebusy` | Sensitive | Only if FreeBusy feature enabled + user connects Calendar |
| Calendar Event Write | `calendar.events` | Sensitive | Only after user enables write + approves a draft |
| Draft / Compose / Send | — | — | **Not a product feature** — not requested |
| Full mailbox / modify | `gmail.modify`, `mail.google.com` | Restricted | **Forbidden** |
| Full calendar | `calendar` / `calendar.readonly` | — | **Forbidden** (prefer `freebusy`) |

Implementation: `integrations/google_oauth.py` (`FEATURE_SCOPE_MATRIX`, `ALLOWED_SCOPES`, `FORBIDDEN_SCOPES`).

## Least-privilege rules

1. **No scopes “for later”.** Flags off ⇒ scopes not requested.
2. **Incremental authorization** with `include_granted_scopes=true` — Gmail-only users can later add FreeBusy without dropping Gmail.
3. **Partial consent:** denied scopes disable the matching feature; other features keep working.
4. **System browser only** (`open_browser=True`) — no embedded WebView.
5. **PKCE** enabled on `InstalledAppFlow` (library + explicit verifier).
6. **Broader legacy grants** → remote revoke + local wipe + reconsent (never reuse indefinitely).
7. **STOP:** adding any *new* Restricted scope (beyond existing `gmail.readonly`) requires Privacy/Security review (`RestrictedScopeReviewRequired`).

## Dev vs production clients

| | Development | Production |
|--|-------------|------------|
| Cloud project | Separate test project | Separate production project |
| Consent screen | Testing / test users only | Verified brand + scopes |
| `oauth_environment` | `development` (default) | `production` |
| Privacy policy URL | Optional | **Required** (`oauth_privacy_policy_url`) |
| Homepage URL | Optional | **Required** (`oauth_homepage_url`) |

Override gate for CI/local: `KARRIEREKRAKE_OAUTH_ALLOW_UNVERIFIED=1` (never ship that in production builds).

Credentials (`private/gmail_credentials.json`) must **never** be committed.

## Desktop vs mobile

| | Desktop | Mobile companion |
|--|---------|------------------|
| Gmail/Calendar Google APIs | Yes (this matrix) | **No** — OIDC placeholder only |
| Redirect | Loopback localhost | App scheme / App Links (no loopback) |
| Browser | System browser | Custom Tabs / ASWebAuthenticationSession |
| Forbidden scopes | Allowlist enforced | Also blocks Gmail Restricted + full calendar |

## Migration

Stored tokens whose scopes include anything outside `ALLOWED_SCOPES` are treated as broader grants:

1. Best-effort `POST https://oauth2.googleapis.com/revoke`
2. Delete keyring entries (`gmail_readonly` / `google_oauth`)
3. UI signals reconsent (`scope_mismatch`)

## Beta / commercial gates

| Gate | Expectation |
|------|-------------|
| UNIT | Allowlist 100% — see `tests/test_google_oauth_production.py` |
| E2E (mocked) | Gmail-only **or** Calendar-only; upgrade only on feature activation |
| BETA | Approved test/production consent screen; test accounts only |
| COMMERCIAL | Restricted (`gmail.readonly`) verification + Sensitive calendar scopes submitted; CASA/security assessment if Google requires it for Restricted mail data |

## Related docs

- `docs/google/oauth-scope-justification.md` — Console verification copy
- `docs/google/oauth-test-accounts.md` — test users
- `docs/google/oauth-screencast-checklist.md` — verification video
- `docs/gmail-oauth-robust-sync.md` — sync behaviour (readonly)
