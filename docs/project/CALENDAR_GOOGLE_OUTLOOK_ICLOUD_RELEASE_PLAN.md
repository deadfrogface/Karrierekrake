# Lightweight calendar strategy

No new in-app calendar UI, calendar database or background calendar daemon.

## Current code reality
- Google adapter has an OAuth/premium gate and reports disconnected in normal mode.
- Microsoft Graph adapter has protocol and approval logic but requires a configured live client.
- iCloud CalDAV adapter supports discovery, busy checks and approved writes, but needs an account-level live test.
- Local ICS snapshots/subscriptions are read-only; never represent an ICS export as successful remote insertion.
- The approved ICS fallback is compatible with standard calendar import workflows, subject to provider UI behavior.

## Remaining implementation before claiming Google/Outlook/iCloud read+write
1. Google: supported OAuth setup, consent-screen verification as applicable, secure token storage, live FreeBusy and event create, disconnect.
2. Outlook: Microsoft Entra public desktop app registration, PKCE/scopes, live Graph client, calendar read and event create, token refresh.
3. iCloud: app-specific password via secure OS credential store, CalDAV discovery/selection, read/write, connectivity diagnostics.
4. Settings: three provider-specific guided connect flows and explicit read/write status.
5. End-to-end tests: genuine accounts in a private test environment, DST, recurrence, retries, duplicate prevention, revocation, failures.
6. Keep local read-only ICS feed and approved .ics export as low-friction fallback.

Do not ship or advertise direct provider sync as completed until all gates pass.
