"""Geocoding cache and Google road-route commute (NEXT-05).

Production authority: Google Maps Platform only
  - Geocoding API (via minimal authenticated proxy)
  - Routes API Compute Route Matrix Essentials

Forbidden as authoritative distance:
  - Haversine / airline
  - Nominatim / pgeocode / OSRM / geopy

On Google failure → DISTANCE_UNKNOWN (None). Never invent km.
max_commute_km means drivable road route ≤ N km — not straight-line.

Home coordinates are resolved once per LocationService instance / run.
Failed home resolution must NOT silently use arbitrary Germany center coordinates.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable

from core.geo_normalize import (
    normalize_country_code,
    normalize_place_fields,
)
from core.geo_resolve import (
    GEO_DATA_SOURCE_UNRESOLVED,
    GEO_DATA_VERSION_UNRESOLVED,
    PlaceResolution,
    UNRESOLVED_MARKER,
    cache_query_key,
    haversine_km,  # diagnostic / tests ONLY — never authoritative commute
    place_from_job_like,
)
from integrations.maps.contracts import DISTANCE_UNKNOWN
from integrations.maps.service import MapsGeoService, get_maps_service

if TYPE_CHECKING:
    from core.config import AppConfig
    from core.database import Database

logger = logging.getLogger("karrierekrake")

# Re-export for existing imports / tests
__all__ = [
    "UNRESOLVED_MARKER",
    "DISTANCE_UNKNOWN",
    "HomeResolution",
    "EnrichStats",
    "LocationService",
    "haversine_km",
    "location_cache_key",
    "enrich_job_locations",
    "cross_border_dach_enabled",
]

DEFAULT_GEOCODE_TIMEOUT_S = 12.0
# Soft cap on unique geocode network attempts per enrich run (cached hits free).
MAX_UNIQUE_GEOCODE_ATTEMPTS_PER_RUN = 80
# Negative-cache TTL for unresolved lookups (seconds). Successes stay until cleared.
UNRESOLVED_TTL_S = 6 * 60 * 60

GEO_DATA_SOURCE_GOOGLE = "google_geocoding"
GEO_DATA_VERSION_GOOGLE = "maps-geocoding-v1"
GEO_DATA_SOURCE_ROUTE = "google_route_matrix"
GEO_DATA_VERSION_ROUTE = "routes-matrix-essentials-v1"


def cross_border_dach_enabled(config: "AppConfig") -> bool:
    """Feature toggle: DACH commute across DE/AT/CH (default on)."""
    settings = getattr(config, "settings", None)
    if settings is not None and hasattr(settings, "cross_border_dach_enabled"):
        return bool(settings.cross_border_dach_enabled)
    loc = getattr(getattr(config, "profile", None), "location", None)
    if loc is not None and hasattr(loc, "cross_border_dach"):
        return bool(loc.cross_border_dach)
    return True


@dataclass
class HomeResolution:
    """Outcome of resolving the search-origin / home coordinates."""

    coords: tuple[float, float] | None = None
    resolved: bool = False
    source: str = ""  # persisted | google_geocoding | unresolved
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
    """Geocode via Google proxy, cache in SQLite, commute via Route Matrix."""

    db: "Database"
    config: "AppConfig"
    timeout_s: float = DEFAULT_GEOCODE_TIMEOUT_S
    maps: MapsGeoService | None = None
    _home: tuple[float, float] | None = field(default=None, init=False, repr=False)
    _home_resolution: HomeResolution | None = field(default=None, init=False, repr=False)
    _memory_hits: dict[str, tuple[float, float, str] | None] = field(
        default_factory=dict, init=False, repr=False
    )
    _route_cache: dict[str, tuple[float | None, float | None]] = field(
        default_factory=dict, init=False, repr=False
    )
    _network_attempts: int = field(default=0, init=False, repr=False)
    home_updated: bool = field(default=False, init=False, repr=False)
    stats: EnrichStats = field(default_factory=EnrichStats, init=False)

    def __post_init__(self) -> None:
        if self.maps is None:
            self.maps = get_maps_service()

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

    def _region(self) -> str:
        return self.home_country().lower()

    def resolve_home(self) -> HomeResolution:
        """Resolve home once via Google. Never uses a silent DE-center fallback."""
        if self._home_resolution is not None:
            return self._home_resolution

        loc = self.config.profile.location
        address = (loc.home_address or "").strip()
        current_fp = _address_fingerprint(address)
        stored_fp = _address_fingerprint(getattr(loc, "home_geocoded_address", "") or "")
        home_cc = self.home_country()

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
                loc.home_geocoded_address = address
                self.home_updated = True

        if loc.home_latitude is not None and loc.home_longitude is not None:
            coords = (float(loc.home_latitude), float(loc.home_longitude))
            self._home = coords
            self._home_resolution = HomeResolution(
                coords=coords,
                resolved=True,
                source="persisted",
                address_used=address,
                country_code=home_cc,
            )
            self.stats.home_resolved = True
            return self._home_resolution

        if not address:
            warning = (
                "Such-Standort fehlt: bitte eine Heimatadresse unter Profil/Standort setzen. "
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
            return self._home_resolution

        result = self.geocode(address)
        if not result:
            cityish = _city_from_address(address)
            if cityish and cityish.lower() != address.lower():
                suffix = _country_suffix(home_cc, self.cross_border)
                result = self.geocode(f"{cityish}, {suffix}")

        if not result:
            warning = (
                f"Heimatadresse konnte nicht geocodiert werden (Google): {address!r}. "
                "Distanzfilter übersprungen — bitte Adresse korrigieren "
                "(kein Haversine-/Nominatim-Fallback)."
            )
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
            return self._home_resolution

        coords = (float(result[0]), float(result[1]))
        self._home = coords
        loc.home_latitude = coords[0]
        loc.home_longitude = coords[1]
        loc.home_geocoded_address = address
        self.home_updated = True
        self._home_resolution = HomeResolution(
            coords=coords,
            resolved=True,
            source=GEO_DATA_SOURCE_GOOGLE,
            address_used=address,
            country_code=home_cc,
        )
        self.stats.home_resolved = True
        return self._home_resolution

    def ensure_home_coords(self) -> tuple[float, float] | None:
        """Resolve home once; return coords or None if unresolved (no DE fallback)."""
        res = self.resolve_home()
        return res.coords

    def geocode(
        self,
        query: str,
        *,
        country_codes: list[str] | None = None,
    ) -> tuple[float, float, str] | None:
        """Google Geocoding via authenticated proxy. Failure → None."""
        del country_codes  # region comes from home country; kept for API compat
        query = (query or "").strip()
        if not query:
            return None
        key = query.lower()
        if key in self._memory_hits:
            self.stats.cached += 1
            return self._memory_hits[key]

        cached = self.db.get_geocode(query)
        if cached is not None:
            lat, lon, display, cached_at = cached[:4]
            if display == UNRESOLVED_MARKER:
                age = _age_seconds(cached_at)
                if age is not None and age < UNRESOLVED_TTL_S:
                    self._memory_hits[key] = None
                    self.stats.cached += 1
                    return None
            else:
                # Only trust Google-sourced cache as production authority.
                rec = self.db.get_geocode_record(query)
                src = (rec or {}).get("data_source") or ""
                if src not in {GEO_DATA_SOURCE_GOOGLE, "google_geocoding"}:
                    # Legacy Nominatim/pgeocode/empty rows — re-resolve via Google.
                    logger.debug(
                        "Ignoring non-Google geocode cache for %r (source=%s)",
                        query,
                        src or "empty",
                    )
                else:
                    result = (lat, lon, display)
                    self._memory_hits[key] = result
                    self.stats.cached += 1
                    return result

        if self._network_attempts >= MAX_UNIQUE_GEOCODE_ATTEMPTS_PER_RUN:
            logger.warning(
                "Geocode attempt cap (%s) reached — skipping %r",
                MAX_UNIQUE_GEOCODE_ATTEMPTS_PER_RUN,
                query,
            )
            self.stats.failed += 1
            return None

        self._network_attempts += 1
        assert self.maps is not None
        geo = self.maps.geocode(query, region=self._region())
        if geo is None:
            self._store_unresolved(query)
            self.stats.failed += 1
            return None
        self.db.set_geocode(
            query,
            geo.latitude,
            geo.longitude,
            geo.formatted_address or query,
            data_source=GEO_DATA_SOURCE_GOOGLE,
            data_version=GEO_DATA_VERSION_GOOGLE,
            country_code=geo.country_code,
            resolution_status="RESOLVED",
        )
        result = (geo.latitude, geo.longitude, geo.formatted_address or query)
        self._memory_hits[key] = result
        self.stats.resolved += 1
        return result

    def _store_unresolved(self, query: str) -> None:
        key = query.lower().strip()
        self._memory_hits[key] = None
        try:
            self.db.set_geocode(
                query,
                0.0,
                0.0,
                UNRESOLVED_MARKER,
                data_source=GEO_DATA_SOURCE_UNRESOLVED,
                data_version=GEO_DATA_VERSION_UNRESOLVED,
                resolution_status="UNKNOWN",
            )
        except Exception as exc:
            logger.debug("Could not persist unresolved geocode for %r: %s", query, exc)

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
        """Resolve a job workplace via Google geocoding (or explicit coords)."""
        if (remote_type or "").lower() == "remote":
            return PlaceResolution(
                status="UNKNOWN",
                reason="remote_no_workplace",
                data_source=GEO_DATA_SOURCE_UNRESOLVED,
                data_version=GEO_DATA_VERSION_UNRESOLVED,
            )
        if latitude is not None and longitude is not None:
            return PlaceResolution(
                status="RESOLVED",
                latitude=float(latitude),
                longitude=float(longitude),
                country_code=normalize_country_code(country_code) or "",
                display_name=address or city or "coords",
                data_source="explicit_coords",
                data_version="wgs84-1",
            )
        suffix = _country_suffix(
            normalize_country_code(country_code) or self.home_country(),
            self.cross_border,
        )
        query_parts = [p for p in (address, postal_code, city) if p]
        if not query_parts:
            return PlaceResolution(
                status="UNKNOWN",
                reason="empty_query",
                data_source=GEO_DATA_SOURCE_UNRESOLVED,
                data_version=GEO_DATA_VERSION_UNRESOLVED,
            )
        query = ", ".join(query_parts + [suffix])
        result = self.geocode(query)
        if not result and city:
            result = self.geocode(f"{city}, {suffix}")
        if not result and postal_code:
            result = self.geocode(f"{postal_code}, {suffix}")
        if not result:
            return PlaceResolution(
                status="UNKNOWN",
                reason="google_geocode_miss",
                data_source=GEO_DATA_SOURCE_UNRESOLVED,
                data_version=GEO_DATA_VERSION_UNRESOLVED,
            )
        lat, lon, display = result
        return PlaceResolution(
            status="RESOLVED",
            latitude=lat,
            longitude=lon,
            country_code=normalize_country_code(country_code) or self.home_country(),
            display_name=display,
            data_source=GEO_DATA_SOURCE_GOOGLE,
            data_version=GEO_DATA_VERSION_GOOGLE,
        )

    def _road_commute(
        self,
        home: tuple[float, float],
        job_lat: float,
        job_lon: float,
    ) -> tuple[float | None, float | None]:
        """Return (distance_km, duration_minutes) from Google Route Matrix only."""
        key = f"{home[0]:.5f},{home[1]:.5f}|{job_lat:.5f},{job_lon:.5f}"
        if key in self._route_cache:
            return self._route_cache[key]
        assert self.maps is not None
        decision = self.maps.commute_decision(
            home_lat=home[0],
            home_lon=home[1],
            job_lat=job_lat,
            job_lon=job_lon,
            max_commute_km=None,
            remote=False,
        )
        if decision.source != "google_route_matrix" or decision.distance_km is None:
            self._route_cache[key] = (DISTANCE_UNKNOWN, None)
            self.stats.google_route_unknown += 1
            return DISTANCE_UNKNOWN, None
        pair = (float(decision.distance_km), decision.duration_minutes)
        self._route_cache[key] = pair
        self.stats.google_route_ok += 1
        return pair

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
        """Return (lat, lon, road_distance_km). Unresolved / Google fail → UNKNOWN.

        Never uses Haversine for the returned distance_km.
        """
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
            return None, None, DISTANCE_UNKNOWN
        if not resolution.ok:
            self.stats.unknown_locations += 1
            return None, None, DISTANCE_UNKNOWN
        lat, lon = float(resolution.latitude), float(resolution.longitude)  # type: ignore[arg-type]
        if home is None:
            return lat, lon, DISTANCE_UNKNOWN
        dist_km, _dur = self._road_commute(home, lat, lon)
        return lat, lon, dist_km

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
        """Return (lat, lon, road_km, duration_minutes). Google-only."""
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
        if not resolution.ok or home is None:
            if resolution.status == "AMBIGUOUS":
                self.stats.ambiguous_locations += 1
            else:
                self.stats.unknown_locations += 1
            return None, None, DISTANCE_UNKNOWN, None
        lat, lon = float(resolution.latitude), float(resolution.longitude)  # type: ignore[arg-type]
        dist_km, dur = self._road_commute(home, lat, lon)
        return lat, lon, dist_km, dur


def _country_suffix(country_code: str, cross_border: bool) -> str:
    del cross_border
    cc = normalize_country_code(country_code) or "DE"
    names = {"DE": "Germany", "AT": "Austria", "CH": "Switzerland"}
    return names.get(cc, "Germany")


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
    """Normalize address text for comparing persisted geocode provenance."""
    return " ".join((address or "").strip().lower().split())


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
    """Enrich jobs with Google geocode + road distance. Dedupes identical queries.

    Remote jobs skip workplace geocoding. Unknown / Google failure leave
    distance_km as None (DISTANCE_UNKNOWN). Never writes Haversine as commute.
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
    else:
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
        lat, lon, dist, dur = location.commute_for_job_location(
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
            if dist is not None:
                job.distance_km = dist
                if hasattr(job, "distance_source"):
                    job.distance_source = GEO_DATA_SOURCE_ROUTE
            else:
                job.distance_km = None
                if hasattr(job, "distance_source"):
                    job.distance_source = ""
            if hasattr(job, "commute_duration_minutes"):
                job.commute_duration_minutes = dur
            cc = getattr(job, "country_code", "") or sample_place.country_code
            if cc and hasattr(job, "country_code"):
                job.country_code = cc

    progress(
        f"Standorte fertig: {len(order)}/{total_q} Orte — "
        f"gelöst {location.stats.resolved}, Cache {location.stats.cached}, "
        f"ungeklärt {location.stats.failed}, Remote übersprungen {location.stats.remote_skipped}, "
        f"Route OK {location.stats.google_route_ok}, Route UNKNOWN {location.stats.google_route_unknown}"
        + ("" if home.resolved else " | Distanzfilter inaktiv (Heimat unklar)")
        + (
            " | DACH-Cross-Border an"
            if location.cross_border
            else " | DACH-Cross-Border aus"
        )
    )
    return jobs
