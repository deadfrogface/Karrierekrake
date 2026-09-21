# NEXT-05 Release Gate — Google Maps Only Geo & Commute

**Date:** 2026-09-21  
**Branch:** `cursor/next-05-google-maps-geo-d85b`

## Acceptance

| Gate | Result |
|------|--------|
| **GOOGLE ONLY** | **YES** — Geocoding API + Routes Compute Route Matrix Essentials via `integrations/maps` |
| **OSRM** | **NO** — not used |
| **NOMINATIM** | **NO** — removed from production `LocationService` path |
| **PGEOCODE** | **NO** — not authoritative for commute / geocode |
| **HAVERSINE AUTHORITATIVE** | **NO** — diagnostic/tests only; never writes `Job.distance_km` |
| **REAL ROAD DISTANCE** | **PASS** — `distance_km` from Route Matrix `distanceMeters` |
| **REAL DURATION** | **PASS** — `commute_duration_minutes` from Matrix `duration` (TRAFFIC_UNAWARE) |
| **SECURE KEY HANDLING** | **PASS** — API key only in maps proxy process; desktop uses Bearer token |

## Semantics

`max_commute_km = 20` means **drivable road route ≤ 20 km**, not straight-line.

If Google fails → `DISTANCE_UNKNOWN` (`None`). **No** Haversine fallback.

## UI

- „km Fahrt“ / drive label **only** when `distance_source == google_route_matrix`
- Example: `18 km Fahrt · ca. 24 Min.`
- Raw Haversine must never be displayed as Fahrtstrecke

## Cost / bill guards

Meters (no addresses in logs):

- `google.geocoding.requests`
- `google.route_matrix.elements`

Guards: per-run max, hourly/monthly quotas, budget alert, rate limit, retry/fingerprint duplicate protection.

## SKU

Default: **Essentials** / `TRAFFIC_UNAWARE`.  
Proxy rejects `TRAFFIC_AWARE_OPTIMAL` and waypoint Pro features without cost approval.

## Proxy

```bash
export KARRIEREKRAKE_GOOGLE_MAPS_API_KEY=...
export KARRIEREKRAKE_MAPS_PROXY_TOKEN=...
python -m integrations.maps.proxy
# Desktop:
export KARRIEREKRAKE_MAPS_PROXY_URL=http://127.0.0.1:8765
export KARRIEREKRAKE_MAPS_PROXY_TOKEN=...
```

Endpoints only: `POST /v1/geocode`, `POST /v1/route-matrix`, `GET /v1/health`.

## Tests

```bash
pytest tests/test_next05_google_maps.py -q
```

Includes airline-inside / road-outside → OUTSIDE radius.
