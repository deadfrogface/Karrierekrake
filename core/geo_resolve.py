"""Local DACH place resolution + Haversine airline distance (authoritative).

Production path (local-first):
  1. Trusted explicit coordinates with provenance
  2. country_code + postal_code via bundled/pgeocode GeoNames data
  3. Unique country_code + city → city centroid
  4. Otherwise UNKNOWN / AMBIGUOUS — never guess

No Google Maps / Places / Routes / Distance Matrix.
No public Nominatim production calls.
Distance = great-circle (Luftlinie) with documented R = 6371.0088 km (haversine_v1).
"""

from __future__ import annotations

import logging
import math
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, Literal

from core.geo_dataset import (
    EARTH_RADIUS_KM,
    HAVERSINE_ALGORITHM,
    get_geo_dataset_manager,
)
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

GEO_DATA_SOURCE_COORDS = "existing_source"
GEO_DATA_VERSION_COORDS = "wgs84-1"
GEO_DATA_SOURCE_PGEOCODE = "pgeocode"
GEO_DATA_SOURCE_GEONAMES = "geonames"
GEO_DATA_VERSION_PGEOCODE = "geonames-pgeocode-0.5"
GEO_DATA_SOURCE_UNRESOLVED = "unresolved"
GEO_DATA_VERSION_UNRESOLVED = "1"

UNRESOLVED_MARKER = "__unresolved__"
UNKNOWN_DISTANCE = None
DISTANCE_UNKNOWN = None  # alias for callers migrating from maps contracts

Precision = Literal[
    "exact_coordinates",
    "postal_centroid",
    "city_centroid",
    "unknown",
]

# Public reference points for golden Haversine tests (not user PII).
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
    "berlin_de": (52.5200, 13.4050, "DE"),
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
    precision: Precision = "unknown"

    @property
    def ok(self) -> bool:
        return (
            self.status == "RESOLVED"
            and self.latitude is not None
            and self.longitude is not None
        )


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km (haversine_v1). Unrounded — UI rounds only.

    Earth radius R = 6371.0088 km (IUGG mean). Angles converted to radians.
    Raises ValueError for non-finite or out-of-range coordinates.
    """
    for name, v in (("lat1", lat1), ("lon1", lon1), ("lat2", lat2), ("lon2", lon2)):
        if v is None or not isinstance(v, (int, float)) or not math.isfinite(float(v)):
            raise ValueError(f"invalid coordinate {name}")
    lat1, lon1, lat2, lon2 = float(lat1), float(lon1), float(lat2), float(lon2)
    if not (-90.0 <= lat1 <= 90.0 and -90.0 <= lat2 <= 90.0):
        raise ValueError("latitude out of range")
    if not (-180.0 <= lon1 <= 180.0 and -180.0 <= lon2 <= 180.0):
        raise ValueError("longitude out of range")
    r = EARTH_RADIUS_KM
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )
    return 2 * r * math.asin(math.sqrt(min(1.0, a)))


def format_airline_km(distance_km: float | None, *, decimals: int = 0) -> str:
    """User-facing label — always Luftlinie, never Fahrt."""
    if distance_km is None or not math.isfinite(float(distance_km)):
        return ""
    if decimals <= 0:
        return f"ca. {int(round(float(distance_km)))} km Luftlinie"
    return f"ca. {float(distance_km):.{decimals}f} km Luftlinie"


def distance_km_or_unknown(
    home: tuple[float, float] | None,
    place: PlaceResolution,
) -> float | None:
    """Airline km for filter math (unrounded). UNKNOWN if home/place missing."""
    if home is None or not place.ok:
        return UNKNOWN_DISTANCE
    assert place.latitude is not None and place.longitude is not None
    try:
        return haversine_km(home[0], home[1], place.latitude, place.longitude)
    except ValueError:
        return UNKNOWN_DISTANCE


def within_radius(
    distance_km: float | None,
    radius_km: float | None,
    *,
    remote: bool = False,
) -> bool | None:
    """True/False if known; None if distance UNKNOWN (do not guess as 0 km).

    Fully remote jobs skip radius math when remote=True.
    """
    if remote:
        return True
    if radius_km is None:
        return True
    if distance_km is None:
        return None
    return float(distance_km) <= float(radius_km)


def cache_query_key(place: NormalizedPlace) -> str:
    """Stable, country-aware cache key (canonical_location_key)."""
    if place.has_coords:
        return f"ll:{place.latitude:.5f},{place.longitude:.5f}"
    cc = (place.country_code or "").upper()
    parts = [p for p in (cc, place.postal_code, place.city, place.address) if p]
    if not parts:
        return ""
    return "|".join(p.strip().lower() for p in parts)


_pgeocode_index: dict[str, Any] = {}


def _ensure_geo_data() -> str:
    """Ensure local dataset and return its version string."""
    mgr = get_geo_dataset_manager()
    info = mgr.ensure_active()
    return info.version if info.valid else GEO_DATA_VERSION_PGEOCODE


def _pgeocode_nominatim(country_code: str) -> Any | None:
    """Offline GeoNames index — never calls the public Nominatim HTTP API."""
    cc = normalize_country_code(country_code)
    if cc not in DACH_COUNTRY_CODES:
        return None
    if cc in _pgeocode_index:
        return _pgeocode_index[cc]
    _ensure_geo_data()
    try:
        import pgeocode
    except ImportError:
        logger.debug("pgeocode not installed — offline PLZ resolution unavailable")
        return None
    # Block accidental online geopy/Nominatim defaults if imported elsewhere.
    os.environ.setdefault("PGEOCODE_DATA_DIR", os.environ.get("PGEOCODE_DATA_DIR", ""))
    try:
        nom = pgeocode.Nominatim(cc.lower())
        _pgeocode_index[cc] = nom
        return nom
    except Exception as exc:
        logger.warning("pgeocode init failed for %s: %s", cc, type(exc).__name__)
        return None


def reset_pgeocode_index_for_tests() -> None:
    _pgeocode_index.clear()


def _finite(value: Any) -> float | None:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(f):
        return None
    return f


def resolve_postal_pgeocode(
    postal_code: str,
    country_code: str,
) -> PlaceResolution:
    """Resolve a single-country PLZ via local GeoNames/pgeocode data."""
    cc = normalize_country_code(country_code)
    digits = "".join(c for c in str(postal_code or "") if c.isdigit())
    # Preserve leading zeros for DE (normalize may keep digits only).
    if cc == "DE" and digits and len(digits) < 5:
        digits = digits.zfill(5)
    if not cc or not digits:
        return PlaceResolution(
            status="UNKNOWN",
            reason="missing_plz_or_country",
            data_source=GEO_DATA_SOURCE_UNRESOLVED,
            data_version=GEO_DATA_VERSION_UNRESOLVED,
        )
    version = _ensure_geo_data()
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
        logger.debug("pgeocode query failed %s %s: %s", cc, digits, type(exc).__name__)
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
        data_source=GEO_DATA_SOURCE_GEONAMES,
        data_version=version,
        precision="postal_centroid",
    )


# A single city's postal centroids stay within this radius of their mean
# (Berlin ≈ 25 km, Hamburg/München less); homonyms in other regions exceed it.
CITY_SPREAD_MAX_KM = 35.0


def _exact_city_rows(nom: Any, needle: str) -> Any | None:
    """Exact place-name rows from the full local table.

    ``query_location`` only returns the top fuzzy hits, which for large cities
    are dominated by bulk-recipient PLZ ("Agentur für Arbeit Berlin Mitte") and
    can miss the plain city name entirely.
    """
    data = getattr(nom, "_data", None)
    columns = getattr(data, "columns", ())
    if data is None or "place_name" not in columns:
        return None
    try:
        folded = getattr(nom, "_kk_place_casefold", None)
        if folded is None or len(folded) != len(data):
            folded = data["place_name"].astype(str).str.casefold()
            nom._kk_place_casefold = folded
        return data[folded == needle]
    except Exception as exc:
        logger.debug("exact city lookup failed: %s", type(exc).__name__)
        return None


def resolve_city_pgeocode(city: str, country_code: str) -> PlaceResolution:
    """Resolve unique city within one country. Ambiguous → AMBIGUOUS, never guess."""
    cc = normalize_country_code(country_code)
    name = (city or "").strip()
    if not cc or not name:
        return PlaceResolution(
            status="UNKNOWN",
            reason="missing_city_or_country",
            data_source=GEO_DATA_SOURCE_UNRESOLVED,
            data_version=GEO_DATA_VERSION_UNRESOLVED,
        )
    version = _ensure_geo_data()
    nom = _pgeocode_nominatim(cc)
    if nom is None:
        return PlaceResolution(
            status="UNKNOWN",
            reason="pgeocode_unavailable",
            country_code=cc,
            data_source=GEO_DATA_SOURCE_UNRESOLVED,
            data_version=GEO_DATA_VERSION_UNRESOLVED,
        )
    needle = name.casefold()
    exact = _exact_city_rows(nom, needle)
    if exact is None or exact.empty:
        try:
            frame = nom.query_location(name)
        except Exception as exc:
            logger.debug("city query failed %s %s: %s", cc, name, type(exc).__name__)
            return PlaceResolution(
                status="UNKNOWN",
                reason="city_query_error",
                country_code=cc,
                data_source=GEO_DATA_SOURCE_UNRESOLVED,
                data_version=GEO_DATA_VERSION_UNRESOLVED,
            )
        if frame is None or getattr(frame, "empty", True):
            return PlaceResolution(
                status="UNKNOWN",
                reason="city_not_found",
                country_code=cc,
                data_source=GEO_DATA_SOURCE_UNRESOLVED,
                data_version=GEO_DATA_VERSION_UNRESOLVED,
            )
        try:
            import pandas as pd

            df = frame if isinstance(frame, pd.DataFrame) else pd.DataFrame(frame)
        except Exception:
            return PlaceResolution(
                status="UNKNOWN",
                reason="city_frame_error",
                country_code=cc,
                data_source=GEO_DATA_SOURCE_UNRESOLVED,
                data_version=GEO_DATA_VERSION_UNRESOLVED,
            )
        if "place_name" in df.columns:
            exact = df[df["place_name"].astype(str).str.casefold() == needle]
            if exact.empty:
                exact = df[
                    df["place_name"].astype(str).str.casefold().str.contains(needle, na=False)
                ]
        else:
            exact = df
    if exact.empty:
        return PlaceResolution(
            status="UNKNOWN",
            reason="city_not_found",
            country_code=cc,
            data_source=GEO_DATA_SOURCE_UNRESOLVED,
            data_version=GEO_DATA_VERSION_UNRESOLVED,
        )
    names = {
        str(n).casefold()
        for n in exact["place_name"].tolist()
        if str(n).strip()
    }
    if len(names) != 1:
        return PlaceResolution(
            status="AMBIGUOUS",
            reason="city_multi_place",
            country_code=cc,
            display_name=name,
            data_source=GEO_DATA_SOURCE_UNRESOLVED,
            data_version=GEO_DATA_VERSION_UNRESOLVED,
        )
    lats = [_finite(v) for v in exact["latitude"].tolist()]
    lons = [_finite(v) for v in exact["longitude"].tolist()]
    pairs = [(a, b) for a, b in zip(lats, lons) if a is not None and b is not None]
    if not pairs:
        return PlaceResolution(
            status="UNKNOWN",
            reason="city_no_coords",
            country_code=cc,
            data_source=GEO_DATA_SOURCE_UNRESOLVED,
            data_version=GEO_DATA_VERSION_UNRESOLVED,
        )
    # Spread check: same name in distant places → AMBIGUOUS
    lat_vals = [p[0] for p in pairs]
    lon_vals = [p[1] for p in pairs]
    lat = sum(lat_vals) / len(lat_vals)
    lon = sum(lon_vals) / len(lon_vals)
    if max(haversine_km(lat, lon, a, b) for a, b in pairs) > CITY_SPREAD_MAX_KM:
        return PlaceResolution(
            status="AMBIGUOUS",
            reason="city_spread",
            country_code=cc,
            display_name=name,
            data_source=GEO_DATA_SOURCE_UNRESOLVED,
            data_version=GEO_DATA_VERSION_UNRESOLVED,
        )
    display = f"{name}, {cc}"
    return PlaceResolution(
        status="RESOLVED",
        latitude=lat,
        longitude=lon,
        country_code=cc,
        display_name=display,
        data_source=GEO_DATA_SOURCE_GEONAMES,
        data_version=version,
        precision="city_centroid",
    )


def resolve_place_offline(place: NormalizedPlace) -> PlaceResolution:
    """Resolve using explicit coords, PLZ, or unique city — local data only."""
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
            precision="exact_coordinates",
        )

    if place.postal_code:
        cc = place.country_code
        if cc:
            return resolve_postal_pgeocode(place.postal_code, cc)
        candidates = plz_candidate_countries(place.postal_code)
        hits: list[PlaceResolution] = []
        for cand in candidates:
            res = resolve_postal_pgeocode(place.postal_code, cand)
            if res.ok:
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

    if place.city and place.country_code:
        return resolve_city_pgeocode(place.city, place.country_code)

    if place.city and not place.country_code:
        # Never guess country for same city name across DE/AT/CH
        return PlaceResolution(
            status="AMBIGUOUS" if place.city else "UNKNOWN",
            reason="city_without_country",
            display_name=place.city,
            data_source=GEO_DATA_SOURCE_UNRESOLVED,
            data_version=GEO_DATA_VERSION_UNRESOLVED,
        )

    return PlaceResolution(
        status="UNKNOWN",
        reason="no_plz_or_city",
        country_code=place.country_code,
        data_source=GEO_DATA_SOURCE_UNRESOLVED,
        data_version=GEO_DATA_VERSION_UNRESOLVED,
    )


def resolve_place(
    place: NormalizedPlace,
    *,
    cross_border: bool = True,
    home_country: str = "DE",
    allow_network: bool = False,
    network_geocode: Callable[[str, list[str]], PlaceResolution | None] | None = None,
) -> PlaceResolution:
    """Resolve place locally. Network geocode is disabled by default (no Nominatim)."""
    del network_geocode  # production must not call public Nominatim
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
        if working.country_code and working.country_code != hc:
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
    if allow_network:
        logger.debug(
            "network geocode requested but disabled (local-first policy) for %s",
            cache_query_key(working),
        )
    return offline


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


# Re-export algorithm id for UI / docs / cache provenance
__all__ = [
    "HAVERSINE_ALGORITHM",
    "EARTH_RADIUS_KM",
    "PlaceResolution",
    "haversine_km",
    "format_airline_km",
    "distance_km_or_unknown",
    "within_radius",
    "cache_query_key",
    "resolve_postal_pgeocode",
    "resolve_city_pgeocode",
    "resolve_place_offline",
    "resolve_place",
    "place_from_job_like",
    "DISTANCE_UNKNOWN",
    "UNKNOWN_DISTANCE",
    "UNRESOLVED_MARKER",
]
