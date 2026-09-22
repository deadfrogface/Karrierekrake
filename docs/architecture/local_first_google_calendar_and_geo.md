# Local-first Google Calendar & Geo (no Karrierekrake backend)

## Decision

Karrierekrake is a **local Windows desktop application**. There is **no** Karrierekrake
backend server, **no** central user database, and **no** cloud sync for profiles,
applications, calendar data, or OAuth tokens.

## Why no server

- User data (CV, applications, calendar free/busy, tokens) must stay on the customer PC.
- A proxy would put tokens and calendar content on provider infrastructure — rejected.
- Desktop OAuth (loopback + PKCE) talks **directly** to Google from the customer PC.

## Google data flow

```
Karrierekrake (PC)
  → system browser + Google consent
  → Google OAuth / Calendar API
  → OS credential store (keyring / Windows Credential Manager)
```

No Karrierekrake host sits in the middle. Tokens are never written to SQLite, JSON,
`.env`, logs, crash reports, or backups.

## Scopes (minimal)

| Mode | Purpose | Scopes |
|------|---------|--------|
| A | Availability only | `calendar.freebusy` |
| B | Availability + create owned events after approval | `calendar.freebusy` + `calendar.events.owned` |

Full `calendar` scope is forbidden. Mode upgrades require a new consent (Installed apps
do not support arbitrary incremental scope expansion reliably).

Gmail readonly remains a separate feature and is **not** widened by this decision.

## Calendar behaviour

- FreeBusy only when the user opens the scheduler or explicitly refreshes (no background poll).
- Short local cache (~5 minutes); conservative rate limits; truncated exponential backoff on 403/429.
- Events only after explicit user approval; idempotent via local action id / private extended property.
- Failed event create ≠ `SCHEDULED`.
- On quota / auth / offline failure → **ICS export** (RFC 5545) with stable UID.

## Why Google Maps was removed

NEXT-05 introduced Geocoding + Route Matrix via an authenticated maps proxy. That required
API keys, metered billing risk, and (in the proxy design) infrastructure. Binding product
rules forbid:

- Google Maps / Places / Distance Matrix / Routes
- Any Karrierekrake Maps API key
- User-supplied Google Cloud developer keys for maps

## Why public Nominatim is forbidden

The OSMF Nominatim usage policy forbids bulk / production geocoding of private addresses
against `nominatim.openstreetmap.org`. We do not use geopy’s Nominatim default either.

## Local geo (authoritative)

1. Bundled, versioned DACH GeoNames postal snapshot (`data/geo/`, GeoNames CC-BY).
2. Optional controlled update: download **directly** from GeoNames / postal-codes-data mirrors
   (country code only in URL — no user addresses).
3. Validate → atomic activate → rollback on failure; offline keeps last good set.
4. Resolve order: trusted coords → `country+PLZ` → unique `country+city` → UNKNOWN (never guess).
5. Distance: **Haversine** `haversine_v1`, R = 6371.0088 km — UI label **„ca. X km Luftlinie“**.
6. No drive time / road distance claims in v1.

## Search / filter order

```
sources → normalize → dedupe → hard fachliche filters → matching/ranking
  → fachlich suitable candidates
  → local geo resolve → airline distance → radius filter
  → final list (fachliches ranking primary; distance secondary tie-breaker)
```

Geo is **not** run for fachlich excluded raw jobs. Radius is a hard user filter but applied
after matching so nearby matches are not dropped by an early Top-N cut.

## Remaining operator duties (outside this repo)

1. Google Cloud OAuth client (Desktop) for production — separate from any Maps project.
2. OAuth consent screen, verification for restricted/sensitive scopes as required by Google.
3. Public homepage + privacy policy URLs configured in settings (no secrets in git).
4. License/attribution review for GeoNames and other OSS (see NOTICE / About).

## Related code

- `core/geo_dataset.py`, `core/geo_resolve.py`, `core/location.py`
- `integrations/google_oauth.py`, `integrations/secure_tokens.py`
- `integrations/calendar_freebusy.py`, `integrations/ics_export.py`
- `docs/operators/google-oauth-production-setup.md`
