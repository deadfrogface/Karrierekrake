"""Minimal authenticated Maps proxy — NOT a general Google API gateway (NEXT-05).

Exposes ONLY:
  POST /v1/geocode          → Geocoding API
  POST /v1/route-matrix     → Routes API Compute Route Matrix Essentials

Rejects arbitrary paths, arbitrary Google URLs, and TRAFFIC_AWARE_OPTIMAL /
advanced waypoint Pro features unless explicitly approved later.

API key lives only in the proxy process environment / keyring — never inside
Karrierekrake.exe as an unrestricted shared web-service credential.
"""

from __future__ import annotations

import json
import logging
import os
import secrets
import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

import httpx

from integrations.maps.contracts import MapsCostEvent, MapsError
from integrations.maps.metering import (
    METRIC_GEOCODING,
    METRIC_ROUTE_MATRIX,
    MapsCostMeter,
    get_cost_meter,
)

logger = logging.getLogger("karrierekrake.maps.proxy")

GEOCODING_URL = "https://maps.googleapis.com/maps/api/geocode/json"
ROUTE_MATRIX_URL = "https://routes.googleapis.com/distanceMatrix/v2:computeRouteMatrix"

# Essentials field mask — no traffic duration / Pro extras.
ROUTE_MATRIX_FIELD_MASK = (
    "originIndex,destinationIndex,status,condition,"
    "distanceMeters,duration"
)

ALLOWED_PATHS = frozenset({"/v1/geocode", "/v1/route-matrix", "/v1/health"})


def _env_api_key() -> str:
    return (
        os.environ.get("KARRIEREKRAKE_GOOGLE_MAPS_API_KEY", "").strip()
        or os.environ.get("GOOGLE_MAPS_API_KEY", "").strip()
    )


def _env_proxy_token() -> str:
    return os.environ.get("KARRIEREKRAKE_MAPS_PROXY_TOKEN", "").strip()


@dataclass
class ProxyConfig:
    host: str = "127.0.0.1"
    port: int = 8765
    api_key: str = ""
    auth_token: str = ""
    timeout_s: float = 12.0


class MapsProxyBackend:
    """Callable Google backends used by the proxy handler (injectable in tests)."""

    def __init__(
        self,
        *,
        api_key: str,
        timeout_s: float = 12.0,
        meter: MapsCostMeter | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.api_key = api_key
        self.timeout_s = timeout_s
        self.meter = meter or get_cost_meter()
        self._client = http_client

    def geocode(self, address: str, *, region: str = "de", run_id: str = "") -> dict[str, Any]:
        if not self.api_key:
            raise MapsError("NO_API_KEY", "Maps API key not configured on proxy")
        fp = self.meter.fingerprint("geocode", address.lower().strip(), region)
        if self.meter.already_spent(fp):
            # Idempotent: still return by re-calling Google would double-bill —
            # callers should cache; here we refuse duplicate network spend.
            raise MapsError("DUPLICATE_REQUEST", "geocode fingerprint already spent this process")
        self.meter.check_allowed(METRIC_GEOCODING, run_id=run_id, count=1)
        self.meter.rate_limit_wait()
        params = {
            "address": address,
            "key": self.api_key,
            "region": region,
            "language": "de",
        }
        try:
            if self._client is not None:
                resp = self._client.get(GEOCODING_URL, params=params)
            else:
                with httpx.Client(timeout=self.timeout_s) as client:
                    resp = client.get(GEOCODING_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
        except MapsError:
            raise
        except Exception as exc:
            self.meter.record(
                MapsCostEvent(
                    metric=METRIC_GEOCODING,
                    count=1,
                    run_id=run_id,
                    request_fingerprint="",  # allow limited retry — not marked spent
                    ok=False,
                )
            )
            raise MapsError("GEOCODE_HTTP", str(exc)[:120]) from exc

        status = str(data.get("status") or "")
        ok = status == "OK"
        results = data.get("results") or []
        if not ok or not results:
            self.meter.record(
                MapsCostEvent(
                    metric=METRIC_GEOCODING,
                    count=1,
                    run_id=run_id,
                    request_fingerprint=fp if ok else "",
                    ok=False,
                )
            )
            raise MapsError("GEOCODE_STATUS", status or "EMPTY")
        self.meter.record(
            MapsCostEvent(
                metric=METRIC_GEOCODING,
                count=1,
                run_id=run_id,
                request_fingerprint=fp,
                ok=True,
            )
        )
        top = results[0]
        loc = (top.get("geometry") or {}).get("location") or {}
        cc = ""
        for comp in top.get("address_components") or []:
            types = comp.get("types") or []
            if "country" in types:
                cc = str(comp.get("short_name") or "").upper()
                break
        return {
            "latitude": float(loc["lat"]),
            "longitude": float(loc["lng"]),
            "formatted_address": str(top.get("formatted_address") or ""),
            "place_id": str(top.get("place_id") or ""),
            "country_code": cc,
            "data_source": "google_geocoding",
            "data_version": "maps-geocoding-v1",
        }

    def route_matrix(
        self,
        *,
        origin_lat: float,
        origin_lon: float,
        dest_lat: float,
        dest_lon: float,
        run_id: str = "",
    ) -> dict[str, Any]:
        if not self.api_key:
            raise MapsError("NO_API_KEY", "Maps API key not configured on proxy")
        fp = self.meter.fingerprint(
            "matrix",
            f"{origin_lat:.5f}",
            f"{origin_lon:.5f}",
            f"{dest_lat:.5f}",
            f"{dest_lon:.5f}",
        )
        if self.meter.already_spent(fp):
            raise MapsError("DUPLICATE_REQUEST", "route-matrix fingerprint already spent")
        self.meter.check_allowed(METRIC_ROUTE_MATRIX, run_id=run_id, count=1)
        self.meter.rate_limit_wait()

        body = {
            "origins": [
                {
                    "waypoint": {
                        "location": {
                            "latLng": {"latitude": origin_lat, "longitude": origin_lon}
                        }
                    }
                }
            ],
            "destinations": [
                {
                    "waypoint": {
                        "location": {
                            "latLng": {"latitude": dest_lat, "longitude": dest_lon}
                        }
                    }
                }
            ],
            "travelMode": "DRIVE",
            # Essentials — never TRAFFIC_AWARE_OPTIMAL without cost approval.
            "routingPreference": "TRAFFIC_UNAWARE",
        }
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self.api_key,
            "X-Goog-FieldMask": ROUTE_MATRIX_FIELD_MASK,
        }
        try:
            if self._client is not None:
                resp = self._client.post(ROUTE_MATRIX_URL, json=body, headers=headers)
            else:
                with httpx.Client(timeout=self.timeout_s) as client:
                    resp = client.post(ROUTE_MATRIX_URL, json=body, headers=headers)
            resp.raise_for_status()
            payload = resp.json()
        except MapsError:
            raise
        except Exception as exc:
            self.meter.record(
                MapsCostEvent(
                    metric=METRIC_ROUTE_MATRIX,
                    count=1,
                    run_id=run_id,
                    request_fingerprint="",
                    ok=False,
                )
            )
            raise MapsError("MATRIX_HTTP", str(exc)[:120]) from exc

        # API returns a JSON array of elements.
        elements = payload if isinstance(payload, list) else payload.get("elements") or []
        if not elements:
            self.meter.record(
                MapsCostEvent(
                    metric=METRIC_ROUTE_MATRIX,
                    count=1,
                    run_id=run_id,
                    request_fingerprint="",
                    ok=False,
                )
            )
            raise MapsError("MATRIX_EMPTY", "no elements")
        el = elements[0]
        self.meter.record(
            MapsCostEvent(
                metric=METRIC_ROUTE_MATRIX,
                count=1,
                run_id=run_id,
                request_fingerprint=fp,
                ok=True,
            )
        )
        status_obj = el.get("status") or {}
        status_code = (
            status_obj.get("code")
            if isinstance(status_obj, dict)
            else status_obj
        ) or el.get("condition") or "OK"
        if str(status_code) not in {"OK", "ROUTE_EXISTS", "0"}:
            # condition ROUTE_EXISTS is success; others → unknown
            cond = str(el.get("condition") or "")
            if cond not in {"ROUTE_EXISTS", ""}:
                raise MapsError("MATRIX_STATUS", str(status_code))
        distance_m = int(el.get("distanceMeters") or 0)
        dur_raw = el.get("duration") or "0s"
        if isinstance(dur_raw, str) and dur_raw.endswith("s"):
            duration_s = int(float(dur_raw[:-1]))
        else:
            duration_s = int(dur_raw or 0)
        if distance_m <= 0 and duration_s <= 0:
            raise MapsError("MATRIX_ZERO", "zero distance")
        return {
            "distance_meters": distance_m,
            "duration_seconds": duration_s,
            "status": "OK",
            "routing_preference": "TRAFFIC_UNAWARE",
            "data_source": "google_route_matrix",
            "data_version": "routes-matrix-essentials-v1",
        }


def _make_handler(
    backend: MapsProxyBackend,
    auth_token: str,
) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A003
            logger.debug("maps_proxy " + fmt, *args)

        def _auth_ok(self) -> bool:
            if not auth_token:
                return False
            hdr = self.headers.get("Authorization", "")
            if hdr.startswith("Bearer "):
                return secrets.compare_digest(hdr[7:].strip(), auth_token)
            return secrets.compare_digest(
                self.headers.get("X-Karrierekrake-Maps-Token", "").strip(),
                auth_token,
            )

        def _read_json(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b"{}"
            try:
                data = json.loads(raw.decode("utf-8") or "{}")
            except json.JSONDecodeError as exc:
                raise MapsError("BAD_JSON", str(exc)) from exc
            if not isinstance(data, dict):
                raise MapsError("BAD_JSON", "body must be object")
            return data

        def _send(self, code: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path not in ALLOWED_PATHS:
                self._send(404, {"error": "NOT_FOUND", "message": "path not allowed"})
                return
            if path == "/v1/health":
                self._send(200, {"ok": True, "service": "karrierekrake-maps-proxy"})
                return
            self._send(405, {"error": "METHOD_NOT_ALLOWED"})

        def do_POST(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path not in ALLOWED_PATHS:
                self._send(404, {"error": "NOT_FOUND", "message": "path not allowed"})
                return
            if path == "/v1/health":
                self._send(200, {"ok": True})
                return
            if not self._auth_ok():
                self._send(401, {"error": "UNAUTHORIZED"})
                return
            try:
                data = self._read_json()
                if path == "/v1/geocode":
                    address = str(data.get("address") or "").strip()
                    if not address:
                        raise MapsError("BAD_REQUEST", "address required")
                    # Reject attempts to smuggle arbitrary Google URLs.
                    if "googleapis.com" in address.lower() or address.startswith("http"):
                        raise MapsError("FORBIDDEN", "arbitrary URL proxying denied")
                    result = backend.geocode(
                        address,
                        region=str(data.get("region") or "de"),
                        run_id=str(data.get("run_id") or ""),
                    )
                    self._send(200, result)
                    return
                if path == "/v1/route-matrix":
                    # Hard reject Pro / traffic SKUs from client.
                    pref = str(data.get("routing_preference") or "TRAFFIC_UNAWARE")
                    if pref != "TRAFFIC_UNAWARE":
                        raise MapsError(
                            "SKU_FORBIDDEN",
                            "only TRAFFIC_UNAWARE Essentials allowed",
                        )
                    if data.get("intermediates") or data.get("waypoints"):
                        raise MapsError("FEATURE_FORBIDDEN", "waypoints not allowed")
                    result = backend.route_matrix(
                        origin_lat=float(data["origin_lat"]),
                        origin_lon=float(data["origin_lon"]),
                        dest_lat=float(data["dest_lat"]),
                        dest_lon=float(data["dest_lon"]),
                        run_id=str(data.get("run_id") or ""),
                    )
                    self._send(200, result)
                    return
                self._send(404, {"error": "NOT_FOUND"})
            except MapsError as exc:
                self._send(400, {"error": exc.code, "message": str(exc)})
            except KeyError as exc:
                self._send(400, {"error": "BAD_REQUEST", "message": f"missing {exc}"})
            except Exception as exc:
                logger.exception("maps proxy internal error")
                self._send(500, {"error": "INTERNAL", "message": str(exc)[:80]})

    return Handler


class MapsProxyServer:
    """Threading HTTP server for the minimal Maps proxy."""

    def __init__(self, config: ProxyConfig | None = None, backend: MapsProxyBackend | None = None) -> None:
        cfg = config or ProxyConfig()
        if not cfg.api_key:
            cfg.api_key = _env_api_key()
        if not cfg.auth_token:
            cfg.auth_token = _env_proxy_token() or secrets.token_urlsafe(24)
        self.config = cfg
        self.backend = backend or MapsProxyBackend(
            api_key=cfg.api_key, timeout_s=cfg.timeout_s
        )
        handler = _make_handler(self.backend, cfg.auth_token)
        self._httpd = ThreadingHTTPServer((cfg.host, cfg.port), handler)
        self._thread: threading.Thread | None = None

    @property
    def base_url(self) -> str:
        host, port = self._httpd.server_address[:2]
        return f"http://{host}:{port}"

    @property
    def auth_token(self) -> str:
        return self.config.auth_token

    def start(self, *, background: bool = True) -> str:
        if background:
            self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
            self._thread.start()
        else:
            self._httpd.serve_forever()
        return self.base_url

    def stop(self) -> None:
        self._httpd.shutdown()
        if self._thread:
            self._thread.join(timeout=2.0)


def run_proxy_main() -> None:
    """CLI entry: ``python -m integrations.maps.proxy``."""
    logging.basicConfig(level=logging.INFO)
    cfg = ProxyConfig(
        host=os.environ.get("KARRIEREKRAKE_MAPS_PROXY_HOST", "127.0.0.1"),
        port=int(os.environ.get("KARRIEREKRAKE_MAPS_PROXY_PORT", "8765")),
        api_key=_env_api_key(),
        auth_token=_env_proxy_token() or secrets.token_urlsafe(24),
    )
    if not cfg.api_key:
        raise SystemExit("Set KARRIEREKRAKE_GOOGLE_MAPS_API_KEY for the proxy process")
    server = MapsProxyServer(cfg)
    print(f"Karrierekrake Maps proxy on {server.base_url}")
    print(f"Auth token (set KARRIEREKRAKE_MAPS_PROXY_TOKEN on desktop): {server.auth_token}")
    print("Endpoints: POST /v1/geocode  POST /v1/route-matrix  GET /v1/health")
    try:
        server.start(background=False)
    except KeyboardInterrupt:
        server.stop()


if __name__ == "__main__":
    run_proxy_main()
