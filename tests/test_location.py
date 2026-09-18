"""Regression tests for geocode / location enrichment (no live Nominatim)."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import pytest

from core.config import AppConfig, LocationConfig, ProfileConfig, SearchPreferences
from core.database import Database
from core.location import (
    UNRESOLVED_MARKER,
    LocationService,
    enrich_job_locations,
    location_cache_key,
)
from core.models import Job, RemoteType


@dataclass
class _FakeJob:
    address: str = ""
    city: str = ""
    postal_code: str = ""
    latitude: float | None = None
    longitude: float | None = None
    distance_km: float | None = None
    remote_type: str = RemoteType.ONSITE.value


def _svc(tmp_path, monkeypatch, home_address: str = "Bremen, Germany") -> LocationService:
    db = Database(tmp_path / "t.db")
    cfg = AppConfig(
        profile=SearchPreferences(
            location=LocationConfig(home_address=home_address, max_distance_km=20)
        )
    )
    # Pin home so tests never need live geocode for home
    cfg.profile.location.home_latitude = 53.0793
    cfg.profile.location.home_longitude = 8.8017
    return LocationService(db, cfg, timeout_s=0.5)


def test_geocode_timeout_does_not_block(monkeypatch, tmp_path):
    svc = _svc(tmp_path, monkeypatch)

    def boom(*_a, **_k):
        raise TimeoutError("simulated")

    monkeypatch.setattr("httpx.Client.get", boom)
    # LocationService creates Client context — patch Client.__enter__ path via get on instance
    class _Client:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, *a, **k):
            raise TimeoutError("simulated")

    monkeypatch.setattr("httpx.Client", _Client)
    t0 = time.time()
    assert svc.geocode("Unknownville XX") is None
    assert time.time() - t0 < 2.0
    # Negative cache: second call must not hit network again
    calls = {"n": 0}

    class _Client2(_Client):
        def get(self, *a, **k):
            calls["n"] += 1
            raise AssertionError("should use cache")

    monkeypatch.setattr("httpx.Client", _Client2)
    assert svc.geocode("Unknownville XX") is None
    assert calls["n"] == 0
    cached = svc.db.get_geocode("Unknownville XX")
    assert cached is not None
    assert cached[2] == UNRESOLVED_MARKER


def test_repeated_location_uses_cache(monkeypatch, tmp_path):
    svc = _svc(tmp_path, monkeypatch)
    calls = {"n": 0}

    class _Client:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, *a, **k):
            calls["n"] += 1
            class _Resp:
                def raise_for_status(self):
                    return None

                def json(self):
                    return [{"lat": "53.1", "lon": "8.8", "display_name": "Bremen"}]

            return _Resp()

    monkeypatch.setattr("httpx.Client", _Client)
    assert svc.geocode("Bremen, Germany") is not None
    assert svc.geocode("Bremen, Germany") is not None
    assert calls["n"] == 1


def test_ensure_home_coords_only_once_on_failure(monkeypatch, tmp_path):
    db = Database(tmp_path / "t.db")
    # No valid DACH PLZ → offline pgeocode cannot rescue; Nominatim empty.
    cfg = AppConfig(
        profile=SearchPreferences(
            location=LocationConfig(home_address="Nowhere Street 1, Nirgendsheim")
        )
    )
    svc = LocationService(db, cfg, timeout_s=0.5)
    calls = {"n": 0}

    class _Client:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, *a, **k):
            calls["n"] += 1

            class _Resp:
                def raise_for_status(self):
                    return None

                def json(self):
                    return []

            return _Resp()

    monkeypatch.setattr("httpx.Client", _Client)
    h1 = svc.ensure_home_coords()
    h2 = svc.ensure_home_coords()
    assert h1 is None
    assert h2 is None
    assert not svc.home_resolved
    assert "Distanzfilter" in svc.home_warning or "geocodiert" in svc.home_warning
    # First failure may try address + city fallback (=2), never again per job
    assert calls["n"] <= 3
    # Simulate many jobs calling ensure_home_coords
    for _ in range(50):
        svc.ensure_home_coords()
    assert calls["n"] <= 3
    # Must never invent Germany-center fallback coordinates
    assert svc._home is None


def test_home_failure_does_not_distort_distance(monkeypatch, tmp_path):
    db = Database(tmp_path / "t.db")
    cfg = AppConfig(
        profile=SearchPreferences(
            location=LocationConfig(home_address="Nowhere Street 1, 00000 Nirgends")
        )
    )
    svc = LocationService(db, cfg, timeout_s=0.5)

    class _Client:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, *a, **k):
            class _Resp:
                def raise_for_status(self):
                    return None

                def json(self):
                    return []

            return _Resp()

    monkeypatch.setattr("httpx.Client", _Client)
    jobs = [_FakeJob(city="Berlin"), _FakeJob(city="Hamburg")]
    enrich_job_locations(jobs, svc)
    assert all(j.distance_km is None for j in jobs)
    assert svc.stats.skipped_distance_no_home is True
    assert not svc.home_resolved


def test_remote_job_skips_geocode(monkeypatch, tmp_path):
    svc = _svc(tmp_path, monkeypatch)
    calls = {"n": 0}

    class _Client:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, *a, **k):
            calls["n"] += 1
            raise AssertionError("remote must not geocode")

    monkeypatch.setattr("httpx.Client", _Client)
    jobs = [_FakeJob(city="Berlin", remote_type=RemoteType.REMOTE.value)]
    enrich_job_locations(jobs, svc)
    assert calls["n"] == 0
    assert jobs[0].distance_km is None
    assert svc.stats.remote_skipped == 1


def test_unresolved_location_continues(monkeypatch, tmp_path):
    svc = _svc(tmp_path, monkeypatch)

    class _Client:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, *a, **k):
            class _Resp:
                def raise_for_status(self):
                    return None

                def json(self):
                    return []

            return _Resp()

    monkeypatch.setattr("httpx.Client", _Client)
    jobs = [
        _FakeJob(city="NowhereXYZ"),
        _FakeJob(city="AlsoNowhere"),
    ]
    enrich_job_locations(jobs, svc)
    assert all(j.distance_km is None for j in jobs)
    assert svc.stats.failed >= 1


def test_enrich_dedupes_identical_cities(monkeypatch, tmp_path):
    svc = _svc(tmp_path, monkeypatch)
    calls = {"n": 0}

    class _Client:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, *a, **k):
            calls["n"] += 1

            class _Resp:
                def raise_for_status(self):
                    return None

                def json(self):
                    return [{"lat": "52.52", "lon": "13.40", "display_name": "Berlin"}]

            return _Resp()

    monkeypatch.setattr("httpx.Client", _Client)
    jobs = [_FakeJob(city="Berlin") for _ in range(10)]
    msgs: list[str] = []
    enrich_job_locations(jobs, svc, progress_callback=msgs.append)
    assert calls["n"] == 1
    assert svc.stats.unique_queries == 1
    assert any("Standorte anreichern:" in m for m in msgs)
    assert all(j.distance_km is not None for j in jobs)


def test_cancelled_enrich_stops(monkeypatch, tmp_path):
    svc = _svc(tmp_path, monkeypatch)
    stop = {"n": 0}

    class _Client:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, *a, **k):
            class _Resp:
                def raise_for_status(self):
                    return None

                def json(self):
                    return [{"lat": "52.0", "lon": "10.0", "display_name": "X"}]

            return _Resp()

    monkeypatch.setattr("httpx.Client", _Client)
    jobs = [_FakeJob(city=f"City{i}") for i in range(20)]

    def should_stop():
        stop["n"] += 1
        return stop["n"] > 3

    enrich_job_locations(jobs, svc, should_stop=should_stop)
    # Not all unique cities processed
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


def test_resolve_home_invalidates_stale_persisted_coords(monkeypatch, tmp_path):
    """Persisted lat/lon must not win when home_address text no longer matches."""
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
    svc = LocationService(db, cfg, timeout_s=0.5)
    calls = {"n": 0}

    class _Client:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, *a, **k):
            calls["n"] += 1

            class _Resp:
                def raise_for_status(self):
                    return None

                def json(self):
                    return [{"lat": "53.55", "lon": "9.99", "display_name": "Hamburg"}]

            return _Resp()

    monkeypatch.setattr("httpx.Client", _Client)
    res = svc.resolve_home()
    assert res.resolved
    # Offline pgeocode may resolve PLZ 20095 before Nominatim — both OK.
    assert res.source in {"geocode", "pgeocode", "nominatim"}
    assert res.coords is not None
    assert abs(res.coords[0] - 53.55) < 1.0  # Hamburg area
    assert abs(res.coords[1] - 9.99) < 1.5
    assert cfg.profile.location.home_latitude == res.coords[0]
    assert cfg.profile.location.home_longitude == res.coords[1]
    assert "Hamburg" in cfg.profile.location.home_geocoded_address or "Neue" in (
        cfg.profile.location.home_geocoded_address or ""
    )
    assert svc.home_updated is True
    # Network only required when offline path cannot resolve
    if res.source in {"geocode", "nominatim"}:
        assert calls["n"] >= 1
