"""Offline-first DACH place → coordinate resolution.

Prefer pgeocode (GeoNames-backed, local) for DE/AT/CH postal codes.
Nominatim is optional, rate-limited, and cached — never invent distances.
Border is not a distance barrier: Haversine is country-independent.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable

from core.geo_normalize import (
    DACH_COUNTRY_CODES,
    NormalizedPlace,
    ResolutionStatus,
    normalize_country_code,
    normalize_place_fields,
    plz_candidate_countries,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger("karrierekrake")

# Versioned data sources for geocode_cache (migration / invalidation).
GEO_DATA_SOURCE_COORDS = "explicit_coords"
GEO_DATA_VERSION_COORDS = "wgs84-1"
GEO_DATA_SOURCE_PGEOCODE = "pgeocode"
GEO_DATA_VERSION_PGEOCODE = "geonames-pgeocode-0.5"
GEO_DATA_SOURCE_NOMINATIM = "nominatim"
GEO_DATA_VERSION_NOMINATIM = "osm-nominatim-1"
GEO_DATA_SOURCE_UNRESOLVED = "unresolved"
GEO_DATA_VERSION_UNRESOLVED = "1"

UNRESOLVED_MARKER = "__unresolved__"
UNKNOWN_DISTANCE = None  # sentinel documentation: never invent a float

# Public / textbook reference points for tests & docs (not user PII).
# Approximate WGS84 — suitable for Haversine golden cases.
PUBLIC_REF_COORDS: dict[str, tuple[float, float, str]] = {
    "konstanz_de": (47.6603, 9.1753, "DE"),
    "kreuzlingen_ch": (47.6499, 9.1750, "CH"),
    "singen_de": (47.7590, 8.8401, "DE"),
    "bregenz_at": (47.5031, 9.7471, "AT"),
    "innsbruck_at": (47.2692, 11.4041, "AT"),
    "basel_ch": (47.5596, 7.5886, "CH"),
    "weil_am_rhein_de": (47.5948, 7.6102, "DE"),
    "salzburg_at": (47.8095, 13.0550, "AT"),
    "freilassing_de": (47.8408, 12.9811, "DE"),
    "passau_de": (48.5665, 13.4312, "DE"),
    "schaerding_at": (48.4522, 13.4372, "AT"),
}


@dataclass(frozen=True)
class PlaceResolution:
    """Outcome of resolving a place. status UNKNOWN/AMBIGUOUS ⇒ no distance."""

    status: ResolutionStatus
    latitude: float | None = None
    longitude: float | None = None
    country_code: str = ""
    display_name: str = ""
    data_source: str = ""
    data_version: str = ""
    reason: str = ""

    @property
    def ok(self) -> bool:
        return (
            self.status == "RESOLVED"
            and self.latitude is not None
            and self.longitude is not None
        )


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two WGS84 points in kilometres.

    Country borders are irrelevant — only coordinates matter.
    """
    r = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )
    return 2 * r * math.asin(math.sqrt(a))


def distance_km_or_unknown(
    home: tuple[float, float] | None,
    place: PlaceResolution,
) -> float | None:
    """Return rounded km or None (UNKNOWN). Never invents a number."""
    if home is None or not place.ok:
        return UNKNOWN_DISTANCE
    assert place.latitude is not None and place.longitude is not None
    return round(haversine_km(home[0], home[1], place.latitude, place.longitude), 2)


def within_radius(
    distance_km: float | None,
    radius_km: float | None,
    *,
    remote: bool = False,
) -> bool | None:
    """True/False if known; None if distance UNKNOWN (do not guess).

    Remote jobs are treated as within radius for commute math (no workplace).
    """
    if remote:
        return True
    if radius_km is None:
        return True
    if distance_km is None:
        return None
    return float(distance_km) <= float(radius_km)


def cache_query_key(place: NormalizedPlace) -> str:
    """Stable, country-aware cache key (v2)."""
    if place.has_coords:
        return f"ll:{place.latitude:.5f},{place.longitude:.5f}"
    cc = (place.country_code or "").upper()
    parts = [p for p in (cc, place.postal_code, place.city, place.address) if p]
    if not parts:
        return ""
    return "|".join(p.strip().lower() for p in parts)


_pgeocode_index: dict[str, Any] = {}


def _pgeocode_nominatim(country_code: str) -> Any | None:
    cc = normalize_country_code(country_code)
    if cc not in DACH_COUNTRY_CODES:
        return None
    if cc in _pgeocode_index:
        return _pgeocode_index[cc]
    try:
        import pgeocode
    except ImportError:
        logger.debug("pgeocode not installed — offline PLZ resolution unavailable")
        return None
    try:
        nom = pgeocode.Nominatim(cc.lower())
        _pgeocode_index[cc] = nom
        return nom
    except Exception as exc:
        logger.warning("pgeocode init failed for %s: %s", cc, exc)
        return None


def _finite(value: Any) -> float | None:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if f != f or math.isinf(f):  # NaN / inf
        return None
    return f


def resolve_postal_pgeocode(
    postal_code: str,
    country_code: str,
) -> PlaceResolution:
    """Resolve a single-country PLZ via pgeocode. Offline-friendly."""
    cc = normalize_country_code(country_code)
    digits = "".join(c for c in str(postal_code or "") if c.isdigit())
    if not cc or not digits:
        return PlaceResolution(
            status="UNKNOWN",
            reason="missing_plz_or_country",
            data_source=GEO_DATA_SOURCE_UNRESOLVED,
            data_version=GEO_DATA_VERSION_UNRESOLVED,
        )
    nom = _pgeocode_nominatim(cc)
    if nom is None:
        return PlaceResolution(
            status="UNKNOWN",
            reason="pgeocode_unavailable",
            country_code=cc,
            data_source=GEO_DATA_SOURCE_UNRESOLVED,
            data_version=GEO_DATA_VERSION_UNRESOLVED,
        )
    try:
        row = nom.query_postal_code(digits)
    except Exception as exc:
        logger.debug("pgeocode query failed %s %s: %s", cc, digits, exc)
        return PlaceResolution(
            status="UNKNOWN",
            reason="pgeocode_error",
            country_code=cc,
            data_source=GEO_DATA_SOURCE_UNRESOLVED,
            data_version=GEO_DATA_VERSION_UNRESOLVED,
        )
    lat = _finite(getattr(row, "latitude", None))
    lon = _finite(getattr(row, "longitude", None))
    if lat is None or lon is None:
        return PlaceResolution(
            status="UNKNOWN",
            reason="plz_not_found",
            country_code=cc,
            data_source=GEO_DATA_SOURCE_UNRESOLVED,
            data_version=GEO_DATA_VERSION_UNRESOLVED,
        )
    place_name = str(getattr(row, "place_name", "") or "")
    if "," in place_name:
        place_name = place_name.split(",")[0].strip()
    display = ", ".join(p for p in (digits, place_name, cc) if p)
    return PlaceResolution(
        status="RESOLVED",
        latitude=lat,
        longitude=lon,
        country_code=cc,
        display_name=display,
        data_source=GEO_DATA_SOURCE_PGEOCODE,
        data_version=GEO_DATA_VERSION_PGEOCODE,
    )


def resolve_place_offline(place: NormalizedPlace) -> PlaceResolution:
    """Resolve using explicit coords or pgeocode only (no network)."""
    if place.is_remote:
        return PlaceResolution(
            status="UNKNOWN",
            reason="remote_no_workplace",
            data_source=GEO_DATA_SOURCE_UNRESOLVED,
            data_version=GEO_DATA_VERSION_UNRESOLVED,
        )
    if place.has_coords:
        return PlaceResolution(
            status="RESOLVED",
            latitude=place.latitude,
            longitude=place.longitude,
            country_code=place.country_code,
            display_name=place.address or place.city or "coords",
            data_source=GEO_DATA_SOURCE_COORDS,
            data_version=GEO_DATA_VERSION_COORDS,
        )
    if not place.postal_code:
        return PlaceResolution(
            status="UNKNOWN",
            reason="no_plz_offline",
            country_code=place.country_code,
            data_source=GEO_DATA_SOURCE_UNRESOLVED,
            data_version=GEO_DATA_VERSION_UNRESOLVED,
        )

    cc = place.country_code
    if cc:
        return resolve_postal_pgeocode(place.postal_code, cc)

    candidates = plz_candidate_countries(place.postal_code)
    hits: list[PlaceResolution] = []
    for cand in candidates:
        res = resolve_postal_pgeocode(place.postal_code, cand)
        if res.ok:
            # Optional city disambiguation when PLZ exists in AT and CH
            if place.city:
                dn = (res.display_name or "").casefold()
                if place.city.casefold() in dn or dn.startswith(place.postal_code):
                    # weak city match — keep as candidate
                    hits.append(res)
                else:
                    hits.append(res)
            else:
                hits.append(res)
    if not hits:
        return PlaceResolution(
            status="UNKNOWN",
            reason="plz_unresolved_offline",
            data_source=GEO_DATA_SOURCE_UNRESOLVED,
            data_version=GEO_DATA_VERSION_UNRESOLVED,
        )
    if len(hits) == 1:
        return hits[0]
    # Same PLZ in multiple countries without reliable city match → AMBIGUOUS
    if place.city:
        city_hits = [
            h
            for h in hits
            if place.city.casefold() in (h.display_name or "").casefold()
        ]
        if len(city_hits) == 1:
            return city_hits[0]
    return PlaceResolution(
        status="AMBIGUOUS",
        reason="plz_multi_country",
        display_name=place.postal_code,
        data_source=GEO_DATA_SOURCE_UNRESOLVED,
        data_version=GEO_DATA_VERSION_UNRESOLVED,
    )


def resolve_place(
    place: NormalizedPlace,
    *,
    cross_border: bool = True,
    home_country: str = "DE",
    allow_network: bool = True,
    network_geocode: Callable[[str, list[str]], PlaceResolution | None] | None = None,
) -> PlaceResolution:
    """Resolve place to coordinates. Prefer offline; network is optional.

    When ``cross_border`` is False, restrict PLZ/network to ``home_country``.
    """
    if place.is_remote:
        return PlaceResolution(
            status="UNKNOWN",
            reason="remote_no_workplace",
            data_source=GEO_DATA_SOURCE_UNRESOLVED,
            data_version=GEO_DATA_VERSION_UNRESOLVED,
        )

    working = place
    if not cross_border:
        hc = normalize_country_code(home_country) or "DE"
        # Force single-country scope when toggle off
        if working.country_code and working.country_code != hc:
            # Still allow explicit coords (math); skip foreign PLZ lookup
            if not working.has_coords:
                return PlaceResolution(
                    status="UNKNOWN",
                    reason="cross_border_disabled",
                    country_code=working.country_code,
                    data_source=GEO_DATA_SOURCE_UNRESOLVED,
                    data_version=GEO_DATA_VERSION_UNRESOLVED,
                )
        elif not working.country_code:
            working = NormalizedPlace(
                city=working.city,
                postal_code=working.postal_code,
                address=working.address,
                country_code=hc,
                latitude=working.latitude,
                longitude=working.longitude,
                remote_type=working.remote_type,
            )

    offline = resolve_place_offline(working)
    if offline.status in {"RESOLVED", "AMBIGUOUS"}:
        return offline
    if offline.status == "UNKNOWN" and offline.reason == "remote_no_workplace":
        return offline

    if not allow_network or network_geocode is None:
        return offline

    # Build query + country filter for Nominatim
    countries: list[str]
    if cross_border:
        countries = sorted(DACH_COUNTRY_CODES)
    else:
        countries = [normalize_country_code(home_country) or "DE"]
    if working.country_code:
        countries = [working.country_code]

    query_parts = [p for p in (working.address, working.postal_code, working.city) if p]
    if working.country_code:
        query_parts.append(working.country_code)
    query = ", ".join(query_parts)
    if not query:
        return PlaceResolution(
            status="UNKNOWN",
            reason="empty_query",
            data_source=GEO_DATA_SOURCE_UNRESOLVED,
            data_version=GEO_DATA_VERSION_UNRESOLVED,
        )
    try:
        net = network_geocode(query, countries)
    except Exception as exc:
        logger.warning("network geocode failed for %r: %s", query, exc)
        return PlaceResolution(
            status="UNKNOWN",
            reason="geocoder_failure",
            data_source=GEO_DATA_SOURCE_UNRESOLVED,
            data_version=GEO_DATA_VERSION_UNRESOLVED,
        )
    if net is None:
        return PlaceResolution(
            status="UNKNOWN",
            reason="geocoder_miss",
            data_source=GEO_DATA_SOURCE_UNRESOLVED,
            data_version=GEO_DATA_VERSION_UNRESOLVED,
        )
    return net


def place_from_job_like(obj: Any) -> NormalizedPlace:
    """Build NormalizedPlace from Job / duck-typed job object."""
    return normalize_place_fields(
        city=getattr(obj, "city", "") or "",
        postal_code=getattr(obj, "postal_code", "") or "",
        address=getattr(obj, "address", "") or "",
        country=getattr(obj, "country", "") or "",
        country_code=getattr(obj, "country_code", "") or "",
        latitude=getattr(obj, "latitude", None),
        longitude=getattr(obj, "longitude", None),
        remote_type=getattr(obj, "remote_type", "") or "",
        description=getattr(obj, "description", "") or "",
    )
