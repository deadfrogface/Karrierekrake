"""Geocoding cache and Haversine distance helpers (DACH cross-border aware).

Commute radius is mathematical (Haversine), not national. DE/AT/CH borders are
not distance barriers. Unresolvable places stay UNKNOWN — never invent km.

Nominatim calls are rate-limited, timed out, negatively cached, and must never
block a search run indefinitely. Prefer offline pgeocode for PLZ when possible.

Home coordinates are resolved **once per LocationService instance / run**.
Failed home resolution must NOT silently use arbitrary Germany center coordinates
for distance filtering — that distorts commute filters.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable

import httpx

from core.geo_normalize import (
    DACH_COUNTRY_CODES,
    normalize_country_code,
    normalize_place_fields,
)
from core.geo_resolve import (
    GEO_DATA_SOURCE_NOMINATIM,
    GEO_DATA_SOURCE_UNRESOLVED,
    GEO_DATA_VERSION_NOMINATIM,
    GEO_DATA_VERSION_UNRESOLVED,
    PlaceResolution,
    UNRESOLVED_MARKER,
    cache_query_key,
    distance_km_or_unknown,
    haversine_km,
    place_from_job_like,
    resolve_place,
)

if TYPE_CHECKING:
    from core.config import AppConfig
    from core.database import Database

logger = logging.getLogger("karrierekrake")

# Re-export for existing imports / tests
__all__ = [
    "UNRESOLVED_MARKER",
    "HomeResolution",
    "EnrichStats",
    "LocationService",
    "haversine_km",
    "location_cache_key",
    "enrich_job_locations",
    "cross_border_dach_enabled",
]

DEFAULT_GEOCODE_TIMEOUT_S = 5.0
MIN_REQUEST_INTERVAL_S = 1.05
# Negative-cache TTL for unresolved lookups (seconds). Successes stay until cleared.
UNRESOLVED_TTL_S = 6 * 60 * 60
# Soft cap on unique geocode network attempts per enrich run (cached hits free).
MAX_UNIQUE_GEOCODE_ATTEMPTS_PER_RUN = 80


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
    source: str = ""  # persisted | geocode | unresolved | pgeocode
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
    # Legacy fallback (pre-country keys)
    if latitude is not None and longitude is not None:
        return f"ll:{latitude:.5f},{longitude:.5f}"
    parts = [p.strip().lower() for p in (address, postal_code, city) if p and str(p).strip()]
    if not parts:
        return ""
    return "|".join(parts)


@dataclass
class LocationService:
    """Geocode once, cache in SQLite (incl. misses), compute Haversine locally."""

    db: "Database"
    config: "AppConfig"
    timeout_s: float = DEFAULT_GEOCODE_TIMEOUT_S
    _home: tuple[float, float] | None = field(default=None, init=False, repr=False)
    _home_resolution: HomeResolution | None = field(default=None, init=False, repr=False)
    _last_request: float = field(default=0.0, init=False, repr=False)
    _memory_hits: dict[str, tuple[float, float, str] | None] = field(
        default_factory=dict, init=False, repr=False
    )
    _network_attempts: int = field(default=0, init=False, repr=False)
    home_updated: bool = field(default=False, init=False, repr=False)
    stats: EnrichStats = field(default_factory=EnrichStats, init=False)

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

    def resolve_home(self) -> HomeResolution:
        """Resolve home once. Never uses a silent Germany-center fallback for filtering."""
        if self._home_resolution is not None:
            return self._home_resolution

        loc = self.config.profile.location
        address = (loc.home_address or "").strip()
        current_fp = _address_fingerprint(address)
        stored_fp = _address_fingerprint(getattr(loc, "home_geocoded_address", "") or "")
        home_cc = self.home_country()

        if loc.home_latitude is not None and loc.home_longitude is not None:
            # Persisted coords are only trusted when they still match the address text.
            # Cleared / whitespace-only address must drop stale lat/lon.
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
                # Legacy YAML: bind fingerprint so later address edits invalidate.
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

        place = normalize_place_fields(
            address=address,
            country_code=home_cc,
            city=_city_from_address(address),
        )
        # Try offline PLZ first when address contains a postal code
        resolved = resolve_place(
            place,
            cross_border=self.cross_border,
            home_country=home_cc,
            allow_network=True,
            network_geocode=self._network_geocode_resolution,
        )
        if not resolved.ok:
            # Legacy path: full-string geocode + city fallback (DACH-aware)
            coords_t = self.geocode(address, country_codes=self._nominatim_countries())
            if not coords_t:
                cityish = _city_from_address(address)
                if cityish and cityish.lower() != address.lower():
                    suffix = _country_suffix(home_cc, self.cross_border)
                    coords_t = self.geocode(
                        f"{cityish}, {suffix}",
                        country_codes=self._nominatim_countries(),
                    )
            if coords_t:
                resolved = PlaceResolution(
                    status="RESOLVED",
                    latitude=coords_t[0],
                    longitude=coords_t[1],
                    country_code=home_cc,
                    display_name=coords_t[2],
                    data_source=GEO_DATA_SOURCE_NOMINATIM,
                    data_version=GEO_DATA_VERSION_NOMINATIM,
                )

        if not resolved.ok:
            warning = (
                f"Heimatadresse konnte nicht geocodiert werden: {address!r}. "
                "Distanzfilter übersprungen — bitte Adresse korrigieren (kein generischer DE-Fallback)."
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

        coords = (float(resolved.latitude), float(resolved.longitude))  # type: ignore[arg-type]
        self._home = coords
        loc.home_latitude = coords[0]
        loc.home_longitude = coords[1]
        loc.home_geocoded_address = address
        self.home_updated = True
        self._home_resolution = HomeResolution(
            coords=coords,
            resolved=True,
            source=resolved.data_source or "geocode",
            address_used=address,
            country_code=resolved.country_code or home_cc,
        )
        self.stats.home_resolved = True
        return self._home_resolution

    def ensure_home_coords(self) -> tuple[float, float] | None:
        """Resolve home once; return coords or None if unresolved (no DE fallback)."""
        res = self.resolve_home()
        return res.coords

    def _nominatim_countries(self) -> list[str]:
        if self.cross_border:
            return sorted(DACH_COUNTRY_CODES)
        return [self.home_country()]

    def _network_geocode_resolution(
        self, query: str, countries: list[str]
    ) -> PlaceResolution | None:
        result = self.geocode(query, country_codes=countries or self._nominatim_countries())
        if not result:
            return None
        lat, lon, display = result
        cc = ""
        if countries and len(countries) == 1:
            cc = countries[0]
        return PlaceResolution(
            status="RESOLVED",
            latitude=lat,
            longitude=lon,
            country_code=cc,
            display_name=display,
            data_source=GEO_DATA_SOURCE_NOMINATIM,
            data_version=GEO_DATA_VERSION_NOMINATIM,
        )

    def geocode(
        self,
        query: str,
        *,
        country_codes: list[str] | None = None,
    ) -> tuple[float, float, str] | None:
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
                # TTL expired — allow one retry
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

        codes = country_codes or self._nominatim_countries()
        countrycodes = ",".join(c.lower() for c in codes if c)

        elapsed = time.time() - self._last_request
        if elapsed < MIN_REQUEST_INTERVAL_S:
            time.sleep(MIN_REQUEST_INTERVAL_S - elapsed)

        self._network_attempts += 1
        try:
            with httpx.Client(timeout=self.timeout_s) as client:
                params: dict = {
                    "q": query,
                    "format": "json",
                    "limit": 1,
                }
                if countrycodes:
                    params["countrycodes"] = countrycodes
                resp = client.get(
                    "https://nominatim.openstreetmap.org/search",
                    params=params,
                    headers={"User-Agent": "Karrierekrake/1.0 (local personal use)"},
                )
                resp.raise_for_status()
                data = resp.json()
            self._last_request = time.time()
            if not data:
                self._store_unresolved(query)
                self.stats.failed += 1
                return None
            lat = float(data[0]["lat"])
            lon = float(data[0]["lon"])
            display = data[0].get("display_name", "") or ""
            self.db.set_geocode(
                query,
                lat,
                lon,
                display,
                data_source=GEO_DATA_SOURCE_NOMINATIM,
                data_version=GEO_DATA_VERSION_NOMINATIM,
            )
            result = (lat, lon, display)
            self._memory_hits[key] = result
            self.stats.resolved += 1
            return result
        except Exception as exc:
            logger.warning("Geocode failed for %r: %s", query, exc)
            self._store_unresolved(query)
            self.stats.failed += 1
            return None

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
        """Resolve a job workplace. Cross-border when toggle enabled."""
        place = normalize_place_fields(
            address=address,
            city=city,
            postal_code=postal_code,
            latitude=latitude,
            longitude=longitude,
            country_code=country_code,
            remote_type=remote_type,
        )
        return resolve_place(
            place,
            cross_border=self.cross_border,
            home_country=self.home_country(),
            allow_network=True,
            network_geocode=self._network_geocode_resolution,
        )

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
        """Return (lat, lon, distance_km). Unresolved → UNKNOWN distance (None)."""
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
            return None, None, None
        if not resolution.ok:
            self.stats.unknown_locations += 1
            # Legacy fallback: try Germany-suffixed queries only when cross-border off
            # and still no coords — keep UNKNOWN rather than inventing distance.
            if home is None:
                return None, None, None
            # Attempt one legacy city/plz geocode for backward compat when fields sparse
            if not any([address, city, postal_code]) and latitude is None:
                return None, None, None
            if latitude is not None and longitude is not None:
                dist = round(haversine_km(home[0], home[1], latitude, longitude), 2)
                return latitude, longitude, dist
            suffix = _country_suffix(self.home_country(), self.cross_border)
            query_parts = [p for p in (address, postal_code, city, suffix) if p]
            query = ", ".join(query_parts) if any([address, city, postal_code]) else ""
            if not query:
                return None, None, None
            result = self.geocode(query, country_codes=self._nominatim_countries())
            if not result and city:
                result = self.geocode(
                    f"{city}, {suffix}",
                    country_codes=self._nominatim_countries(),
                )
            if not result and postal_code:
                result = self.geocode(
                    f"{postal_code}, {suffix}",
                    country_codes=self._nominatim_countries(),
                )
            if not result:
                return None, None, None
            lat, lon, _ = result
            return lat, lon, round(haversine_km(home[0], home[1], lat, lon), 2)

        lat, lon = resolution.latitude, resolution.longitude
        dist = distance_km_or_unknown(home, resolution)
        return lat, lon, dist


def _country_suffix(country_code: str, cross_border: bool) -> str:
    cc = normalize_country_code(country_code) or "DE"
    names = {"DE": "Germany", "AT": "Austria", "CH": "Switzerland"}
    if cross_border:
        return names.get(cc, "Germany")
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
    """Extract a single usable city token from a home address.

    Multi-city strings like "Berlin / Hamburg" or "Berlin, Hamburg und München"
    must NOT be geocoded as one absurd query — take the first concrete city.
    """
    raw = (home_address or "").strip()
    if not raw:
        return ""
    # Prefer first segment when users list alternatives.
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
    """Enrich jobs with coordinates/distance. Dedupes identical location queries.

    Remote jobs skip workplace geocoding. Progress reports unique-query progress.
    Cross-border (DE/AT/CH) uses Haversine only — borders are not barriers.
    Unknown / ambiguous places leave distance_km as None (UNKNOWN).
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
            location.stats.remote_skipped += 1
            continue
        # Lazy-normalize country_code on job when missing (no mass DB mutation).
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
        lat, lon, dist = location.distance_for_job_location(
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
            elif getattr(job, "distance_km", None) is not None and lat is None:
                # Do not keep stale invented distances when resolution failed
                pass
            cc = getattr(job, "country_code", "") or sample_place.country_code
            if cc and hasattr(job, "country_code"):
                job.country_code = cc

    progress(
        f"Standorte fertig: {len(order)}/{total_q} Orte — "
        f"gelöst {location.stats.resolved}, Cache {location.stats.cached}, "
        f"ungeklärt {location.stats.failed}, Remote übersprungen {location.stats.remote_skipped}"
        + ("" if home.resolved else " | Distanzfilter inaktiv (Heimat unklar)")
        + (
            " | DACH-Cross-Border an"
            if location.cross_border
            else " | DACH-Cross-Border aus"
        )
    )
    return jobs
