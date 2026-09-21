# DACH cross-border commute (NEXT-05 — Google Maps)

> **Authoritative production geo:** Google Maps Platform only  
> (Geocoding API + Routes Compute Route Matrix Essentials).  
> Haversine / pgeocode / Nominatim are **not** production distance providers.

Karrierekrake treats **commute radius as drivable road distance**
(`max_commute_km` = road route kilometres via Google Route Matrix), not
national borders and **not** straight-line (Haversine) distance.

## Rules

1. Home and job places are geocoded with **Google Geocoding** (via the
   minimal authenticated maps proxy — API key never ships unrestricted
   inside Karrierekrake.exe).
2. Distance + duration come from **Compute Route Matrix Essentials**
   (`TRAVEL_MODE=DRIVE`, `TRAFFIC_UNAWARE`).
3. If Google fails → `DISTANCE_UNKNOWN` (`None`). **No** Haversine /
   Nominatim / pgeocode / OSRM fallback.
4. UI may show „km Fahrt“ / duration **only** when
   `distance_source == google_route_matrix`.
5. Cross-border DE/AT/CH: borders are not barriers; the road route may
   cross them. Toggle `cross_border_dach` only affects geocode region bias.

## Classic acceptance case

Airline (Haversine) < configured radius, but road route > radius  
→ job is **OUTSIDE** radius.

## Cost / security

See `docs/project/next-05-google-maps-geo.md`.

## Legacy note

Older docs and `core/geo_resolve.haversine_km` remain for **diagnostics /
unit tests only**. They must never write `Job.distance_km`.
