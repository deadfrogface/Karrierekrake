"""Local geocoding cache and Haversine airline distance (local-first).

Production authority: bundled/updated GeoNames DACH postal data + haversine_v1.
No Google Maps / Places / Routes / Distance Matrix.
No public Nominatim.

On resolution failure → DISTANCE_UNKNOWN (None). Never invent km.
max_commute_km means airline (Luftlinie) ≤ N km.

Home coordinates are resolved once per LocationService instance / run.
Failed home resolution must NOT silently use arbitrary Germany center coordinates.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable

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
    place_from_job_like,
    resolve_place,
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
        """Resolve home once locally. Never uses a silent DE-center fallback."""
        if self._home_resolution is not None:
            return self._home_resolution

        loc = self.config.profile.location
        address = (loc.home_address or "").strip()
        postal = getattr(loc, "postal_code", "") or ""
        city = getattr(loc, "city", "") or ""
        current_fp = _address_fingerprint(address or f"{postal}|{city}")
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
                loc.home_geocoded_address = address or current_fp
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

        place = normalize_place_fields(
            address=address,
            city=city or _city_from_address(address),
            postal_code=postal or _plz_from_address(address),
            country_code=home_cc,
        )
        if not place.postal_code and not place.city and not address:
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
            return self._home_resolution

        resolution = resolve_place(
            place,
            cross_border=self.cross_border,
            home_country=home_cc,
            allow_network=False,
        )
        if not resolution.ok:
            warning = (
                f"Heimatstandort konnte lokal nicht aufgelöst werden "
                f"(PLZ/Ort): {address or place.city or place.postal_code!r}. "
                "Distanzfilter übersprungen — bitte PLZ und Land prüfen."
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
            if dist is not None:
                job.distance_km = dist
                if hasattr(job, "distance_source"):
                    job.distance_source = HAVERSINE_ALGORITHM
            else:
                job.distance_km = None
                if hasattr(job, "distance_source"):
                    job.distance_source = ""
            if hasattr(job, "commute_duration_minutes"):
                job.commute_duration_minutes = None
            cc = getattr(job, "country_code", "") or sample_place.country_code
            if cc and hasattr(job, "country_code"):
                job.country_code = cc

    location.stats.google_route_ok = location.stats.airline_ok
    location.stats.google_route_unknown = location.stats.airline_unknown
    progress(
        f"Standorte fertig: {len(order)}/{total_q} Orte — "
        f"gelöst {location.stats.resolved}, Cache {location.stats.cached}, "
        f"ungeklärt {location.stats.failed}, Remote übersprungen {location.stats.remote_skipped}, "
        f"Luftlinie OK {location.stats.airline_ok}, UNKNOWN {location.stats.airline_unknown}"
        + ("" if home.resolved else " | Distanzfilter inaktiv (Heimat unklar)")
    )
    return jobs
