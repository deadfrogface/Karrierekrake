"""High-level Google-only geo / commute service (NEXT-05).

Flow:
  Home → Google geocode → Job location Google geocode
  → Compute Route Matrix Essentials → road km + duration → radius decision

Failure anywhere → DISTANCE_UNKNOWN (never Haversine / Nominatim / pgeocode).
"""

from __future__ import annotations

import logging
import threading
from typing import Callable

from integrations.maps.client import MapsProxyClient
from integrations.maps.contracts import (
    DISTANCE_UNKNOWN,
    CommuteDecision,
    GeocodeResult,
    MapsError,
    RouteMatrixResult,
)
from integrations.maps.metering import MapsCostMeter, get_cost_meter

logger = logging.getLogger("karrierekrake.maps")

_service_lock = threading.Lock()
_service_singleton: "MapsGeoService | None" = None


class MapsGeoService:
    """Authoritative production geo provider — Google Maps Platform only."""

    def __init__(
        self,
        client: MapsProxyClient | None = None,
        meter: MapsCostMeter | None = None,
        *,
        run_id: str = "",
    ) -> None:
        self.client = client or MapsProxyClient()
        self.meter = meter or get_cost_meter()
        self.run_id = run_id
        self._geocode_mem: dict[str, GeocodeResult | None] = {}
        self._route_mem: dict[str, RouteMatrixResult | None] = {}

    def set_run_id(self, run_id: str) -> None:
        self.run_id = run_id or ""
        if run_id:
            self.meter.reset_run(run_id)

    def geocode(self, address: str, *, region: str = "de") -> GeocodeResult | None:
        """Google Geocoding via proxy. Miss/failure → None (UNKNOWN)."""
        key = f"{region}|{(address or '').strip().lower()}"
        if not (address or "").strip():
            return None
        if key in self._geocode_mem:
            return self._geocode_mem[key]
        try:
            result = self.client.geocode(
                address.strip(), region=region, run_id=self.run_id
            )
            self._geocode_mem[key] = result
            return result
        except MapsError as exc:
            logger.warning("Google geocode failed (%s): %s", exc.code, exc)
            self._geocode_mem[key] = None
            return None
        except Exception as exc:
            logger.warning("Google geocode unexpected failure: %s", exc)
            self._geocode_mem[key] = None
            return None

    def route_matrix(
        self,
        *,
        origin_lat: float,
        origin_lon: float,
        dest_lat: float,
        dest_lon: float,
    ) -> RouteMatrixResult | None:
        """Road route via Compute Route Matrix Essentials. Failure → None."""
        key = (
            f"{origin_lat:.5f},{origin_lon:.5f}|"
            f"{dest_lat:.5f},{dest_lon:.5f}"
        )
        if key in self._route_mem:
            return self._route_mem[key]
        try:
            result = self.client.route_matrix(
                origin_lat=origin_lat,
                origin_lon=origin_lon,
                dest_lat=dest_lat,
                dest_lon=dest_lon,
                run_id=self.run_id,
            )
            if not result.ok:
                self._route_mem[key] = None
                return None
            self._route_mem[key] = result
            return result
        except MapsError as exc:
            logger.warning("Google route matrix failed (%s): %s", exc.code, exc)
            self._route_mem[key] = None
            return None
        except Exception as exc:
            logger.warning("Google route matrix unexpected failure: %s", exc)
            self._route_mem[key] = None
            return None

    def commute_decision(
        self,
        *,
        home_lat: float,
        home_lon: float,
        job_lat: float,
        job_lon: float,
        max_commute_km: float | None,
        remote: bool = False,
    ) -> CommuteDecision:
        """Road-distance radius decision. Airline math is never authoritative."""
        if remote:
            return CommuteDecision(
                distance_km=DISTANCE_UNKNOWN,
                duration_minutes=None,
                within_radius=True,
                source="remote",
                reason="remote_no_workplace",
            )
        route = self.route_matrix(
            origin_lat=home_lat,
            origin_lon=home_lon,
            dest_lat=job_lat,
            dest_lon=job_lon,
        )
        if route is None:
            return CommuteDecision(
                distance_km=DISTANCE_UNKNOWN,
                duration_minutes=None,
                within_radius=None,
                source="",
                reason="google_route_unavailable",
            )
        km = route.distance_km
        mins = route.duration_minutes
        if max_commute_km is None:
            within: bool | None = True
        else:
            within = km <= float(max_commute_km)
        return CommuteDecision(
            distance_km=km,
            duration_minutes=mins,
            within_radius=within,
            source="google_route_matrix",
            reason="ok",
        )

    def resolve_commute_for_addresses(
        self,
        *,
        home_address: str,
        job_address: str,
        max_commute_km: float | None,
        region: str = "de",
        remote: bool = False,
    ) -> CommuteDecision:
        """Full Home→geocode→Job→geocode→matrix→decision pipeline."""
        if remote:
            return self.commute_decision(
                home_lat=0.0,
                home_lon=0.0,
                job_lat=0.0,
                job_lon=0.0,
                max_commute_km=max_commute_km,
                remote=True,
            )
        home = self.geocode(home_address, region=region)
        if home is None:
            return CommuteDecision(
                distance_km=DISTANCE_UNKNOWN,
                duration_minutes=None,
                within_radius=None,
                source="",
                reason="home_geocode_failed",
            )
        job = self.geocode(job_address, region=region)
        if job is None:
            return CommuteDecision(
                distance_km=DISTANCE_UNKNOWN,
                duration_minutes=None,
                within_radius=None,
                source="",
                reason="job_geocode_failed",
            )
        return self.commute_decision(
            home_lat=home.latitude,
            home_lon=home.longitude,
            job_lat=job.latitude,
            job_lon=job.longitude,
            max_commute_km=max_commute_km,
            remote=False,
        )


def get_maps_service(
    *,
    factory: Callable[[], MapsGeoService] | None = None,
) -> MapsGeoService:
    global _service_singleton
    with _service_lock:
        if factory is not None:
            _service_singleton = factory()
            return _service_singleton
        if _service_singleton is None:
            _service_singleton = MapsGeoService()
        return _service_singleton


def reset_maps_service_for_tests() -> None:
    global _service_singleton
    with _service_lock:
        _service_singleton = None
