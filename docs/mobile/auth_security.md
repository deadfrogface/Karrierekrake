# PR39 — Mobile Auth / Secure Storage / Calendar Approval

## Inspection summary

| Area | Finding |
|------|---------|
| Android Manifest | Launcher only — no App Links / OAuth redirect yet (added here) |
| iOS entitlements | None — Universal Links / URL scheme added here |
| Mobile auth | Absent in PR38 — native AppAuth+PKCE layer added |
| PR37 sync | **UNSPECIFIED** — still binding |
| Desktop OAuth | Loopback `localhost` — **forbidden** on mobile |
| Calendar | Slot select local; write gated |
| Push | Needs backend → **Future Work**, not invented |
| Secure storage | None — `flutter_secure_storage` only (no plaintext fallback) |

## Hard rules (STOP)

- No WebView OAuth
- No plaintext token fallback
- No broad OAuth scopes
- No invented push/sync backend
- No sensitive mail/job data in notification payloads
- Client secrets in installed apps are **not** confidential — public client + PKCE

## Push

**Future work.** Remote push requires an approved transport/backend
(see `docs/mobile/sync_decision.md`). Until then:

- No FCM/APNs wiring
- No device-token upload
- Local OS notifications for on-device reminders only (optional, no PII payload)

## Rollback

- Feature flags disable OAuth / calendar-write attempt / deep-link handling
- `revoke()` clears secure storage
- Uninstall removes Keystore/Keychain entries for the app
