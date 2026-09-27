"""Prove invisible airline prefilter vs authoritative BRouter Fahrstrecke.

Stage A (search): airline_km is computed but never shown; exclude only when
airline_km > max radius (equality still goes to BRouter).
Stage B: only brouter distance_km decides the final radius and UI label.
Stage C: unknown road → keep job + „Fahrstrecke nicht bestimmbar“.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from core.config import AppConfig, LocationConfig, ProfileConfig
from core.hard_filter import distance_exclude
from core.models import Job, RemoteType
from core.road_route_brouter import BROUTER_ENGINE_ID, RoadRouteResult
from desktop.i18n import i18n
from desktop.pages.jobs import format_commute_label


def _cfg(radius: float = 30.0) -> AppConfig:
    return AppConfig(
        profile=ProfileConfig(location=LocationConfig(max_distance_km=radius))
    )


@pytest.fixture(autouse=True)
def _de_ui():
    i18n.set_language("de")


# ---------------------------------------------------------------------------
# Stage A — invisible Luftlinie prefilter (strict >)
# ---------------------------------------------------------------------------


def test_airline_equal_radius_does_not_prefilter():
    """Luftlinie == Radius: keep for BRouter (not „sicher größer“)."""
    job = Job(
        title="Border",
        company="X",
        airline_km=30.0,
        distance_km=None,
        distance_source="",
        remote_type=RemoteType.ONSITE.value,
    )
    assert distance_exclude(job, _cfg(30.0)) is None


def test_airline_just_over_radius_prefilters():
    job = Job(
        title="Far",
        company="X",
        airline_km=30.01,
        distance_km=None,
        distance_source="",
        remote_type=RemoteType.ONSITE.value,
    )
    reason = distance_exclude(job, _cfg(30.0))
    assert reason is not None
    assert "Luftlinie-Vorfilter" in reason
    assert "30.0" in reason or "30" in reason
    # Prefilter reason may mention airline km for logs — UI must not use them.
    label = format_commute_label(job)
    assert "Fahrstrecke nicht bestimmbar" in label
    assert "Luftlinie" not in label
    assert "30" not in label  # no airline kilometres in UI


def test_airline_km_never_used_as_final_when_road_missing():
    """airline ≤ radius but no road → keep; never treat airline as Fahrstrecke."""
    job = Job(
        title="Near",
        company="Y",
        airline_km=12.0,
        distance_km=None,
        distance_source="",
        distance_error="Routing-Dienst nicht verfügbar",
        remote_type=RemoteType.ONSITE.value,
    )
    assert distance_exclude(job, _cfg(30.0)) is None
    label = format_commute_label(job)
    assert "Fahrstrecke nicht bestimmbar" in label
    assert "12" not in label
    assert "Luftlinie" not in label


# ---------------------------------------------------------------------------
# Stage B — only BRouter Fahrstrecke is final
# ---------------------------------------------------------------------------


def test_road_over_radius_excludes_even_if_airline_under():
    job = Job(
        title="Detour",
        company="Z",
        airline_km=25.0,
        distance_km=42.0,
        distance_source=BROUTER_ENGINE_ID,
        remote_type=RemoteType.ONSITE.value,
    )
    reason = distance_exclude(job, _cfg(30.0))
    assert reason is not None
    assert "Fahrstrecke" in reason
    assert "Luftlinie" not in reason
    label = format_commute_label(job)
    assert "42" in label
    assert "Fahrstrecke" in label
    assert "Luftlinie" not in label


def test_road_equal_radius_kept_and_shown():
    job = Job(
        title="Edge",
        company="Z",
        airline_km=20.0,
        distance_km=30.0,
        distance_source=BROUTER_ENGINE_ID,
        remote_type=RemoteType.ONSITE.value,
    )
    assert distance_exclude(job, _cfg(30.0)) is None
    label = format_commute_label(job)
    assert "30" in label
    assert "Fahrstrecke" in label


def test_haversine_on_distance_km_not_shown_as_road():
    """Legacy/mistaken haversine in distance_km must not appear as Fahrstrecke."""
    job = Job(
        title="Legacy",
        company="Z",
        airline_km=18.0,
        distance_km=18.0,
        distance_source="haversine_v1",
        remote_type=RemoteType.ONSITE.value,
    )
    # Final filter must not treat haversine distance_km as road.
    assert distance_exclude(job, _cfg(30.0)) is None
    label = format_commute_label(job)
    assert "Fahrstrecke nicht bestimmbar" in label
    assert "18" not in label
    assert "Luftlinie" not in label


# ---------------------------------------------------------------------------
# Enrich pipeline: where Stage A skips BRouter
# ---------------------------------------------------------------------------


def test_enrich_skips_brouter_when_airline_over_radius(tmp_path, monkeypatch):
    from core.database import Database
    from core.geo_dataset import GeoDatasetManager, reset_geo_dataset_manager_for_tests
    from core.geo_resolve import reset_pgeocode_index_for_tests
    from core.location import LocationService, enrich_job_locations

    reset_geo_dataset_manager_for_tests()
    reset_pgeocode_index_for_tests()
    monkeypatch.setenv("KARRIEREKRAKE_GEO_DATA_DIR", str(tmp_path / "geo"))
    GeoDatasetManager(config_root=tmp_path).ensure_active()

    db = Database(tmp_path / "t.db", recover=False)
    cfg = AppConfig(
        root=tmp_path,
        profile=ProfileConfig(
            location=LocationConfig(
                postal_code="10115",
                city="Berlin",
                country="DE",
                home_latitude=52.52,
                home_longitude=13.405,
                home_geocoded_address="10115 Berlin",
                max_distance_km=20.0,
                allow_remote_germany=True,
                allow_hybrid=True,
            )
        ),
    )
    svc = LocationService(db, cfg)
    route_calls: list[tuple] = []

    def _no_route(*args, **kwargs):
        route_calls.append(args)
        return RoadRouteResult(ok=False, distance_km=None, error="should_not_call")

    import core.location as loc_mod

    monkeypatch.setattr(loc_mod, "_route_road_km", _no_route)

    # Explicit coords ~50 km north of Berlin home → airline >> 20 km
    far = Job(
        title="Far",
        company="X",
        latitude=52.52 + 50 / 111.2,
        longitude=13.405,
        country_code="DE",
        remote_type=RemoteType.ONSITE.value,
    )
    enrich_job_locations([far], svc)
    assert far.airline_km is not None and far.airline_km > 20.0
    assert far.distance_km is None
    assert far.distance_source == ""
    assert route_calls == []  # Stage A skipped BRouter
    reason = distance_exclude(far, cfg)
    assert reason and "Luftlinie-Vorfilter" in reason
    label = format_commute_label(far)
    assert "Fahrstrecke nicht bestimmbar" in label or "Luftlinie" not in label
    # Excluded jobs may still format; airline km must not be the label value.
    assert f"{far.airline_km:.0f}" not in label
    assert f"{far.airline_km:.1f}" not in label


def test_enrich_routes_when_airline_equals_radius(tmp_path, monkeypatch):
    """airline_km == max_distance_km must still call BRouter (not Stage-A skip)."""
    from core.database import Database
    from core.geo_dataset import GeoDatasetManager, reset_geo_dataset_manager_for_tests
    from core.geo_resolve import reset_pgeocode_index_for_tests
    from core.location import LocationService, enrich_job_locations

    reset_geo_dataset_manager_for_tests()
    reset_pgeocode_index_for_tests()
    monkeypatch.setenv("KARRIEREKRAKE_GEO_DATA_DIR", str(tmp_path / "geo"))
    GeoDatasetManager(config_root=tmp_path).ensure_active()

    db = Database(tmp_path / "t.db", recover=False)
    cfg = AppConfig(
        root=tmp_path,
        profile=ProfileConfig(
            location=LocationConfig(
                postal_code="10115",
                city="Berlin",
                country="DE",
                home_latitude=52.52,
                home_longitude=13.405,
                home_geocoded_address="10115 Berlin",
                max_distance_km=20.0,
                allow_remote_germany=True,
                allow_hybrid=True,
            )
        ),
    )
    svc = LocationService(db, cfg)
    monkeypatch.setattr(svc, "ensure_home_coords", lambda: (52.52, 13.405))
    monkeypatch.setattr(
        svc,
        "commute_for_job_location",
        lambda **kwargs: (52.7, 13.405, 20.0, None),  # airline exactly == radius
    )
    calls: list[tuple] = []

    def _road(*args, **kwargs):
        calls.append(args)
        return RoadRouteResult(ok=True, distance_km=28.5, engine=BROUTER_ENGINE_ID)

    import core.location as loc_mod

    monkeypatch.setattr(loc_mod, "_route_road_km", _road)

    job = Job(
        title="Eq",
        company="X",
        latitude=52.7,
        longitude=13.405,
        country_code="DE",
        remote_type=RemoteType.ONSITE.value,
    )
    enrich_job_locations([job], svc)
    assert len(calls) == 1  # Stage A did NOT skip — equality routes
    assert job.airline_km == 20.0
    assert job.distance_km == 28.5
    assert job.distance_source == BROUTER_ENGINE_ID
    reason = distance_exclude(job, cfg)
    assert reason and "Fahrstrecke" in reason
    label = format_commute_label(job)
    assert "Fahrstrecke" in label
    assert "Luftlinie" not in label
    assert "20" not in label  # airline not shown


# ---------------------------------------------------------------------------
# DE/NL/BE border places (coords) — prefilter vs road
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name,lat,lon,radius,expect_prefilter",
    [
        # Aachen home → Maastricht (~29 km airline) radius 25 → prefilter
        ("aachen_to_maastricht", 50.8514, 5.6910, 25.0, True),
        # Aachen home → Maastricht radius 40 → route
        ("aachen_to_maastricht_wide", 50.8514, 5.6910, 40.0, False),
        # Eupen BE from Aachen (~15–20 km) radius 10 → likely prefilter
        ("aachen_to_eupen", 50.6279, 6.0365, 10.0, True),
    ],
)
def test_border_pairs_prefilter_stage(name, lat, lon, radius, expect_prefilter):
    home = (50.7753, 6.0839)  # Aachen
    from core.geo_resolve import haversine_km

    air = haversine_km(home[0], home[1], lat, lon)
    job = Job(
        title=name,
        company="Border",
        airline_km=air,
        latitude=lat,
        longitude=lon,
        country_code="",
        remote_type=RemoteType.ONSITE.value,
    )
    if expect_prefilter:
        assert air > radius
        reason = distance_exclude(job, _cfg(radius))
        assert reason and "Luftlinie-Vorfilter" in reason
        assert job.distance_km is None
    else:
        assert air <= radius
        # Without road yet → keep (Stage C), not prefilter
        assert distance_exclude(job, _cfg(radius)) is None
        job.distance_km = air + 5.0  # simulated road > airline
        job.distance_source = BROUTER_ENGINE_ID
        # Final uses road only
        if job.distance_km > radius:
            assert "Fahrstrecke" in (distance_exclude(job, _cfg(radius)) or "")
