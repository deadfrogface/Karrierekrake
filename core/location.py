"""Local geocoding cache, Haversine airline prefilter, and BRouter Fahrstrecke.

Production authority: bundled/updated GeoNames DE/AT/CH/NL/BE postal data.
Airline (haversine_v1) is a fast radius prefilter only.
Authoritative commute distance for remaining jobs is local BRouter road-km.

On resolution or routing failure → DISTANCE_UNKNOWN (None). Never invent km.
Never present airline kilometres as Fahrstrecke.
max_commute_km means: airline prefilter, then Fahrstrecke ≤ N km.

Home coordinates are resolved once per LocationService instance / run.
Failed home resolution must NOT silently use arbitrary Germany center coordinates.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable

from core.geo_dataset import get_geo_dataset_manager
from core.geo_normalize import (
    normalize_country_code,
    normalize_place_fields,
)
from core.geo_resolve import (
    DISTANCE_UNKNOWN,
    GEO_DATA_SOURCE_GEONAMES,
    GEO_DATA_SOURCE_UNRESOLVED,
    GEO_DATA_VERSION_UNRESOLVED,
    HAVERSINE_ALGORITHM,
    PlaceResolution,
    UNRESOLVED_MARKER,
    cache_query_key,
    haversine_km,
    lookup_cached_resolution,
    place_from_job_like,
    resolve_place,
    store_cached_resolution,
)

if TYPE_CHECKING:
    from core.config import AppConfig
    from core.database import Database

logger = logging.getLogger("karrierekrake")

__all__ = [
    "UNRESOLVED_MARKER",
    "DISTANCE_UNKNOWN",
    "HAVERSINE_ALGORITHM",
    "HomeResolution",
    "EnrichStats",
    "LocationService",
    "haversine_km",
    "location_cache_key",
    "enrich_job_locations",
    "cross_border_dach_enabled",
    "HOME_PLZ_HINT",
    "HomeNotice",
    "home_location_notice",
    "apply_visible_home",
]

DEFAULT_GEOCODE_TIMEOUT_S = 12.0
UNRESOLVED_TTL_S = 6 * 60 * 60

# Trusted cache sources for local geo (stale google_* rows are ignored).
TRUSTED_GEO_SOURCES = frozenset(
    {
        "geonames",
        "pgeocode",
        "existing_source",
        "explicit_coords",
        "local_geo",
    }
)
STALE_GEO_SOURCES = frozenset(
    {
        "google_geocoding",
        "google_route_matrix",
        "nominatim",
        "maps",
        "stale_cleared",
        "",
    }
)

GEO_DATA_SOURCE_LOCAL = "local_geo"

# Shown when the home place is AMBIGUOUS or UNKNOWN. Never a guessed centroid.
HOME_PLZ_HINT = (
    "Standort nicht prüfbar. Bitte Postleitzahl angeben — "
    "ohne PLZ wird kein Ort geschätzt und der Umkreisfilter übersprungen."
)


def cross_border_dach_enabled(config: "AppConfig") -> bool:
    """Feature toggle: DACH commute across DE/AT/CH (default on)."""
    settings = getattr(config, "settings", None)
    if settings is not None and hasattr(settings, "cross_border_dach_enabled"):
        return bool(settings.cross_border_dach_enabled)
    loc = getattr(getattr(config, "profile", None), "location", None)
    if loc is not None and hasattr(loc, "cross_border_dach"):
        return bool(loc.cross_border_dach)
    return True


@dataclass(frozen=True)
class HomeNotice:
    """Fresh home-resolution status for settings, overview, and job labels.

    ``resolved`` is an explicit OK. ``ambiguous`` / ``unknown`` ask for a
    postal code and do not invent coordinates.
    """

    status: str
    ask_postal: bool
    notice_key: str
    place_label: str = ""
    country_code: str = ""
    latitude: float | None = None
    longitude: float | None = None
    offer_change_place: bool = False


# One finished resolution per normalized home plus the resolve_place arguments.
# Not written to profile.yaml. Values are ``(generation, PlaceResolution)``.
# The key does not include the generation.
_HOME_RESOLUTION_CACHE: dict[str, tuple[int, PlaceResolution]] = {}
# Address fingerprint → (cross_border, home_country) that the stored coordinates
# belong to. A toggle must not reuse them.
_PERSISTED_HOME_PARAMS: dict[str, tuple[bool, str]] = {}


def home_resolution_key(
    *,
    address: str = "",
    postal_code: str = "",
    city: str = "",
    country: str = "",
    cross_border: bool = True,
    home_country: str = "",
    allow_network: bool = False,
) -> str:
    """Cache key: normalized home plus every argument ``resolve_place`` receives.

    The geo-index generation is stored with the value, not in the key.
    """
    country_code = normalize_country_code(country) or "DE"
    home_cc = normalize_country_code(home_country) or country_code
    return "|".join(
        (
            _address_fingerprint(address),
            (postal_code or "").strip(),
            _address_fingerprint(city),
            country_code.upper(),
            "1" if cross_border else "0",
            home_cc.upper(),
            "1" if allow_network else "0",
        )
    )


def reset_home_resolution_cache_for_tests() -> None:
    _HOME_RESOLUTION_CACHE.clear()
    _PERSISTED_HOME_PARAMS.clear()


def _home_text(location: Any) -> tuple[str, str, str, str]:
    address = (getattr(location, "home_address", "") or "").strip()
    postal = (getattr(location, "postal_code", "") or "").strip()
    city = (getattr(location, "city", "") or "").strip()
    country = (getattr(location, "country", "") or "").strip() or "DE"
    return address, postal, city, country


def _home_fingerprint(location: Any) -> str:
    address, postal, city, _country = _home_text(location)
    return _address_fingerprint(address or (f"{postal}|{city}" if (postal or city) else ""))


def home_resolve_params(
    location: Any,
    config: Any | None = None,
    *,
    cross_border: bool | None = None,
    home_country: str | None = None,
) -> tuple[bool, str]:
    """The ``cross_border`` / ``home_country`` pair ``resolve_home`` passes through."""
    if cross_border is None and config is not None:
        cross_border = cross_border_dach_enabled(config)
    if cross_border is None:
        cross_border = bool(getattr(location, "cross_border_dach", True))
    if home_country is None:
        _address, _postal, _city, country = _home_text(location)
        home_country = country
    return bool(cross_border), normalize_country_code(home_country) or "DE"


def _remember_persisted_params(
    location: Any, *, cross_border: bool, home_country: str
) -> None:
    fingerprint = _home_fingerprint(location)
    if fingerprint:
        _PERSISTED_HOME_PARAMS[fingerprint] = (bool(cross_border), home_country.upper())


def _persisted_covers(
    location: Any, *, cross_border: bool, home_country: str
) -> bool:
    """True when stored coordinates were produced for these resolve parameters."""
    if not _coords_match_address(location):
        return False
    fingerprint = _home_fingerprint(location)
    known = _PERSISTED_HOME_PARAMS.get(fingerprint)
    current = (bool(cross_border), (home_country or "DE").upper())
    if known is None:
        _PERSISTED_HOME_PARAMS[fingerprint] = current
        return True
    return known == current


def _persisted_resolution(
    location: Any, *, home_country: str
) -> PlaceResolution:
    address, postal, city, _country = _home_text(location)
    # Same label the hint used before the shared lookup: city, not the raw address.
    label = city or _city_from_address(address) or address or ", ".join(
        p for p in (postal, home_country) if p
    )
    return PlaceResolution(
        status="RESOLVED",
        latitude=float(location.home_latitude),
        longitude=float(location.home_longitude),
        country_code=home_country,
        display_name=label,
        data_source="existing_source",
        reason="persisted_coords",
        precision="exact_coordinates",
    )


def cached_home_resolution(
    location: Any,
    *,
    cross_border: bool,
    home_country: str,
) -> PlaceResolution | None:
    """One lookup for the hint and for ``LocationService.resolve_home``.

    Does not mutate ``location``. ``cross_border``, ``home_country`` and
    ``allow_network=False`` are the same arguments ``resolve_place`` receives.
    """
    address, postal, city, country = _home_text(location)
    if not postal and not city and not address:
        return None
    home_cc = normalize_country_code(home_country) or normalize_country_code(country) or "DE"
    key = home_resolution_key(
        address=address,
        postal_code=postal,
        city=city,
        country=country,
        cross_border=cross_border,
        home_country=home_cc,
        allow_network=False,
    )
    # Stored coordinates for this parameter set beat a cached miss. A later
    # save can attach coordinates to an address that was unknown a moment ago.
    if _persisted_covers(location, cross_border=cross_border, home_country=home_cc):
        cached = lookup_cached_resolution(_HOME_RESOLUTION_CACHE, key)
        if cached is not None and cached.ok:
            return cached
        resolution = _persisted_resolution(location, home_country=home_cc)
        store_cached_resolution(_HOME_RESOLUTION_CACHE, key, resolution)
        return resolution
    cached = lookup_cached_resolution(_HOME_RESOLUTION_CACHE, key)
    if cached is not None:
        return cached
    place = normalize_place_fields(
        address=address,
        city=city or _city_from_address(address),
        postal_code=postal or _plz_from_address(address),
        country_code=normalize_country_code(country) or "DE",
    )
    resolution = resolve_place(
        place,
        cross_border=cross_border,
        home_country=home_cc,
        allow_network=False,
    )
    # A still-loading index is not a resolution. The next read tries again.
    # Same key: a stale miss is replaced in place.
    store_cached_resolution(_HOME_RESOLUTION_CACHE, key, resolution)
    if resolution.ok:
        _remember_persisted_params(
            location, cross_border=cross_border, home_country=home_cc
        )
    return resolution


def _notice_from_resolution(location: Any, resolution: PlaceResolution | None) -> HomeNotice:
    address, _postal, city, country = _home_text(location)
    label = city or _city_from_address(address) or address or _postal
    country_code = normalize_country_code(country) or "DE"
    if resolution is not None and resolution.ok:
        return HomeNotice(
            status="resolved",
            ask_postal=False,
            notice_key="dash.home_resolved",
            place_label=resolution.display_name or label,
            country_code=country_code,
            latitude=float(resolution.latitude) if resolution.latitude is not None else None,
            longitude=float(resolution.longitude) if resolution.longitude is not None else None,
        )
    if resolution is not None and resolution.reason == "geo_index_loading":
        return HomeNotice(
            status="loading",
            ask_postal=False,
            notice_key="dash.home_checking",
            place_label=label,
            country_code=country_code,
        )
    if resolution is not None and resolution.reason == "geo_index_unavailable":
        return HomeNotice(
            status="unavailable",
            ask_postal=False,
            notice_key="dash.home_index_unavailable",
            place_label=label,
            country_code=country_code,
        )
    if resolution is not None and (
        resolution.status == "AMBIGUOUS" or resolution.reason == "plz_not_found"
    ):
        return HomeNotice(
            status="ambiguous" if resolution.status == "AMBIGUOUS" else "unknown",
            ask_postal=True,
            notice_key="dash.home_plz_hint",
            place_label=label,
            country_code=country_code,
        )
    return HomeNotice(
        status="unknown",
        ask_postal=True,
        notice_key="dash.home_not_found",
        place_label=label,
        country_code=country_code,
        offer_change_place=True,
    )


def home_location_notice(
    location: Any,
    config: Any | None = None,
    *,
    cross_border: bool | None = None,
    home_country: str | None = None,
) -> HomeNotice:
    """Re-read the current home place. Does not persist coordinates or guess a PLZ.

    Uses ``cached_home_resolution``, the same lookup as ``resolve_home``.
    ``aufgelöst`` is returned only for a real resolution.
    """
    address, postal, city, _country = _home_text(location)
    if not postal and not city and not address:
        return HomeNotice(status="missing", ask_postal=True, notice_key="dash.home_missing")
    border, home_cc = home_resolve_params(
        location, config, cross_border=cross_border, home_country=home_country
    )
    return _notice_from_resolution(
        location,
        cached_home_resolution(location, cross_border=border, home_country=home_cc),
    )


def apply_visible_home(
    location: Any,
    *,
    street: str = "",
    postal_code: str = "",
    city: str = "",
    country: str = "",
) -> bool:
    """Copy a contact address into the search home.

    Callers must invoke this only when the user has checked the search-home
    opt-in. A changed contact address alone must not be copied, and neither
    must a stored CV contact while saving skills or any other section.

    Returns True when persisted coordinates were cleared. Does not invent a PLZ.
    Empty street/PLZ/city leaves an existing search home unchanged.
    """
    postal = (postal_code or "").strip()
    city_n = (city or "").strip()
    street_n = (street or "").strip()
    country_n = (country or "").strip()
    if not postal and not city_n and not street_n:
        return False
    parts = [part for part in (street_n, f"{postal} {city_n}".strip(), country_n) if part]
    new_home = ", ".join(parts)
    changed = (
        new_home != (getattr(location, "home_address", "") or "").strip()
        or postal != (getattr(location, "postal_code", "") or "").strip()
        or city_n != (getattr(location, "city", "") or "").strip()
    )
    if changed:
        location.home_latitude = None
        location.home_longitude = None
        location.home_geocoded_address = ""
    location.home_address = new_home
    location.postal_code = postal
    location.city = city_n
    if country_n:
        location.country = country_n
    return changed


def _coords_match_address(location: Any) -> bool:
    address = (getattr(location, "home_address", "") or "").strip()
    postal = (getattr(location, "postal_code", "") or "").strip()
    city = (getattr(location, "city", "") or "").strip()
    lat = getattr(location, "home_latitude", None)
    lon = getattr(location, "home_longitude", None)
    stored = _address_fingerprint(getattr(location, "home_geocoded_address", "") or "")
    current = _address_fingerprint(address or (f"{postal}|{city}" if (postal or city) else ""))
    try:
        if lat is None or lon is None or not current:
            return False
        lat_f, lon_f = float(lat), float(lon)
    except (TypeError, ValueError):
        return False
    return (
        -90.0 <= lat_f <= 90.0
        and -180.0 <= lon_f <= 180.0
        and (not stored or stored == current)
    )


def _locality_from_display(display_name: str, postal_code: str) -> str:
    """Middle token of a postal display (``10115, Berlin, DE`` → ``Berlin``)."""
    postal = (postal_code or "").strip()
    for part in (display_name or "").split(","):
        token = part.strip()
        if not token or token == postal:
            continue
        if len(token) == 2 and token.isalpha():
            continue
        return token
    return ""


def commit_loaded_home(location: Any) -> str:
    """Write a finished local resolution onto ``location``.

    Returns ``resolved``, ``unchanged``, ``pending``, or ``unresolved``.
    A still-loading index is ``pending`` and stores neither coordinates nor an
    error string. A genuine miss stays without coordinates so the notice can
    keep asking for a real PLZ. Does not start a second geo stack.
    """
    if _coords_match_address(location):
        return "unchanged"
    address = (getattr(location, "home_address", "") or "").strip()
    postal = (getattr(location, "postal_code", "") or "").strip()
    city = (getattr(location, "city", "") or "").strip()
    country = (getattr(location, "country", "") or "").strip() or "DE"
    if not postal and not city and not address:
        return "unresolved"
    border, home_cc = home_resolve_params(location)
    resolution = cached_home_resolution(
        location, cross_border=border, home_country=home_cc
    )
    if resolution is None or resolution.reason == "geo_index_loading":
        return "pending"
    if not resolution.ok or resolution.latitude is None or resolution.longitude is None:
        return "unresolved"
    location.home_latitude = float(resolution.latitude)
    location.home_longitude = float(resolution.longitude)
    location.home_geocoded_address = address or (resolution.display_name or "")
    if not city:
        locality = _locality_from_display(resolution.display_name or "", postal)
        if locality:
            location.city = locality
    return "resolved"


def store_user_home_coordinates(location: Any) -> str:
    """Write coordinates after the user changed the search home.

    This is the only profile-UI writer. Startup and other section saves keep
    the resolution in ``_HOME_RESOLUTION_CACHE`` and leave ``profile.yaml``
    coordinates untouched. Street, postal code, and city are not rewritten.
    Returns ``resolved``, ``pending``, or ``unresolved``.
    """
    address = (getattr(location, "home_address", "") or "").strip()
    postal = (getattr(location, "postal_code", "") or "").strip()
    city = (getattr(location, "city", "") or "").strip()
    if not postal and not city and not address:
        location.home_latitude = None
        location.home_longitude = None
        location.home_geocoded_address = ""
        return "unresolved"
    border, home_cc = home_resolve_params(location)
    resolution = cached_home_resolution(
        location, cross_border=border, home_country=home_cc
    )
    if resolution is not None and resolution.reason == "geo_index_loading":
        return "pending"
    if (
        resolution is None
        or not resolution.ok
        or resolution.latitude is None
        or resolution.longitude is None
    ):
        location.home_latitude = None
        location.home_longitude = None
        location.home_geocoded_address = ""
        return "unresolved"
    location.home_latitude = float(resolution.latitude)
    location.home_longitude = float(resolution.longitude)
    location.home_geocoded_address = address or (
        f"{postal}|{city}" if (postal or city) else ""
    )
    return "resolved"


@dataclass
class HomeResolution:
    """Outcome of resolving the search-origin / home coordinates."""

    coords: tuple[float, float] | None = None
    resolved: bool = False
    source: str = ""
    warning: str = ""
    address_used: str = ""
    country_code: str = ""


@dataclass
class EnrichStats:
    total: int = 0
    remote_skipped: int = 0
    resolved: int = 0
    cached: int = 0
    failed: int = 0
    unique_queries: int = 0
    home_resolved: bool = False
    home_warning: str = ""
    skipped_distance_no_home: bool = False
    unknown_locations: int = 0
    ambiguous_locations: int = 0
    cross_border_enabled: bool = True
    airline_ok: int = 0
    airline_unknown: int = 0
    airline_prefilter_excluded: int = 0
    road_ok: int = 0
    road_unknown: int = 0
    # Back-compat aliases used by older stats consumers
    google_route_ok: int = 0
    google_route_unknown: int = 0


def location_cache_key(
    *,
    address: str = "",
    city: str = "",
    postal_code: str = "",
    latitude: float | None = None,
    longitude: float | None = None,
    country_code: str = "",
) -> str:
    """Stable key for deduplicating geocode work within a run."""
    place = normalize_place_fields(
        address=address,
        city=city,
        postal_code=postal_code,
        latitude=latitude,
        longitude=longitude,
        country_code=country_code,
    )
    key = cache_query_key(place)
    if key:
        return key
    if latitude is not None and longitude is not None:
        return f"ll:{latitude:.5f},{longitude:.5f}"
    parts = [p.strip().lower() for p in (address, postal_code, city) if p and str(p).strip()]
    if not parts:
        return ""
    return "|".join(parts)


@dataclass
class LocationService:
    """Local DACH resolve + SQLite cache + Haversine airline distance."""

    db: "Database"
    config: "AppConfig"
    timeout_s: float = DEFAULT_GEOCODE_TIMEOUT_S
    _home: tuple[float, float] | None = field(default=None, init=False, repr=False)
    _home_resolution: HomeResolution | None = field(default=None, init=False, repr=False)
    _memory_hits: dict[str, PlaceResolution | None] = field(
        default_factory=dict, init=False, repr=False
    )
    _dataset_version: str = field(default="", init=False, repr=False)
    home_updated: bool = field(default=False, init=False, repr=False)
    stats: EnrichStats = field(default_factory=EnrichStats, init=False)

    def __post_init__(self) -> None:
        root = getattr(self.config, "root", None)
        mgr = get_geo_dataset_manager(root)
        info = mgr.ensure_active()
        self._dataset_version = info.version if info.valid else GEO_DATA_VERSION_UNRESOLVED
        # Drop maps-related settings values if present (ignored, not used).
        settings = getattr(self.config, "settings", None)
        if settings is not None:
            geo = getattr(settings, "geocoder", "") or ""
            if str(geo).lower() in {"google", "nominatim", "maps", "osrm"}:
                settings.geocoder = "local"

    @property
    def home_resolved(self) -> bool:
        res = self._home_resolution
        return bool(res and res.resolved and res.coords)

    @property
    def home_warning(self) -> str:
        res = self._home_resolution
        return (res.warning if res else "") or ""

    @property
    def cross_border(self) -> bool:
        return cross_border_dach_enabled(self.config)

    def home_country(self) -> str:
        loc = self.config.profile.location
        return normalize_country_code(getattr(loc, "country", "") or "") or "DE"

    def dataset_info(self):
        return get_geo_dataset_manager(getattr(self.config, "root", None)).current_info()

    def resolve_home(self) -> HomeResolution:
        """Resolve home once locally. Never uses a silent DE-center fallback.

        The lookup is ``cached_home_resolution`` with this service's
        ``cross_border`` and ``home_country``. The hint reads that same result.
        """
        loc = self.config.profile.location
        address = (loc.home_address or "").strip()
        postal = getattr(loc, "postal_code", "") or ""
        city = getattr(loc, "city", "") or ""
        current_fp = _address_fingerprint(address or f"{postal}|{city}")
        stored_fp = _address_fingerprint(getattr(loc, "home_geocoded_address", "") or "")
        home_cc = self.home_country()
        border = self.cross_border
        stamp = (border, home_cc, current_fp)
        if self._home_resolution is not None and getattr(self, "_home_stamp", None) == stamp:
            return self._home_resolution

        if loc.home_latitude is not None and loc.home_longitude is not None:
            if not current_fp:
                loc.home_latitude = None
                loc.home_longitude = None
                loc.home_geocoded_address = ""
                self.home_updated = True
            elif stored_fp and stored_fp != current_fp:
                loc.home_latitude = None
                loc.home_longitude = None
                loc.home_geocoded_address = ""
                self.home_updated = True
            elif not stored_fp and current_fp:
                loc.home_geocoded_address = address or current_fp
                self.home_updated = True

        if not postal and not city and not address:
            warning = (
                "Such-Standort fehlt: bitte Wohnort/PLZ und Land unter Profil setzen. "
                "Distanzfilter ist deaktiviert, bis der Standort auflösbar ist."
            )
            logger.warning(warning)
            self._home_resolution = HomeResolution(
                coords=None,
                resolved=False,
                source="unresolved",
                warning=warning,
                address_used="",
                country_code=home_cc,
            )
            self.stats.home_resolved = False
            self.stats.home_warning = warning
            self.stats.skipped_distance_no_home = True
            self._home_stamp = stamp
            return self._home_resolution

        resolution = cached_home_resolution(
            loc, cross_border=border, home_country=home_cc
        )
        if resolution is not None and resolution.reason == "persisted_coords" and resolution.ok:
            coords = (float(resolution.latitude), float(resolution.longitude))  # type: ignore[arg-type]
            self._home = coords
            self._home_resolution = HomeResolution(
                coords=coords,
                resolved=True,
                source="persisted",
                address_used=address,
                country_code=home_cc,
            )
            self._home_stamp = stamp
            self.stats.home_resolved = True
            return self._home_resolution
        if resolution is None or not resolution.ok:
            warning = HOME_PLZ_HINT
            logger.warning(warning)
            self._home = None
            self._home_resolution = HomeResolution(
                coords=None,
                resolved=False,
                source="unresolved",
                warning=warning,
                address_used=address,
                country_code=home_cc,
            )
            self.stats.home_resolved = False
            self.stats.home_warning = warning
            self.stats.skipped_distance_no_home = True
            self._home_stamp = stamp
            return self._home_resolution

        coords = (float(resolution.latitude), float(resolution.longitude))  # type: ignore[arg-type]
        self._home = coords
        loc.home_latitude = coords[0]
        loc.home_longitude = coords[1]
        loc.home_geocoded_address = address or resolution.display_name
        self.home_updated = True
        self._home_resolution = HomeResolution(
            coords=coords,
            resolved=True,
            source=resolution.data_source or GEO_DATA_SOURCE_LOCAL,
            address_used=address or resolution.display_name,
            country_code=home_cc,
        )
        self._home_stamp = stamp
        self.stats.home_resolved = True
        return self._home_resolution

    def ensure_home_coords(self) -> tuple[float, float] | None:
        res = self.resolve_home()
        return res.coords

    def _cache_trusted(self, query: str) -> PlaceResolution | None:
        rec = self.db.get_geocode_record(query)
        if not rec:
            return None
        src = (rec.get("data_source") or "").strip()
        ver = (rec.get("data_version") or "").strip()
        display = rec.get("display_name") or ""
        if display == UNRESOLVED_MARKER:
            age = _age_seconds(rec.get("cached_at"))
            if age is not None and age < UNRESOLVED_TTL_S:
                return PlaceResolution(
                    status="UNKNOWN",
                    reason="cached_unresolved",
                    data_source=GEO_DATA_SOURCE_UNRESOLVED,
                    data_version=GEO_DATA_VERSION_UNRESOLVED,
                )
            return None
        if src in STALE_GEO_SOURCES or src not in TRUSTED_GEO_SOURCES:
            logger.debug("Ignoring stale geocode cache for %r (source=%s)", query, src or "empty")
            return None
        if self._dataset_version and ver and ver not in {
            self._dataset_version,
            GEO_DATA_VERSION_UNRESOLVED,
            "wgs84-1",
        }:
            # Lazy re-resolve when dataset version changed
            logger.debug("Stale geo dataset version for %r (%s != %s)", query, ver, self._dataset_version)
            return None
        lat, lon = rec.get("latitude"), rec.get("longitude")
        if lat is None or lon is None:
            return None
        status = (rec.get("resolution_status") or "RESOLVED").upper()
        if status not in {"RESOLVED", "UNKNOWN", "AMBIGUOUS"}:
            status = "RESOLVED"
        return PlaceResolution(
            status=status,  # type: ignore[arg-type]
            latitude=float(lat),
            longitude=float(lon),
            country_code=rec.get("country_code") or "",
            display_name=display,
            data_source=src,
            data_version=ver or self._dataset_version,
            precision="postal_centroid",
        )

    def resolve_job_place(
        self,
        *,
        address: str = "",
        city: str = "",
        postal_code: str = "",
        latitude: float | None = None,
        longitude: float | None = None,
        country_code: str = "",
        remote_type: str = "",
    ) -> PlaceResolution:
        """Resolve a job workplace locally (or explicit coords)."""
        place = normalize_place_fields(
            address=address,
            city=city,
            postal_code=postal_code,
            latitude=latitude,
            longitude=longitude,
            country_code=country_code,
            remote_type=remote_type,
        )
        key = cache_query_key(place) or location_cache_key(
            address=address,
            city=city,
            postal_code=postal_code,
            latitude=latitude,
            longitude=longitude,
            country_code=country_code,
        )
        if key and key in self._memory_hits:
            hit = self._memory_hits[key]
            self.stats.cached += 1
            return hit or PlaceResolution(
                status="UNKNOWN",
                reason="memory_miss",
                data_source=GEO_DATA_SOURCE_UNRESOLVED,
                data_version=GEO_DATA_VERSION_UNRESOLVED,
            )

        if key:
            cached = self._cache_trusted(key)
            if cached is not None:
                self._memory_hits[key] = cached if cached.ok else None
                self.stats.cached += 1
                return cached

        resolution = resolve_place(
            place,
            cross_border=self.cross_border,
            home_country=self.home_country(),
            allow_network=False,
        )
        if key:
            self._memory_hits[key] = resolution if resolution.ok else None
            try:
                if resolution.ok:
                    self.db.set_geocode(
                        key,
                        float(resolution.latitude),  # type: ignore[arg-type]
                        float(resolution.longitude),  # type: ignore[arg-type]
                        resolution.display_name or key,
                        data_source=resolution.data_source or GEO_DATA_SOURCE_GEONAMES,
                        data_version=resolution.data_version or self._dataset_version,
                        country_code=resolution.country_code,
                        resolution_status="RESOLVED",
                    )
                    self.stats.resolved += 1
                else:
                    self.db.set_geocode(
                        key,
                        0.0,
                        0.0,
                        UNRESOLVED_MARKER,
                        data_source=GEO_DATA_SOURCE_UNRESOLVED,
                        data_version=GEO_DATA_VERSION_UNRESOLVED,
                        country_code=resolution.country_code,
                        resolution_status=resolution.status,
                    )
                    self.stats.failed += 1
            except Exception as exc:
                logger.debug("geocode cache write failed: %s", type(exc).__name__)
        return resolution

    def distance_for_job_location(
        self,
        *,
        address: str = "",
        city: str = "",
        postal_code: str = "",
        latitude: float | None = None,
        longitude: float | None = None,
        country_code: str = "",
        remote_type: str = "",
    ) -> tuple[float | None, float | None, float | None]:
        """Return (lat, lon, airline_km). Unresolved → UNKNOWN. Never invents 0 km."""
        home = self.ensure_home_coords()
        resolution = self.resolve_job_place(
            address=address,
            city=city,
            postal_code=postal_code,
            latitude=latitude,
            longitude=longitude,
            country_code=country_code,
            remote_type=remote_type,
        )
        if resolution.status == "AMBIGUOUS":
            self.stats.ambiguous_locations += 1
            self.stats.airline_unknown += 1
            return None, None, DISTANCE_UNKNOWN
        if not resolution.ok:
            self.stats.unknown_locations += 1
            self.stats.airline_unknown += 1
            return None, None, DISTANCE_UNKNOWN
        lat, lon = float(resolution.latitude), float(resolution.longitude)  # type: ignore[arg-type]
        if home is None:
            self.stats.airline_unknown += 1
            return lat, lon, DISTANCE_UNKNOWN
        try:
            dist = haversine_km(home[0], home[1], lat, lon)
        except ValueError:
            self.stats.airline_unknown += 1
            return lat, lon, DISTANCE_UNKNOWN
        self.stats.airline_ok += 1
        return lat, lon, dist

    def commute_for_job_location(
        self,
        *,
        address: str = "",
        city: str = "",
        postal_code: str = "",
        latitude: float | None = None,
        longitude: float | None = None,
        country_code: str = "",
        remote_type: str = "",
    ) -> tuple[float | None, float | None, float | None, float | None]:
        """Return (lat, lon, airline_km, duration_minutes).

        duration is always None in v1 — no invented drive time.
        """
        lat, lon, dist = self.distance_for_job_location(
            address=address,
            city=city,
            postal_code=postal_code,
            latitude=latitude,
            longitude=longitude,
            country_code=country_code,
            remote_type=remote_type,
        )
        return lat, lon, dist, None


def _age_seconds(cached_at: str | None) -> float | None:
    if not cached_at:
        return None
    try:
        from datetime import datetime, timezone

        text = str(cached_at).replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt).total_seconds()
    except Exception:
        return None


def _address_fingerprint(address: str) -> str:
    return " ".join((address or "").strip().lower().split())


def _plz_from_address(home_address: str) -> str:
    import re

    m = re.search(r"\b(\d{4,5})\b", home_address or "")
    return m.group(1) if m else ""


def _city_from_address(home_address: str) -> str:
    """Extract a single usable city token from a home address."""
    raw = (home_address or "").strip()
    if not raw:
        return ""
    for sep in ("/", ";", " und ", " oder ", " | "):
        if sep in raw:
            raw = raw.split(sep, 1)[0].strip()
            break
    parts = [p for p in raw.split(",") if p.strip()]

    skip = {
        "germany",
        "deutschland",
        "de",
        "austria",
        "österreich",
        "oesterreich",
        "at",
        "switzerland",
        "schweiz",
        "ch",
    }
    for part in reversed(parts):
        low = part.lower().strip()
        if low in skip:
            continue
        tokens = part.split()
        words = [t for t in tokens if not any(c.isdigit() for c in t)]
        if not words:
            continue
        if tokens and tokens[0].isdigit():
            return " ".join(words)
        if any(c.isdigit() for c in part):
            continue
        return " ".join(words)
    return ""


def enrich_job_locations(
    jobs: list,
    location: LocationService,
    *,
    progress_callback: Callable[[str], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> list:
    """Enrich jobs with local geocode + airline distance. Dedupes identical queries.

    Call only for fachlich suitable candidates (after hard matching).
    Remote jobs skip workplace geocoding. Unknown leave distance_km as None.
    """

    def progress(msg: str) -> None:
        if progress_callback:
            try:
                progress_callback(msg)
            except Exception:
                pass

    def stopped() -> bool:
        try:
            return bool(should_stop and should_stop())
        except Exception:
            return False

    location.stats = EnrichStats(
        total=len(jobs),
        cross_border_enabled=location.cross_border,
    )
    home = location.resolve_home()
    if not home.resolved:
        progress(home.warning or "Heimatstandort unklar — Distanzfilter deaktiviert.")
        location.stats.home_resolved = False
        location.stats.home_warning = home.warning
        location.stats.skipped_distance_no_home = True
        # Distance is already unknown. Skip workplace geocoding so the radius
        # skip returns immediately and cannot stall on ambiguous place scans.
        for job in jobs:
            if getattr(job, "remote_type", "") == "remote":
                job.distance_km = None
                if hasattr(job, "commute_duration_minutes"):
                    job.commute_duration_minutes = None
                if hasattr(job, "distance_source"):
                    job.distance_source = ""
                location.stats.remote_skipped += 1
                continue
            job.distance_km = None
            if hasattr(job, "distance_source"):
                job.distance_source = ""
            if hasattr(job, "commute_duration_minutes"):
                job.commute_duration_minutes = None
            location.stats.unknown_locations += 1
        return jobs
    location.stats.home_resolved = True

    groups: dict[str, list] = {}
    order: list[str] = []
    for job in jobs:
        if getattr(job, "remote_type", "") == "remote":
            job.distance_km = None
            if hasattr(job, "commute_duration_minutes"):
                job.commute_duration_minutes = None
            if hasattr(job, "distance_source"):
                job.distance_source = ""
            location.stats.remote_skipped += 1
            continue
        place = place_from_job_like(job)
        if place.country_code and hasattr(job, "country_code"):
            if not (getattr(job, "country_code", "") or "").strip():
                job.country_code = place.country_code
        key = location_cache_key(
            address=getattr(job, "address", "") or "",
            city=getattr(job, "city", "") or "",
            postal_code=getattr(job, "postal_code", "") or "",
            latitude=getattr(job, "latitude", None),
            longitude=getattr(job, "longitude", None),
            country_code=getattr(job, "country_code", "") or place.country_code,
        )
        if not key:
            location.stats.unknown_locations += 1
            continue
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(job)

    location.stats.unique_queries = len(order)
    total_q = max(len(order), 1)

    for idx, key in enumerate(order, start=1):
        if stopped():
            progress(f"Standorte anreichern abgebrochen ({idx - 1}/{len(order)}).")
            break
        group = groups[key]
        sample = group[0]
        progress(
            f"Standorte anreichern: {idx}/{len(order)} "
            f"(gelöst {location.stats.resolved}, Cache {location.stats.cached}, "
            f"offen {location.stats.failed})"
        )
        sample_place = place_from_job_like(sample)
        lat, lon, dist, _dur = location.commute_for_job_location(
            address=getattr(sample, "address", "") or "",
            city=getattr(sample, "city", "") or "",
            postal_code=getattr(sample, "postal_code", "") or "",
            latitude=getattr(sample, "latitude", None),
            longitude=getattr(sample, "longitude", None),
            country_code=getattr(sample, "country_code", "") or sample_place.country_code,
            remote_type=getattr(sample, "remote_type", "") or "",
        )
        for job in group:
            if lat is not None:
                job.latitude = lat
                job.longitude = lon
            # Airline is invisible prefilter only — never written to distance_km.
            if hasattr(job, "airline_km"):
                job.airline_km = dist
            job.distance_km = None
            if hasattr(job, "distance_source"):
                job.distance_source = ""
            if hasattr(job, "distance_error"):
                job.distance_error = (
                    "" if dist is not None else "Standort nicht auflösbar"
                )
            if hasattr(job, "commute_duration_minutes"):
                job.commute_duration_minutes = None
            cc = getattr(job, "country_code", "") or sample_place.country_code
            if cc and hasattr(job, "country_code"):
                job.country_code = cc

        # Road distance only for jobs that survive the airline prefilter
        # (airline > radius → skip BRouter; airline == radius still routes).
        max_km = float(
            getattr(getattr(location.config.profile, "location", None), "max_distance_km", 0)
            or 0
        )
        home_coords = location.ensure_home_coords()
        if (
            home_coords is not None
            and lat is not None
            and lon is not None
            and dist is not None
            and (max_km <= 0 or float(dist) <= max_km)
        ):
            road = _route_road_km(home_coords[0], home_coords[1], float(lat), float(lon))
            for job in group:
                if road.ok and road.distance_km is not None:
                    job.distance_km = float(road.distance_km)
                    if hasattr(job, "distance_source"):
                        job.distance_source = road.engine
                    if hasattr(job, "distance_error"):
                        job.distance_error = ""
                    location.stats.road_ok += 1
                else:
                    job.distance_km = None
                    if hasattr(job, "distance_source"):
                        job.distance_source = ""
                    if hasattr(job, "distance_error"):
                        job.distance_error = _road_error_label(road.error)
                    location.stats.road_unknown += 1
        elif dist is not None and max_km > 0 and float(dist) > max_km:
            # Airline prefilter hit: keep airline_km for distance_exclude only.
            # distance_km stays None — never surface airline as Fahrstrecke.
            for job in group:
                if hasattr(job, "airline_km"):
                    job.airline_km = dist
                job.distance_km = None
                if hasattr(job, "distance_source"):
                    job.distance_source = ""
                if hasattr(job, "distance_error"):
                    job.distance_error = ""
                location.stats.airline_prefilter_excluded = (
                    getattr(location.stats, "airline_prefilter_excluded", 0) + 1
                )

    location.stats.google_route_ok = location.stats.road_ok or location.stats.airline_ok
    location.stats.google_route_unknown = (
        location.stats.road_unknown or location.stats.airline_unknown
    )
    progress(
        f"Standorte fertig: {len(order)}/{total_q} Orte — "
        f"gelöst {location.stats.resolved}, Cache {location.stats.cached}, "
        f"ungeklärt {location.stats.failed}, Remote übersprungen {location.stats.remote_skipped}, "
        f"Luftlinie OK {location.stats.airline_ok}, UNKNOWN {location.stats.airline_unknown}, "
        f"Fahrstrecke OK {location.stats.road_ok}, UNKNOWN {location.stats.road_unknown}"
        + ("" if home.resolved else " | Distanzfilter inaktiv (Heimat unklar)")
    )
    return jobs


def _road_error_label(error: str) -> str:
    text = (error or "").strip()
    low = text.casefold()
    if "island" in low:
        return "Routing-Insel / kein Straßenanschluss"
    if "start:" in low or "jar missing" in low or "profiles missing" in low:
        return "Routing-Dienst nicht verfügbar"
    if "segment" in low or "missing" in low:
        return "Kartensegment fehlt"
    if "http_4" in low or "http_5" in low:
        return "Routingfehler"
    if not text:
        return "Routingfehler"
    # Keep short — UI appends this in parentheses.
    return text[:80]


def _route_road_km(
    lat1: float, lon1: float, lat2: float, lon2: float
):
    from core.road_route_brouter import RoadRouteResult, get_brouter_runtime

    try:
        return get_brouter_runtime().route(lat1, lon1, lat2, lon2)
    except Exception as exc:  # noqa: BLE001
        return RoadRouteResult(ok=False, distance_km=None, error=str(exc))
