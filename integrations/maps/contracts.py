"""Normalized contracts for Google Maps geo (NEXT-05).

No addresses in cost / audit payloads — only opaque hashes and counters.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

# Sentinel: never invent a float distance when Google fails.
DISTANCE_UNKNOWN: None = None

TravelMode = Literal["DRIVE"]
RoutingPreference = Literal["TRAFFIC_UNAWARE"]  # Essentials — no Pro SKU default


class MapsError(RuntimeError):
    """Google Maps / proxy failure. Callers must treat distance as UNKNOWN."""

    def __init__(self, code: str, message: str = "") -> None:
        self.code = code
        super().__init__(message or code)


@dataclass(frozen=True)
class GeocodeResult:
    latitude: float
    longitude: float
    formatted_address: str = ""
    place_id: str = ""
    country_code: str = ""
    data_source: str = "google_geocoding"
    data_version: str = "maps-geocoding-v1"

    @property
    def ok(self) -> bool:
        return True


@dataclass(frozen=True)
class RouteMatrixResult:
    """One origin→destination element from Compute Route Matrix Essentials."""

    distance_meters: int
    duration_seconds: int
    status: str = "OK"
    # Essentials / TRAFFIC_UNAWARE — never TRAFFIC_AWARE_OPTIMAL by default.
    routing_preference: RoutingPreference = "TRAFFIC_UNAWARE"
    data_source: str = "google_route_matrix"
    data_version: str = "routes-matrix-essentials-v1"

    @property
    def distance_km(self) -> float:
        return round(self.distance_meters / 1000.0, 2)

    @property
    def duration_minutes(self) -> float:
        return round(self.duration_seconds / 60.0, 1)

    @property
    def ok(self) -> bool:
        return self.status == "OK" and self.distance_meters >= 0


@dataclass(frozen=True)
class CommuteDecision:
    """Final radius decision from road route only."""

    distance_km: float | None
    duration_minutes: float | None
    within_radius: bool | None  # None = UNKNOWN (soft path)
    source: str = ""
    reason: str = ""

    def ui_distance_label(self, *, lang: str = "de") -> str:
        """User-facing label. Never claim 'Fahrt' without a Google route."""
        if self.distance_km is None or self.source != "google_route_matrix":
            return "—" if lang == "de" else "—"
        km = f"{self.distance_km:.0f}" if self.distance_km == int(self.distance_km) else f"{self.distance_km:.1f}"
        if lang == "en":
            return f"{km} km drive"
        return f"{km} km Fahrt"

    def ui_duration_label(self, *, lang: str = "de") -> str:
        if self.duration_minutes is None or self.source != "google_route_matrix":
            return ""
        mins = int(round(self.duration_minutes))
        if lang == "en":
            return f"approx. {mins} min"
        return f"ca. {mins} Min."

    def ui_combined(self, *, lang: str = "de") -> str:
        dist = self.ui_distance_label(lang=lang)
        dur = self.ui_duration_label(lang=lang)
        if dist == "—":
            return dist
        if dur:
            return f"{dist}\n{dur}" if lang == "de" else f"{dist}\n{dur}"
        return dist


@dataclass
class MapsCostEvent:
    """Metering event — never includes addresses or place text."""

    metric: str  # google.geocoding.requests | google.route_matrix.elements
    count: int = 1
    run_id: str = ""
    request_fingerprint: str = ""  # hash only
    ok: bool = True
    extra: dict[str, Any] = field(default_factory=dict)
