# Google OAuth test accounts

Use **only** accounts listed on the Cloud Console OAuth consent screen
(Testing) or approved production test users.

## Recommended roles

| Account | Role | Notes |
|---------|------|-------|
| `oauth-gmail-only@…` | Gmail-only | Connect Gmail; Calendar FreeBusy **off** |
| `oauth-cal-only@…` | Calendar-only | FreeBusy enabled; do not connect Gmail |
| `oauth-both@…` | Incremental | Gmail first, then enable FreeBusy (scope upgrade) |
| `oauth-partial@…` | Partial consent | Deny Calendar on consent screen; Gmail must still work |
| `oauth-revoke@…` | Disconnect | Connect then Settings → Disconnect Google; confirm revoke |

## Instructions for testers

1. Confirm Console project is the **dev/test** project (not production).
2. Confirm you are on the test-user allowlist.
3. Use the **system browser** consent page (address bar visible).
4. On the consent screen, verify requested scopes match the feature under test
   (no `gmail.modify`, no `mail.google.com`, no full `calendar`).
5. After disconnect, confirm a new connect shows the consent screen again
   (refresh token revoked / wiped).

## Do not

- Share production client secrets in chat or commits
- Add personal `@gmail.com` accounts that are not on the allowlist
- Approve broader scopes “to unblock testing”
