"""Regression tests for Google geocode / location enrichment (NEXT-05).

No live Google / Nominatim. Inject MapsGeoService with a fake client.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import pytest

from core.config import AppConfig, LocationConfig, SearchPreferences
from core.database import Database
from core.location import (
    UNRESOLVED_MARKER,
    LocationService,
    enrich_job_locations,
    location_cache_key,
)
from core.models import Job, RemoteType
from integrations.maps.contracts import GeocodeResult, MapsError, RouteMatrixResult
from integrations.maps.metering import reset_cost_meter_for_tests
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
    country_code: str = ""


class _FakeMaps:
    def __init__(self) -> None:
        self.geocode_calls = 0
        self.matrix_calls = 0
        self.fail = False
        self.empty = False
        self.lat = 53.1
        self.lon = 8.8
        self.road_m = 5000
        self.road_s = 600

    def geocode(self, address: str, *, region: str = "de", run_id: str = "") -> GeocodeResult:
        self.geocode_calls += 1
        if self.fail:
            raise MapsError("FAIL", "forced")
        if self.empty:
            raise MapsError("MISS", "empty")
        return GeocodeResult(
            latitude=self.lat,
            longitude=self.lon,
            formatted_address=address,
            country_code="DE",
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
        self.matrix_calls += 1
        if self.fail:
            raise MapsError("FAIL", "forced")
        return RouteMatrixResult(
            distance_meters=self.road_m,
            duration_seconds=self.road_s,
        )


def _svc(
    tmp_path,
    fake: _FakeMaps | None = None,
    *,
    home_address: str = "Bremen, Germany",
    pin_home: bool = True,
) -> tuple[LocationService, _FakeMaps]:
    reset_maps_service_for_tests()
    reset_cost_meter_for_tests()
    fake = fake or _FakeMaps()
    db = Database(tmp_path / "t.db")
    cfg = AppConfig(
        profile=SearchPreferences(
            location=LocationConfig(home_address=home_address, max_distance_km=20)
        )
    )
    if pin_home:
        cfg.profile.location.home_latitude = 53.0793
        cfg.profile.location.home_longitude = 8.8017
        cfg.profile.location.home_geocoded_address = home_address
    maps = MapsGeoService(client=fake)  # type: ignore[arg-type]
    return LocationService(db, cfg, timeout_s=0.5, maps=maps), fake


def test_geocode_failure_does_not_block(tmp_path):
    svc, fake = _svc(tmp_path)
    fake.fail = True
    t0 = time.time()
    assert svc.geocode("Unknownville XX") is None
    assert time.time() - t0 < 2.0
    # Negative cache: second call must not hit network again
    before = fake.geocode_calls
    assert svc.geocode("Unknownville XX") is None
    assert fake.geocode_calls == before
    cached = svc.db.get_geocode("Unknownville XX")
    assert cached is not None
    assert cached[2] == UNRESOLVED_MARKER


def test_repeated_location_uses_cache(tmp_path):
    svc, fake = _svc(tmp_path)
    assert svc.geocode("Bremen, Germany") is not None
    assert svc.geocode("Bremen, Germany") is not None
    assert fake.geocode_calls == 1


def test_ensure_home_coords_only_once_on_failure(tmp_path):
    fake = _FakeMaps()
    fake.empty = True
    svc, fake = _svc(
        tmp_path,
        fake,
        home_address="Nowhere Street 1, Nirgendsheim",
        pin_home=False,
    )
    h1 = svc.ensure_home_coords()
    h2 = svc.ensure_home_coords()
    assert h1 is None
    assert h2 is None
    assert not svc.home_resolved
    assert "Distanzfilter" in svc.home_warning or "geocodiert" in svc.home_warning
    first_calls = fake.geocode_calls
    assert first_calls <= 3
    for _ in range(50):
        svc.ensure_home_coords()
    assert fake.geocode_calls == first_calls
    assert svc._home is None


def test_home_failure_does_not_distort_distance(tmp_path):
    fake = _FakeMaps()
    fake.empty = True
    svc, _ = _svc(
        tmp_path,
        fake,
        home_address="Nowhere Street 1, 00000 Nirgends",
        pin_home=False,
    )
    jobs = [_FakeJob(city="Berlin"), _FakeJob(city="Hamburg")]
    enrich_job_locations(jobs, svc)
    assert all(j.distance_km is None for j in jobs)
    assert svc.stats.skipped_distance_no_home is True
    assert not svc.home_resolved


def test_remote_job_skips_geocode(tmp_path):
    svc, fake = _svc(tmp_path)
    jobs = [_FakeJob(city="Berlin", remote_type=RemoteType.REMOTE.value)]
    enrich_job_locations(jobs, svc)
    assert fake.geocode_calls == 0
    assert fake.matrix_calls == 0
    assert jobs[0].distance_km is None
    assert svc.stats.remote_skipped == 1


def test_unresolved_location_continues(tmp_path):
    svc, fake = _svc(tmp_path)
    fake.empty = True
    jobs = [
        _FakeJob(city="NowhereXYZ"),
        _FakeJob(city="AlsoNowhere"),
    ]
    enrich_job_locations(jobs, svc)
    assert all(j.distance_km is None for j in jobs)
    assert svc.stats.failed >= 1


def test_enrich_dedupes_identical_cities(tmp_path):
    svc, fake = _svc(tmp_path)
    jobs = [_FakeJob(city="Berlin") for _ in range(10)]
    msgs: list[str] = []
    enrich_job_locations(jobs, svc, progress_callback=msgs.append)
    # One geocode for the group + route matrix once
    assert fake.geocode_calls == 1
    assert fake.matrix_calls == 1
    assert svc.stats.unique_queries == 1
    assert any("Standorte anreichern:" in m for m in msgs)
    assert all(j.distance_km is not None for j in jobs)
    assert all(j.distance_source == "google_route_matrix" for j in jobs)


def test_cancelled_enrich_stops(tmp_path):
    svc, _fake = _svc(tmp_path)
    stop = {"n": 0}
    jobs = [_FakeJob(city=f"City{i}") for i in range(20)]

    def should_stop():
        stop["n"] += 1
        return stop["n"] > 3

    enrich_job_locations(jobs, svc, should_stop=should_stop)
    assert sum(1 for j in jobs if j.distance_km is not None) < 20


def test_location_cache_key_stable():
    assert location_cache_key(city="Berlin") == location_cache_key(city="Berlin")
    assert location_cache_key(latitude=1.0, longitude=2.0).startswith("ll:")


def test_clean_db_starts_at_zero(tmp_path):
    db = Database(tmp_path / "empty.db")
    stats = db.dashboard_stats()
    assert stats["total_jobs"] == 0
    assert stats["jobs_found_today"] == 0
    assert stats["this_run"] == 0
    assert stats["needs_review"] == 0


def test_clear_job_data_and_run_id(tmp_path):
    db = Database(tmp_path / "jobs.db")
    run = db.start_search_run()
    job = Job(id="j1", source="test", source_job_id="1", title="T", company="C", run_id=run)
    db.upsert_job(job)
    db.set_source_status("indeed", "ok", "", 1)
    assert db.dashboard_stats(run_id=run)["this_run"] == 1
    assert db.dashboard_stats()["total_jobs"] == 1
    cleared = db.clear_job_data()
    assert cleared["jobs"] == 1
    assert db.dashboard_stats()["total_jobs"] == 0
    assert db.latest_run_id() is None


def test_resolve_home_invalidates_stale_persisted_coords(tmp_path):
    """Persisted lat/lon must not win when home_address text no longer matches."""
    fake = _FakeMaps()
    fake.lat = 53.55
    fake.lon = 9.99
    reset_maps_service_for_tests()
    reset_cost_meter_for_tests()
    db = Database(tmp_path / "t.db")
    cfg = AppConfig(
        profile=SearchPreferences(
            location=LocationConfig(
                home_address="Neue Straße 9, 20095 Hamburg",
                max_distance_km=20,
                home_latitude=52.52,
                home_longitude=13.40,
                home_geocoded_address="Alte Straße 1, 10115 Berlin",
            )
        )
    )
    maps = MapsGeoService(client=fake)  # type: ignore[arg-type]
    svc = LocationService(db, cfg, timeout_s=0.5, maps=maps)
    res = svc.resolve_home()
    assert res.resolved
    assert res.source == "google_geocoding"
    assert res.coords is not None
    assert abs(res.coords[0] - 53.55) < 0.01
    assert abs(res.coords[1] - 9.99) < 0.01
    assert cfg.profile.location.home_latitude == res.coords[0]
    assert cfg.profile.location.home_longitude == res.coords[1]
    assert svc.home_updated is True
    assert fake.geocode_calls >= 1


def test_google_fail_leaves_distance_unknown_not_haversine(tmp_path):
    svc, fake = _svc(tmp_path)
    fake.fail = True  # matrix + geocode fail after coords path
    # Use explicit coords so only matrix is needed — force matrix fail only
    fake.fail = False

    class _BoomMatrix(_FakeMaps):
        def route_matrix(self, **kwargs):
            self.matrix_calls += 1
            raise MapsError("MATRIX_FAIL", "forced")

    boom = _BoomMatrix()
    svc, _ = _svc(tmp_path, boom)
    lat, lon, dist = svc.distance_for_job_location(
        latitude=53.08, longitude=8.81, city="Near"
    )
    assert lat is not None
    assert dist is None
