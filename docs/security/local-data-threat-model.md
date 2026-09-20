# Local data security — threat model & inventory (PR40)

**Status:** binding for desktop token/secret handling.  
**Crypto policy:** OS credential store ([keyring](https://github.com/jaraco/keyring)) +
[cryptography](https://github.com/pyca/cryptography) only where a **named** key
lives in the OS store. **No homemade AES/KDF. No plaintext token fallback.**

“We encrypt everything” is **not** a plan without key management — keys for any
Fernet envelope MUST come from the OS credential store (or force re-login).

## Data classification

| Class | Examples | Persist where | Log? | Export? | Backup? |
|-------|----------|---------------|------|---------|---------|
| **Secret** | OAuth access/refresh tokens, client_secret in token payload | OS keyring only | Never | Never | Never (keyring) |
| **PII high** | Profile, CV files, mail bodies | AppData DB / `cvs/` | Redact | Explicit user export only | User wipe backup may include config — warn |
| **PII low** | Job titles, company names | Local DB | OK short | OK | OK |
| **Config** | settings.yaml, model paths | AppData config | OK | OK | OK |
| **Telemetry** | none shipped | — | — | — | — |

## Inventory — secret / sensitive persistence

| Location | Before PR40 | After PR40 |
|----------|-------------|------------|
| `integrations/secure_tokens.py` | keyring **or** `oauth_*.json` mode 0600 | **keyring only**; legacy file migrate→delete or wipe+re-login |
| `private/gmail_credentials.json` | OAuth client config (user-supplied) | unchanged path; not committed; treated as secret file |
| Drift/SQLite (`data/`) | jobs, emails, lifecycle | no tokens; corruption → fail closed |
| `cvs/`, `cover_letters/` | documents | not logged; secure temp for parse |
| `logs/` | app logs | redaction filter; no tokens/mail/CV |
| `.env` | local overrides | gitignored / content gate |
| Model config / GGUF paths | local paths | no secrets |
| License strings in profile | user field “Führerschein” | PII, not crypto license |

## Threats (minimum)

| Threat | Mitigation |
|--------|------------|
| Token theft from disk | Tokens only in OS credential storage |
| Local user boundary | Windows Credential Locker / macOS Keychain / libsecret per-user |
| Plaintext secret | **STOP** — refuse store if keyring unavailable |
| Debug log leak | `SecretRedactionFilter` on `karrierekrake.*` loggers |
| Temp file leak | `secure_temp_file` 0600 + best-effort wipe |
| Backup persistence | App wipe backup excludes `oauth_*.json`; keyring not copied |
| DB corruption | Detect SQLite malformation; no secret in error strings |
| Export leak | `ExportGate` requires explicit classification + deny secrets |

## Migration

1. If legacy `oauth_<account>.json` exists **and** keyring works → write keyring → verify read → delete file.
2. If keyring unavailable → **delete** insecure file (do not keep) → user must re-login.
3. Never copy plaintext into a “temporary encrypted” file with an app-hardcoded key.

## Rollback

- Feature still callable; `store_token` raises `KeyringUnavailable` → UI prompts re-auth.
- `disconnect_gmail(revoke_remote=True)` clears keyring + legacy files.

## Explicit non-goals

- Homemade crypto
- Claiming “encrypted ⇒ GDPR compliant”
- Mobile push/sync backends (see PR37/PR39)
