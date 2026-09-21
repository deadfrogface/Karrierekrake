"""Local location enrichment tests (no Google Maps / Nominatim)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from core.config import AppConfig, LocationConfig, SearchPreferences, SettingsConfig
from core.database import Database
from core.geo_dataset import GeoDatasetManager, reset_geo_dataset_manager_for_tests
from core.geo_resolve import HAVERSINE_ALGORITHM, reset_pgeocode_index_for_tests
from core.location import LocationService, enrich_job_locations, location_cache_key
from core.models import RemoteType


@pytest.fixture(autouse=True)
def _geo(tmp_path, monkeypatch):
    reset_geo_dataset_manager_for_tests()
    reset_pgeocode_index_for_tests()
    monkeypatch.setenv("KARRIEREKRAKE_GEO_DATA_DIR", str(tmp_path / "geo_active"))
    GeoDatasetManager(config_root=tmp_path).ensure_active()
    yield
    reset_geo_dataset_manager_for_tests()
    reset_pgeocode_index_for_tests()


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


def _svc(tmp_path: Path) -> LocationService:
    db = Database(tmp_path / "loc.db", recover=False)
    cfg = AppConfig(
        root=tmp_path,
        profile=SearchPreferences(
            location=LocationConfig(
                home_address="10115 Berlin",
                postal_code="10115",
                city="Berlin",
                country="DE",
                max_distance_km=50,
            )
        ),
        settings=SettingsConfig(geocoder="local"),
    )
    return LocationService(db, cfg)


def test_location_cache_key_stable():
    a = location_cache_key(city="Berlin", postal_code="10115", country_code="DE")
    b = location_cache_key(city="Berlin", postal_code="10115", country_code="DE")
    assert a == b
    assert a.startswith("DE|") or "10115" in a


def test_enrich_remote_skips_distance(tmp_path):
    svc = _svc(tmp_path)
    jobs = [_FakeJob(remote_type=RemoteType.REMOTE.value, city="Berlin", postal_code="10117")]
    enrich_job_locations(jobs, svc)
    assert jobs[0].distance_km is None
    assert svc.stats.remote_skipped == 1


def test_enrich_plz_airline(tmp_path):
    svc = _svc(tmp_path)
    jobs = [
        _FakeJob(
            city="Berlin",
            postal_code="10117",
            country_code="DE",
            remote_type=RemoteType.ONSITE.value,
        )
    ]
    enrich_job_locations(jobs, svc)
    assert jobs[0].distance_km is not None
    assert jobs[0].distance_source == HAVERSINE_ALGORITHM
    assert jobs[0].commute_duration_minutes is None


def test_home_unresolved_without_address(tmp_path):
    db = Database(tmp_path / "h.db", recover=False)
    cfg = AppConfig(
        root=tmp_path,
        profile=SearchPreferences(location=LocationConfig(home_address="", country="DE")),
        settings=SettingsConfig(geocoder="local"),
    )
    svc = LocationService(db, cfg)
    home = svc.resolve_home()
    assert not home.resolved
    assert home.coords is None


def test_stale_google_cache_ignored(tmp_path):
    svc = _svc(tmp_path)
    svc.db.set_geocode(
        "de|10117|berlin",
        1.0,
        2.0,
        "fake",
        data_source="google_geocoding",
        data_version="maps-geocoding-v1",
        country_code="DE",
        resolution_status="RESOLVED",
    )
    res = svc.resolve_job_place(
        city="Berlin",
        postal_code="10117",
        country_code="DE",
    )
    # Must re-resolve locally, not trust Google cache coords 1,2
    if res.ok:
        assert not (res.latitude == 1.0 and res.longitude == 2.0)
