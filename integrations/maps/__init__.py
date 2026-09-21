"""Google Maps Platform — sole production geo / commute provider (NEXT-05).

Authoritative:
  - Geocoding API (via minimal authenticated proxy)
  - Routes API Compute Route Matrix Essentials

Forbidden as production distance authority:
  - Haversine / airline
  - Nominatim / OpenStreetMap
  - pgeocode
  - OSRM / geopy network

On Google failure → DISTANCE_UNKNOWN (never invent km).
"""

from __future__ import annotations

from integrations.maps.contracts import (
    DISTANCE_UNKNOWN,
    CommuteDecision,
    GeocodeResult,
    MapsError,
    RouteMatrixResult,
)
from integrations.maps.service import MapsGeoService, get_maps_service

__all__ = [
    "DISTANCE_UNKNOWN",
    "CommuteDecision",
    "GeocodeResult",
    "MapsError",
    "MapsGeoService",
    "RouteMatrixResult",
    "get_maps_service",
]
