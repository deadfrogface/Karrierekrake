"""Desktop client for the minimal Maps proxy (NEXT-05).

Karrierekrake.exe never holds unrestricted Google Routes/Geocoding keys.
It only talks to the authenticated proxy with the exact two operations needed.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from integrations.maps.contracts import (
    GeocodeResult,
    MapsError,
    RouteMatrixResult,
)

logger = logging.getLogger("karrierekrake.maps.client")


def proxy_base_url() -> str:
    return (
        os.environ.get("KARRIEREKRAKE_MAPS_PROXY_URL", "").strip()
        or "http://127.0.0.1:8765"
    )


def proxy_auth_token() -> str:
    return os.environ.get("KARRIEREKRAKE_MAPS_PROXY_TOKEN", "").strip()


class MapsProxyClient:
    """Thin HTTP client — only /v1/geocode and /v1/route-matrix."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        auth_token: str | None = None,
        timeout_s: float = 15.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = (base_url or proxy_base_url()).rstrip("/")
        self.auth_token = auth_token if auth_token is not None else proxy_auth_token()
        self.timeout_s = timeout_s
        self._transport = transport

    def _headers(self) -> dict[str, str]:
        hdrs = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.auth_token:
            hdrs["Authorization"] = f"Bearer {self.auth_token}"
            hdrs["X-Karrierekrake-Maps-Token"] = self.auth_token
        return hdrs

    def _client(self) -> httpx.Client:
        kwargs: dict[str, Any] = {"timeout": self.timeout_s}
        if self._transport is not None:
            kwargs["transport"] = self._transport
        return httpx.Client(**kwargs)

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        if path not in {"/v1/geocode", "/v1/route-matrix"}:
            raise MapsError("FORBIDDEN", "client may only call geocode/route-matrix")
        url = f"{self.base_url}{path}"
        try:
            with self._client() as client:
                resp = client.post(url, json=payload, headers=self._headers())
        except httpx.HTTPError as exc:
            raise MapsError("PROXY_UNAVAILABLE", str(exc)[:120]) from exc
        try:
            data = resp.json()
        except Exception:
            data = {}
        if resp.status_code == 401:
            raise MapsError("PROXY_UNAUTHORIZED", "maps proxy auth failed")
        if resp.status_code >= 400:
            err = data.get("error") if isinstance(data, dict) else None
            msg = data.get("message") if isinstance(data, dict) else resp.text[:80]
            raise MapsError(str(err or "PROXY_ERROR"), str(msg or resp.status_code))
        if not isinstance(data, dict):
            raise MapsError("PROXY_BAD_RESPONSE", "expected object")
        return data

    def geocode(
        self,
        address: str,
        *,
        region: str = "de",
        run_id: str = "",
    ) -> GeocodeResult:
        data = self._post(
            "/v1/geocode",
            {"address": address, "region": region, "run_id": run_id},
        )
        return GeocodeResult(
            latitude=float(data["latitude"]),
            longitude=float(data["longitude"]),
            formatted_address=str(data.get("formatted_address") or ""),
            place_id=str(data.get("place_id") or ""),
            country_code=str(data.get("country_code") or ""),
            data_source=str(data.get("data_source") or "google_geocoding"),
            data_version=str(data.get("data_version") or "maps-geocoding-v1"),
        )

    def route_matrix(
        self,
        *,
        origin_lat: float,
        origin_lon: float,
        dest_lat: float,
        dest_lon: float,
        run_id: str = "",
    ) -> RouteMatrixResult:
        data = self._post(
            "/v1/route-matrix",
            {
                "origin_lat": origin_lat,
                "origin_lon": origin_lon,
                "dest_lat": dest_lat,
                "dest_lon": dest_lon,
                "run_id": run_id,
                "routing_preference": "TRAFFIC_UNAWARE",
            },
        )
        return RouteMatrixResult(
            distance_meters=int(data["distance_meters"]),
            duration_seconds=int(data["duration_seconds"]),
            status=str(data.get("status") or "OK"),
            routing_preference="TRAFFIC_UNAWARE",
            data_source=str(data.get("data_source") or "google_route_matrix"),
            data_version=str(data.get("data_version") or "routes-matrix-essentials-v1"),
        )

    def health(self) -> bool:
        try:
            with self._client() as client:
                resp = client.get(f"{self.base_url}/v1/health", timeout=3.0)
            return resp.status_code == 200
        except Exception:
            return False
