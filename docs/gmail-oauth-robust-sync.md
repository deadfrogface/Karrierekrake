# Gmail OAuth & robust sync (PR27)

**Branch intent:** Harden existing `integrations/gmail_auth.py` + `integrations/gmail_sync.py`
(readonly). Do **not** rewrite the stack.

## Scope decision

| Capability | Scope |
|------------|--------|
| Sync / read / history | `https://www.googleapis.com/auth/gmail.readonly` **only** |
| Compose / send / modify | **Not** requested in this PR |
| Pub/Sub push | **Not** required |

## Behaviour

- **Initial sync:** paginated `messages.list` with bounded `newer_than:…` query (not unbounded mailbox dump every start).
- **Incremental:** `users.history.list` from persisted `historyId`.
- **Invalid historyId (404):** controlled **full sync fallback**; **never** wipe `email_messages`.
- **Cursor:** versioned JSON in `app_meta` (`gmail_sync_cursor_v1`, `CURSOR_SCHEMA_VERSION`).
- **Dedupe:** skip known `gmail_id` before callbacks; `process_parsed_email` returns `status=duplicate` (no duplicate lifecycle events).
## Tokens (PR40)

- **Storage:** OS credential store via `keyring` only (`integrations/secure_tokens.py`).
- **No plaintext fallback.** Legacy `oauth_*.json` is migrated once into keyring then wiped;
  if migration fails, the file is destroyed and the user must re-login.
- Disconnect + optional remote revoke; refresh failures clear local token and signal `needs_reauth`.
- **Logs:** exception types / message ids only — redaction filter strips tokens/mail/CV
  (`core.security.redaction`). See `docs/security/local-data-threat-model.md`.


## Acceptance mapping

| Gate | Expectation |
|------|-------------|
| UNIT | No duplicate processing for same `gmail_id` |
| E2E (mocked) | Initial → restart → incremental; each message once |
| BETA | `gmail_sync_enabled` default **off** (opt-in test accounts) |
| COMMERCIAL | Least privilege + disconnect/revoke + no PII logs |

## Production Google compliance

**PR43** — Cloud Console verification / production OAuth branding & policy.
This PR documents the dependency only; it does not implement Console verification.

## Rollback

- Revert to prior sync entrypoint (`sync_recent`) if needed.
- Cursor schema mismatch → full sync without deleting stored emails.
- Sync must not re-fire lifecycle events for already-ingested `gmail_id`s.
