# CalDAV and application reliability — 2026-10-01

Base: origin/main f62642b. Branch: codex/app-reliability-optimize-20261001.
No merge or public release claimed. Qwen3.5-4B remains the single production model.

## Implemented

- Settings now provide CalDAV HTTPS URL / username / app-password entry, authenticated calendar discovery and calendar selection. Credentials are stored via the existing OS-keyring layer, not the settings YAML. IMAP has matching credential entry and an authentication check.
- Live CalDAV uses python-caldav 3.3.1: discovery, selected calendar, recurring-event expansion, all-day events, timezone conversion, opaque busy intervals and approved PUT. Writes use If-None-Match / ETag, and a retry cannot overwrite a conflicting event. Each HTTP session closes. HTTP and embedded URL credentials are rejected; TLS verification stays enabled.
- Lifecycle calendar UI now asks for an invitation/date text, queries the selected provider, offers actual available slots and writes only after explicit approval with allow_calendar_write enabled. Availability is rechecked before writing. Failure leaves the proposal available for retry, with no success claim.
- Google Calendar no longer substitutes an empty mock calendar or in-memory write transport in production. It builds a Calendar service from stored Google credentials. FreeBusy errors/missing calendars fail closed. Approved events use a stable ID.
- Provider probes/OAuth are background tasks. Google callback waits are bounded. Probe cache is isolated by account directory; Google scopes accept strings/lists. IMAP fetch uses stable account+UIDVALIDITY+UID IDs, BODY.PEEK and guaranteed cleanup.
- CV omitted-list repair from the separate fake-mail branch is ported without demo activation. Explicit skills/language/tool/certificate sections trigger a focused grounded retry rather than silent data loss.
- Windows artifacts upload the release ZIP once instead of uploading the same large EXE again alongside it. Artifact compression is disabled for the already compressed ZIP. No model or user functionality removed.
- Packaged startup smoke now exercises CalDAV/TLS/timezone/recurrence dependencies, without contacting an account. Windows pre-build tests include calendar, matching, inbox association and text safety.

## Evidence and limits

| Run | Result | What it proves |
|---|---|---|
| Matching/search/mail/scheduling/gold first selection | 929 passed, 17 skipped | deterministic component/synthetic lifecycle behavior; skipped scenarios are not PASS |
| UI/inbox/source guards and fake-provider E2E selection | 864 passed, 1 network test deselected | synthetic/component/Qt behavior, not real portal/account availability |
| Text-quality/gold/response/GUI selection | 431 passed | gold rules, source grounding, refusal/approval behavior; no fresh live Qwen quality score |
| Exact Windows pre-build selection on Linux/offscreen Qt | 1002 passed, no skips | new transport wiring and regressions including GUI heartbeat and explicit approval |
| Additional provider/settings/regression selection | 168 passed | credential/probe and import regression checks |
| Privacy scan | PASS | tracked source scan |
| Live Contentful public-board query | UNVERIFIED — URLError | execution environment could not access endpoint; not source success/failure evidence |
| Windows EXE install/import/preview/apply/restart/letter | Pending remote build | must inspect actual workflow result and artifact |
| Real CalDAV/Google/IMAP account | NOT TESTED | no user credentials used and no real event/email sent |
| Laptop i3 peak/latency | NOT TESTED | cloud runner is not the target device |

These runs overlap; their counts must not be added together as a unique total.
The frozen NV3 parser score remains 0.980; these tests are not a new independent 99% measurement.

## Remaining functional limits

- Microsoft Graph calendar's live client remains unimplemented; adapter currently requires injection. It fails explicitly, not silently switching providers.
- Calendar UI now performs real proposal/create flow; provider-wide appointment updates/deletion and an event timeline are not added in this change.
- Loopback HTTPS Radicale test passed discovery, recurring-event expansion with EXDATE, event creation and duplicate retry using the actual python-caldav HTTP protocol. This exposed and fixed an invalid GET-method call in the retry path. Library event-body warnings are suppressed to protect calendar contents. External-provider compatibility still needs a dedicated account test.
- Network portal availability, real OAuth grants and actual Qwen-generated letter/reply quality need live evidence. Existing gold and safety tests are not substituted for that evidence.
