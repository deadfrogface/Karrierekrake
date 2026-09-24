"""Local-first geo / no-Maps regression + pipeline order tests."""

from __future__ import annotations

import math
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from core.geo_dataset import (
    EARTH_RADIUS_KM,
    HAVERSINE_ALGORITHM,
    GeoDatasetManager,
    bundled_geo_dir,
    get_geo_dataset_manager,
    reset_geo_dataset_manager_for_tests,
    validate_dataset,
)
from core.geo_normalize import normalize_postal_code, normalize_place_fields
from core.geo_resolve import (
    haversine_km,
    format_airline_km,
    resolve_city_pgeocode,
    resolve_postal_pgeocode,
    resolve_place,
    within_radius,
    reset_pgeocode_index_for_tests,
)
from core.hard_filter import distance_exclude, hard_exclude
from core.location import LocationService, enrich_job_locations
from core.matcher import apply_distance_scoring, score_job
from core.models import Job, JobStatus, RemoteType


@pytest.fixture(autouse=True)
def _geo_env(tmp_path, monkeypatch):
    reset_geo_dataset_manager_for_tests()
    reset_pgeocode_index_for_tests()
    # Use bundled snapshot via a writable active dir under tmp
    active = tmp_path / "geo_active"
    monkeypatch.setenv("KARRIEREKRAKE_GEO_DATA_DIR", str(active))
    mgr = GeoDatasetManager(config_root=tmp_path)
    info = mgr.ensure_active()
    assert info.valid, info.message
    yield
    reset_geo_dataset_manager_for_tests()
    reset_pgeocode_index_for_tests()


def test_no_maps_runtime_dependency():
    import importlib
    import sys

    assert "integrations.maps" not in sys.modules
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("integrations.maps")
    root = Path(__file__).resolve().parents[1]
    url_forbidden = (
        "maps.googleapis.com",
        "routes.googleapis.com",
        "places.googleapis.com",
    )
    for path in (root / "core").rglob("*.py"):
        if path.name == "database.py":
            continue
        text = path.read_text(encoding="utf-8")
        for token in url_forbidden:
            assert token not in text, f"{path} contains {token}"
        for token in ("GOOGLE_MAPS_API_KEY", "MAPS_API_KEY"):
            assert token not in text, f"{path} contains {token}"
    for path in (root / "integrations").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for token in url_forbidden:
            assert token not in text, f"{path} contains {token}"
    req = (root / "requirements-runtime.txt").read_text(encoding="utf-8")
    assert "googlemaps" not in req
    assert "DELETE FROM app_meta" in (root / "core" / "database.py").read_text(encoding="utf-8")


def test_no_nominatim_public_url_in_runtime():
    root = Path(__file__).resolve().parents[1]
    bad = "nominatim.openstreetmap.org"
    for folder in ("core", "integrations", "desktop", "app"):
        for path in (root / folder).rglob("*.py"):
            assert bad not in path.read_text(encoding="utf-8"), path


def test_bundled_dach_dataset_valid():
    path = bundled_geo_dir()
    ok, msg = validate_dataset(path)
    assert ok, msg


def test_validate_accepts_crlf_country_files(tmp_path):
    """Windows autocrlf must not break manifest SHA-256 checks."""
    import shutil

    from core.geo_dataset import _normalize_geonames_files

    src = bundled_geo_dir()
    dst = tmp_path / "geo"
    shutil.copytree(src, dst)
    de = dst / "geonames" / "DE.txt"
    de.write_bytes(de.read_bytes().replace(b"\n", b"\r\n"))
    ok, msg = validate_dataset(dst)
    assert ok, msg
    _normalize_geonames_files(dst)
    assert b"\r\n" not in (dst / "geonames" / "DE.txt").read_bytes()
    ok2, msg2 = validate_dataset(dst)
    assert ok2, msg2


def test_plz_leading_zero_de():
    assert normalize_postal_code("01234", country_code="DE") == "01234"
    res = resolve_postal_pgeocode("01067", "DE")  # Dresden area
    assert res.ok
    assert res.precision == "postal_centroid"


def test_at_ch_plz_and_cross_border_haversine():
    at = resolve_postal_pgeocode("6900", "AT")
    ch = resolve_postal_pgeocode("6900", "CH")
    # Same numeric PLZ may resolve in both — different countries
    if at.ok and ch.ok:
        d = haversine_km(at.latitude, at.longitude, ch.latitude, ch.longitude)
        assert d > 1.0  # not the same point guessed across border


def test_haversine_zero_and_reference():
    assert haversine_km(52.52, 13.405, 52.52, 13.405) == pytest.approx(0.0, abs=1e-9)
    # Berlin → roughly known; Konstanz–Kreuzlingen short cross-border
    d = haversine_km(47.6603, 9.1753, 47.6499, 9.1750)
    assert 0.5 < d < 3.0
    assert EARTH_RADIUS_KM == pytest.approx(6371.0088)
    assert HAVERSINE_ALGORITHM == "haversine_v1"


def test_haversine_rejects_invalid():
    with pytest.raises(ValueError):
        haversine_km(float("nan"), 0, 0, 0)
    with pytest.raises(ValueError):
        haversine_km(100, 0, 0, 0)


def test_format_airline_rounds_only_display():
    raw = haversine_km(52.52, 13.405, 52.53, 13.41)
    label = format_airline_km(raw)
    assert "Luftlinie" in label
    assert "Fahrt" not in label
    assert within_radius(raw, raw + 0.001) is True
    assert within_radius(raw, raw - 0.001) is False


def test_ambiguous_city_without_country():
    place = normalize_place_fields(city="Neustadt", country_code="")
    res = resolve_place(place)
    assert res.status in {"AMBIGUOUS", "UNKNOWN"}
    assert not res.ok


def test_large_city_name_resolves_to_city_centroid():
    # Fuzzy top-100 hits for "Berlin" are bulk-recipient PLZ names only.
    res = resolve_city_pgeocode("Berlin", "DE")
    assert res.status == "RESOLVED"
    assert 52.3 < res.latitude < 52.7 and 13.0 < res.longitude < 13.8


def test_homonym_city_names_stay_ambiguous():
    assert resolve_city_pgeocode("Halle", "DE").status == "AMBIGUOUS"
    assert resolve_city_pgeocode("Frankfurt", "DE").status == "AMBIGUOUS"


def test_home_city_with_country_word_resolves(tmp_path):
    from core.config import empty_app_config
    from core.database import Database

    cfg = empty_app_config(root=tmp_path)
    cfg.profile.location.home_address = "Berlin, Deutschland"
    loc = LocationService(Database(tmp_path / "h.db", recover=False), cfg)
    home = loc.resolve_home()
    assert home.resolved, home.warning
    assert not home.warning


def test_unicode_city_de():
    place = normalize_place_fields(city="München", country_code="DE", postal_code="80331")
    res = resolve_place(place)
    assert res.ok


def test_hard_exclude_skips_distance():
    cfg = MagicMock()
    cfg.profile.location.allow_remote_germany = True
    cfg.profile.location.allow_hybrid = True
    cfg.profile.location.max_distance_km = 10
    cfg.profile.jobs.unwanted_titles = []
    cfg.profile.filters.excluded_companies = []
    cfg.profile.filters.exclusion_keywords = []
    cfg.profile.jobs.excluded_industries = []
    cfg.settings.published_within_days = 365
    job = Job(title="Dev", company="ACME", remote_type=RemoteType.ONSITE.value, distance_km=999)
    assert hard_exclude(job, cfg) is None
    assert distance_exclude(job, cfg) is not None


def _minimal_config(tmp_path, *, home_plz="10115", country="DE", radius=50.0):
    from core.config import AppConfig, LocationConfig, SearchPreferences, SettingsConfig
    from core.database import Database

    db = Database(tmp_path / "t.db", recover=False)
    loc = LocationConfig(
        home_address=f"{home_plz} Berlin",
        postal_code=home_plz,
        city="Berlin",
        country=country,
        max_distance_km=radius,
        allow_remote_germany=True,
        allow_hybrid=True,
    )
    cfg = AppConfig(
        root=tmp_path,
        profile=SearchPreferences(location=loc),
        settings=SettingsConfig(geocoder="local", minimum_match_for_auto_apply=50),
    )
    return db, cfg


def test_enrich_sets_airline_source(tmp_path):
    db, cfg = _minimal_config(tmp_path)
    svc = LocationService(db, cfg)
    jobs = [
        Job(
            title="SE",
            company="X",
            city="Berlin",
            postal_code="10117",
            country_code="DE",
            remote_type=RemoteType.ONSITE.value,
        )
    ]
    enrich_job_locations(jobs, svc)
    assert jobs[0].distance_source == HAVERSINE_ALGORITHM
    assert jobs[0].distance_km is not None
    assert jobs[0].commute_duration_minutes is None


def test_remote_skips_radius(tmp_path):
    db, cfg = _minimal_config(tmp_path, radius=5)
    job = Job(title="SE", company="X", remote_type=RemoteType.REMOTE.value)
    assert distance_exclude(job, cfg) is None


def test_unknown_not_zero_km(tmp_path):
    db, cfg = _minimal_config(tmp_path)
    job = Job(
        title="SE",
        company="X",
        city="",
        postal_code="",
        remote_type=RemoteType.ONSITE.value,
        distance_km=None,
    )
    reason = distance_exclude(job, cfg)
    assert reason is not None
    assert "prüfbar" in reason


def test_pipeline_geo_only_after_fachlich(tmp_path, monkeypatch):
    """GeoResolver must not run for fachlich excluded jobs."""
    from core.config import AppConfig, LocationConfig, SearchPreferences, SettingsConfig, JobsConfig
    from core.database import Database

    db = Database(tmp_path / "p.db", recover=False)
    cfg = AppConfig(
        root=tmp_path,
        profile=SearchPreferences(
            location=LocationConfig(
                postal_code="10115",
                city="Berlin",
                country="DE",
                home_address="10115 Berlin",
                max_distance_km=30,
            ),
            jobs=JobsConfig(unwanted_titles=["Praktikant"]),
        ),
        settings=SettingsConfig(geocoder="local"),
    )
    calls = {"n": 0}
    real = LocationService.resolve_job_place

    def counted(self, *a, **kw):
        calls["n"] += 1
        return real(self, *a, **kw)

    monkeypatch.setattr(LocationService, "resolve_job_place", counted)
    excluded = Job(
        title="Praktikant Buchhaltung",
        company="Y",
        city="Berlin",
        postal_code="10117",
        country_code="DE",
        remote_type=RemoteType.ONSITE.value,
    )
    result = score_job(excluded, cfg, apply_distance=False)
    assert result.excluded
    candidates = []
    if not result.excluded:
        candidates.append(excluded)
    svc = LocationService(db, cfg)
    if candidates:
        enrich_job_locations(candidates, svc)
    assert calls["n"] == 0


def test_near_but_fachlich_excluded_stays_out(tmp_path):
    from core.config import AppConfig, LocationConfig, SearchPreferences, SettingsConfig, JobsConfig

    cfg = AppConfig(
        root=tmp_path,
        profile=SearchPreferences(
            location=LocationConfig(
                postal_code="10115",
                city="Berlin",
                country="DE",
                max_distance_km=100,
                home_latitude=52.52,
                home_longitude=13.405,
                home_geocoded_address="x",
            ),
            jobs=JobsConfig(unwanted_titles=["Praktikant"]),
        ),
        settings=SettingsConfig(),
    )
    job = Job(
        title="Praktikant",
        company="Near",
        latitude=52.53,
        longitude=13.41,
        distance_km=2.0,
        remote_type=RemoteType.ONSITE.value,
    )
    r = score_job(job, cfg, apply_distance=False)
    assert r.excluded


def test_cache_hit_skips_second_resolve(tmp_path, monkeypatch):
    db, cfg = _minimal_config(tmp_path)
    svc = LocationService(db, cfg)
    jobs = [
        Job(
            id="1",
            title="A",
            company="C",
            postal_code="10117",
            city="Berlin",
            country_code="DE",
            remote_type=RemoteType.ONSITE.value,
        ),
        Job(
            id="2",
            title="B",
            company="C",
            postal_code="10117",
            city="Berlin",
            country_code="DE",
            remote_type=RemoteType.ONSITE.value,
        ),
    ]
    enrich_job_locations(jobs, svc)
    assert svc.stats.unique_queries == 1
    assert jobs[0].distance_km == jobs[1].distance_km


def test_failed_geo_update_keeps_old(tmp_path, monkeypatch):
    mgr = get_geo_dataset_manager(tmp_path)
    before = mgr.ensure_active()
    assert before.valid

    def boom(*a, **k):
        raise RuntimeError("network down")

    monkeypatch.setattr(mgr, "_download_country", boom)
    after = mgr.update_from_upstream()
    assert after.valid
    assert after.version == before.version
