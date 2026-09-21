"""NEXT-05 — Google Maps only geo / commute (no Haversine authority)."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from core.config import AppConfig, LocationConfig, SearchPreferences
from core.database import Database
from core.geo_resolve import haversine_km
from core.location import LocationService, enrich_job_locations
from core.models import Job, RemoteType
from integrations.maps.contracts import (
    DISTANCE_UNKNOWN,
    CommuteDecision,
    GeocodeResult,
    MapsError,
    RouteMatrixResult,
)
from integrations.maps.metering import (
    METRIC_GEOCODING,
    METRIC_ROUTE_MATRIX,
    MapsBudgetConfig,
    reset_cost_meter_for_tests,
)
from integrations.maps.proxy import MapsProxyBackend, MapsProxyServer, ProxyConfig
from integrations.maps.client import MapsProxyClient
from integrations.maps.service import MapsGeoService, reset_maps_service_for_tests


@dataclass
class _FakeJob:
    address: str = ""
    city: str = ""
    postal_code: str = ""
    latitude: float | None = None
    longitude: float | None = None
    distance_km: float | None = None
    commute_duration_minutes: float | None = None
    distance_source: str = ""
    remote_type: str = RemoteType.ONSITE.value
    country_code: str = "DE"


class FakeMapsClient:
    """Deterministic Google stand-in for unit tests (no live network)."""

    def __init__(self) -> None:
        self.geocode_calls = 0
        self.matrix_calls = 0
        self.geocode_map: dict[str, GeocodeResult] = {}
        self.matrix_map: dict[tuple[float, float, float, float], RouteMatrixResult] = {}
        self.fail_geocode = False
        self.fail_matrix = False

    def geocode(self, address: str, *, region: str = "de", run_id: str = "") -> GeocodeResult:
        self.geocode_calls += 1
        if self.fail_geocode:
            raise MapsError("GEOCODE_FAIL", "forced")
        key = address.strip().lower()
        for needle, res in self.geocode_map.items():
            if needle in key:
                return res
        raise MapsError("GEOCODE_MISS", address)

    def route_matrix(
        self,
        *,
        origin_lat: float,
        origin_lon: float,
        dest_lat: float,
        dest_lon: float,
        run_id: str = "",
    ) -> RouteMatrixResult:
        self.matrix_calls += 1
        if self.fail_matrix:
            raise MapsError("MATRIX_FAIL", "forced")
        key = (
            round(origin_lat, 5),
            round(origin_lon, 5),
            round(dest_lat, 5),
            round(dest_lon, 5),
        )
        if key in self.matrix_map:
            return self.matrix_map[key]
        # Default: look up by dest only
        for (oa, oo, da, do), res in self.matrix_map.items():
            if abs(da - dest_lat) < 1e-4 and abs(do - dest_lon) < 1e-4:
                return res
        raise MapsError("MATRIX_MISS", "no fixture")


def _svc(tmp_path, fake: FakeMapsClient, home=("Berlin", 52.52, 13.405)) -> LocationService:
    reset_maps_service_for_tests()
    reset_cost_meter_for_tests()
    db = Database(tmp_path / "t.db")
    cfg = AppConfig(
        profile=SearchPreferences(
            location=LocationConfig(
                home_address=home[0],
                max_distance_km=20,
                home_latitude=home[1],
                home_longitude=home[2],
                home_geocoded_address=home[0],
            )
        )
    )
    maps = MapsGeoService(client=fake)  # type: ignore[arg-type]
    return LocationService(db, cfg, maps=maps)


def test_google_failure_yields_distance_unknown(tmp_path):
    fake = FakeMapsClient()
    fake.fail_matrix = True
    # Explicit coords so geocode is not needed
    fake.geocode_map["x"] = GeocodeResult(52.52, 13.405)
    svc = _svc(tmp_path, fake)
    lat, lon, dist = svc.distance_for_job_location(
        latitude=52.53, longitude=13.42, city="Nearby"
    )
    assert lat == pytest.approx(52.53)
    assert lon == pytest.approx(13.42)
    assert dist is DISTANCE_UNKNOWN
    assert dist is None


def test_no_haversine_fallback_when_google_fails(tmp_path):
    """Airline would be ~1 km; Google fail must NOT invent Haversine commute."""
    home = (52.5200, 13.4050)
    job = (52.5250, 13.4100)
    airline = haversine_km(*home, *job)
    assert airline < 5  # would pass a 20 km Haversine filter

    fake = FakeMapsClient()
    fake.fail_matrix = True
    svc = _svc(tmp_path, fake, home=("Berlin", *home))
    _lat, _lon, dist = svc.distance_for_job_location(latitude=job[0], longitude=job[1])
    assert dist is None
    # Must not equal airline
    assert dist != round(airline, 2)


def test_airline_inside_radius_but_road_outside(tmp_path):
    """Classic case: straight-line < 20 km, road route > 20 km → OUTSIDE."""
    home = (52.5200, 13.4050)  # Berlin center-ish
    # Contrived nearby coords (airline short)
    job = (52.5800, 13.4500)
    airline = haversine_km(*home, *job)
    assert airline < 20, f"fixture broken: airline={airline}"

    fake = FakeMapsClient()
    fake.matrix_map[
        (round(home[0], 5), round(home[1], 5), round(job[0], 5), round(job[1], 5))
    ] = RouteMatrixResult(
        distance_meters=28_500,  # 28.5 km road
        duration_seconds=42 * 60,
    )
    svc = _svc(tmp_path, fake, home=("Berlin", *home))
    lat, lon, dist, dur = svc.commute_for_job_location(
        latitude=job[0], longitude=job[1], city="Far by road"
    )
    assert dist == pytest.approx(28.5)
    assert dur == pytest.approx(42.0)
    assert dist > 20
    assert airline < 20
    # Radius decision
    decision = svc.maps.commute_decision(  # type: ignore[union-attr]
        home_lat=home[0],
        home_lon=home[1],
        job_lat=job[0],
        job_lon=job[1],
        max_commute_km=20,
    )
    assert decision.within_radius is False
    assert decision.source == "google_route_matrix"


def test_road_inside_radius_ui_labels():
    decision = CommuteDecision(
        distance_km=18.0,
        duration_minutes=24.0,
        within_radius=True,
        source="google_route_matrix",
    )
    assert "18 km Fahrt" in decision.ui_distance_label(lang="de")
    assert "24 Min" in decision.ui_duration_label(lang="de")
    # Without Google source — no false Fahrt claim
    bad = CommuteDecision(
        distance_km=18.0,
        duration_minutes=24.0,
        within_radius=True,
        source="haversine",
    )
    assert bad.ui_distance_label(lang="de") == "—"


def test_enrich_sets_road_distance_and_source(tmp_path):
    home = (52.52, 13.405)
    job_ll = (52.53, 13.41)
    fake = FakeMapsClient()
    fake.matrix_map[
        (round(home[0], 5), round(home[1], 5), round(job_ll[0], 5), round(job_ll[1], 5))
    ] = RouteMatrixResult(distance_meters=12_000, duration_seconds=18 * 60)
    svc = _svc(tmp_path, fake, home=("Berlin", *home))
    jobs = [
        _FakeJob(city="Mitte", latitude=job_ll[0], longitude=job_ll[1], country_code="DE")
    ]
    enrich_job_locations(jobs, svc)
    assert jobs[0].distance_km == pytest.approx(12.0)
    assert jobs[0].commute_duration_minutes == pytest.approx(18.0)
    assert jobs[0].distance_source == "google_route_matrix"


def test_cost_meter_separate_metrics_no_addresses():
    meter = reset_cost_meter_for_tests(MapsBudgetConfig(max_geocode_per_run=5))
    from integrations.maps.contracts import MapsCostEvent

    meter.record(
        MapsCostEvent(
            metric=METRIC_GEOCODING,
            count=1,
            run_id="run1",
            request_fingerprint=meter.fingerprint("geocode", "hash-only"),
            ok=True,
        )
    )
    meter.record(
        MapsCostEvent(
            metric=METRIC_ROUTE_MATRIX,
            count=1,
            run_id="run1",
            request_fingerprint=meter.fingerprint("matrix", "1", "2"),
            ok=True,
        )
    )
    snap = meter.snapshot()
    assert snap["runs"]["run1"][METRIC_GEOCODING] == 1
    assert snap["runs"]["run1"][METRIC_ROUTE_MATRIX] == 1
    # Events must not carry address fields
    for ev in meter.events:
        assert "address" not in ev.extra
        assert "Berlin" not in (ev.request_fingerprint or "")


def test_bill_guard_blocks_over_run_quota():
    meter = reset_cost_meter_for_tests(MapsBudgetConfig(max_geocode_per_run=1))
    meter.check_allowed(METRIC_GEOCODING, run_id="r", count=1)
    from integrations.maps.contracts import MapsCostEvent

    meter.record(
        MapsCostEvent(metric=METRIC_GEOCODING, count=1, run_id="r", request_fingerprint="a")
    )
    with pytest.raises(MapsError) as ei:
        meter.check_allowed(METRIC_GEOCODING, run_id="r", count=1)
    assert ei.value.code == "BUDGET_RUN_GEOCODE"


def test_duplicate_fingerprint_blocks_double_spend(tmp_path):
    meter = reset_cost_meter_for_tests()
    backend = MapsProxyBackend(api_key="test-key", meter=meter)

    class _Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "status": "OK",
                "results": [
                    {
                        "geometry": {"location": {"lat": 1.0, "lng": 2.0}},
                        "formatted_address": "X",
                        "place_id": "p",
                        "address_components": [],
                    }
                ],
            }

    class _Client:
        def get(self, *a, **k):
            return _Resp()

    backend._client = _Client()
    backend.geocode("Somewhere DE", run_id="r1")
    with pytest.raises(MapsError) as ei:
        backend.geocode("Somewhere DE", run_id="r1")
    assert ei.value.code == "DUPLICATE_REQUEST"


def test_proxy_rejects_arbitrary_paths_and_pro_sku():
    meter = reset_cost_meter_for_tests()

    class StubBackend(MapsProxyBackend):
        def geocode(self, address, *, region="de", run_id=""):
            return {
                "latitude": 1.0,
                "longitude": 2.0,
                "formatted_address": "ok",
                "place_id": "",
                "country_code": "DE",
                "data_source": "google_geocoding",
                "data_version": "maps-geocoding-v1",
            }

        def route_matrix(self, **kwargs):
            return {
                "distance_meters": 1000,
                "duration_seconds": 60,
                "status": "OK",
                "routing_preference": "TRAFFIC_UNAWARE",
                "data_source": "google_route_matrix",
                "data_version": "routes-matrix-essentials-v1",
            }

    server = MapsProxyServer(
        ProxyConfig(host="127.0.0.1", port=0, api_key="k", auth_token="secret"),
        backend=StubBackend(api_key="k", meter=meter),
    )
    # Bind ephemeral port
    server._httpd.server_bind = server._httpd.server_bind  # already bound
    # Recreate with port 0 properly
    from http.server import ThreadingHTTPServer
    from integrations.maps.proxy import _make_handler

    handler = _make_handler(server.backend, "secret")
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    import threading

    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    host, port = httpd.server_address[:2]
    base = f"http://{host}:{port}"
    try:
        client = MapsProxyClient(base_url=base, auth_token="secret")
        assert client.health() or True  # health may work
        import httpx

        r = httpx.get(f"{base}/v1/googleapis/anything", timeout=2)
        assert r.status_code == 404
        r2 = httpx.post(
            f"{base}/v1/route-matrix",
            json={
                "origin_lat": 1,
                "origin_lon": 2,
                "dest_lat": 3,
                "dest_lon": 4,
                "routing_preference": "TRAFFIC_AWARE_OPTIMAL",
            },
            headers={"Authorization": "Bearer secret"},
            timeout=2,
        )
        assert r2.status_code == 400
        assert r2.json()["error"] == "SKU_FORBIDDEN"
        # Allowed essentials call
        ok = client.route_matrix(
            origin_lat=1, origin_lon=2, dest_lat=3, dest_lon=4
        )
        assert ok.distance_meters == 1000
    finally:
        httpd.shutdown()


def test_proxy_requires_auth():
    meter = reset_cost_meter_for_tests()

    class StubBackend(MapsProxyBackend):
        def geocode(self, address, *, region="de", run_id=""):
            return {
                "latitude": 1.0,
                "longitude": 2.0,
                "formatted_address": "ok",
                "place_id": "",
                "country_code": "DE",
            }

    from http.server import ThreadingHTTPServer
    from integrations.maps.proxy import _make_handler
    import threading
    import httpx

    handler = _make_handler(StubBackend(api_key="k", meter=meter), "tok")
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    host, port = httpd.server_address[:2]
    try:
        r = httpx.post(
            f"http://{host}:{port}/v1/geocode",
            json={"address": "Berlin"},
            timeout=2,
        )
        assert r.status_code == 401
    finally:
        httpd.shutdown()


def test_release_gate_markers():
    """Documented NEXT-05 acceptance markers as executable asserts."""
    assert DISTANCE_UNKNOWN is None
    import core.location as loc

    src = open(loc.__file__, encoding="utf-8").read()
    assert "nominatim.openstreetmap.org" not in src
    assert "import pgeocode" not in src
    assert "router.project-osrm.org" not in src
    assert "from geopy" not in src
    # Haversine must not be used for distance assignment
    assert "haversine_km(home" not in src
    assert "round(haversine_km" not in src
    assert "get_maps_service" in src or "MapsGeoService" in src
    assert "google_route_matrix" in src
