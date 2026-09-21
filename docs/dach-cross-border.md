# DACH cross-border geography (local-first)

**Status:** BINDING with `docs/architecture/local_first_google_calendar_and_geo.md`

## Rules

1. Distance is **airline (Luftlinie)** via local Haversine (`haversine_v1`).
2. Coordinates come from the versioned GeoNames/pgeocode DACH snapshot — never Google Maps.
3. Public Nominatim is **forbidden**.
4. Cross-border DE/AT/CH distances are allowed when the toggle is on.
5. Ambiguous / unknown places stay UNKNOWN — never invent 0 km.
6. UI label: **„ca. X km Luftlinie“** (`distance_source == haversine_v1`).

## Pipeline order

Fachliches matching first → local geo only for suitable candidates → radius filter.
