# DACH Cross-Border Commute (PR24)

## Summary

Karrierekrake treats **commute radius mathematically** (Haversine on WGS84), not
nationally. A job in CH or AT that is within the configured kilometre radius of
the home coordinates is **inside** the filter — the border is not a distance
barrier.

Example (public reference coordinates):

| Home | Radius | Job | Result |
|------|--------|-----|--------|
| Konstanz DE | 25 km | DE workplace ~20 km | inside |
| Konstanz DE | 25 km | Kreuzlingen CH ~6 km | inside |
| Konstanz DE | 25 km | Innsbruck AT ~140+ km | outside |

## Feature toggle / rollback

- Settings: `cross_border_dach_enabled` (default `true`) in `config/settings.yaml`
- Profile mirror: `location.cross_border_dach`
- **Off:** place resolution restricted to the profile home country; country
  intent gates are not expanded to DACH.
- Unresolvable places → distance `UNKNOWN` (`None`), never a guessed kilometre.

## What this is / is not

**Is:**

- DE / AT / CH ISO country normalization
- Offline-first PLZ → coordinates via **pgeocode** (GeoNames data)
- Cross-border Haversine
- Versioned geocode cache (`data_source`, `data_version`)
- Remote jobs skip workplace radius (still subject to remote allow flags)

**Is not:**

- Tax, visa, or Grenzgänger legal advice
- A claim of full AT/CH job-board coverage
- Active commercial marketing in AT/CH
- Anti-bot bypass or unlimited Nominatim use

## Source matrix (commercial honesty)

| Source | Board geography | Country on Job | Notes |
|--------|-----------------|----------------|-------|
| Bundesagentur | DE | `DE` | Official ATS/API; preferred when available |
| Indeed (JobSpy) | DE (`country_indeed=germany`) | Normalized from location text; default DE | **Isolated** — not expanded to AT/CH boards |
| StepStone / XING | Primarily DE sites | From JSON-LD `addressCountry` / text | No AT/CH coverage claim |
| Company sites | Placeholder | — | Prefer official Greenhouse/Lever feeds later |
| Greenhouse / Lever apply | Apply path only | — | Not discovery coverage |

## Place resolution order

1. Explicit lat/lon on the job (trusted as given)
2. Offline **pgeocode** for DE/AT/CH postal codes (requires country when PLZ is
   ambiguous across AT/CH, e.g. `6900`)
3. Cached Nominatim (rate-limited, negative-cached, DACH `countrycodes` when
   cross-border is on)
4. Else **UNKNOWN** — no invented distance

## Migration

- `jobs.country_code` added (lazy fill on enrich; no mass UPDATE without backup)
- `geocode_cache` gains `data_source`, `data_version`, `country_code`,
  `resolution_status`; legacy rows remain readable
- Current pgeocode provenance: `pgeocode` / `geonames-pgeocode-0.5`

## Dependencies

- [pgeocode](https://github.com/symerio/pgeocode) — local PLZ (GeoNames CC-BY)
- [geopy](https://github.com/geopy/geopy) — available for Nominatim helpers;
  primary HTTP path remains rate-limited `httpx` + SQLite cache

## Tests

- `tests/test_dach_cross_border.py` — border / Haversine / cache / offline / remote
- `tests/test_dach_source_normalization.py` — country & source field matrix
