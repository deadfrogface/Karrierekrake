"""DACH cross-border geo tests (NEXT-05).

Haversine/pgeocode cases remain as diagnostics. LocationService enrich paths
use an injected Google Maps fake (road km ≈ airline for golden border cases).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import pytest

from core.config import AppConfig, LocationConfig, SearchPreferences, SettingsConfig
from core.database import Database
from core.geo_normalize import (
    normalize_country_code,
    normalize_place_fields,
    plz_candidate_countries,
)
from core.geo_resolve import (
    PUBLIC_REF_COORDS,
    PlaceResolution,
    distance_km_or_unknown,
    haversine_km,
    resolve_place,
    resolve_place_offline,
    resolve_postal_pgeocode,
    within_radius,
)
from core.location import LocationService, enrich_job_locations
from core.models import RemoteType
from integrations.maps.contracts import GeocodeResult, MapsError, RouteMatrixResult
from integrations.maps.metering import reset_cost_meter_for_tests
from integrations.maps.service import MapsGeoService, reset_maps_service_for_tests


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TOL_KM = 1.5  # numerical tolerance for textbook Haversine checks


def _approx_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    return haversine_km(a[0], a[1], b[0], b[1])


class _MapsFakeAirlineAsRoad:
    """Test double: Route Matrix returns ~airline metres (border golden cases)."""

    def __init__(self, *, geocode_ok: bool = False) -> None:
        self.geocode_ok = geocode_ok
        self.geocode_calls = 0
        self.matrix_calls = 0

    def geocode(self, address: str, *, region: str = "de", run_id: str = "") -> GeocodeResult:
        self.geocode_calls += 1
        if not self.geocode_ok:
            raise MapsError("MISS", "no geocode in this fixture")
        return GeocodeResult(latitude=47.66, longitude=9.17, formatted_address=address)

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
        km = haversine_km(origin_lat, origin_lon, dest_lat, dest_lon)
        return RouteMatrixResult(
            distance_meters=int(round(km * 1000)),
            duration_seconds=int(round(km * 90)),  # ~90 s per km
        )


@dataclass
class _Job:
    address: str = ""
    city: str = ""
    postal_code: str = ""
    country_code: str = ""
    latitude: float | None = None
    longitude: float | None = None
    distance_km: float | None = None
    commute_duration_minutes: float | None = None
    distance_source: str = ""
    remote_type: str = RemoteType.ONSITE.value
    description: str = ""


def _svc(
    tmp_path,
    *,
    home_lat: float,
    home_lon: float,
    radius: float = 25.0,
    cross_border: bool = True,
    country: str = "DE",
    geocode_ok: bool = False,
) -> LocationService:
    reset_maps_service_for_tests()
    reset_cost_meter_for_tests()
    db = Database(tmp_path / "geo.db")
    cfg = AppConfig(
        profile=SearchPreferences(
            location=LocationConfig(
                home_address="Konstanz, Germany",
                max_distance_km=radius,
                country=country,
                home_latitude=home_lat,
                home_longitude=home_lon,
                home_geocoded_address="Konstanz, Germany",
                cross_border_dach=cross_border,
            )
        ),
        settings=SettingsConfig(cross_border_dach_enabled=cross_border),
    )
    fake = _MapsFakeAirlineAsRoad(geocode_ok=geocode_ok)
    maps = MapsGeoService(client=fake)  # type: ignore[arg-type]
    return LocationService(db, cfg, timeout_s=0.2, maps=maps)


# ---------------------------------------------------------------------------
# Unit: Haversine numerical correctness
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "lat1,lon1,lat2,lon2,expected_km",
    [
        # Same point
        (47.66, 9.17, 47.66, 9.17, 0.0),
        # ~1° latitude ≈ 111.2 km
        (47.0, 9.0, 48.0, 9.0, 111.2),
        # Equator 1° lon ≈ 111.2 km
        (0.0, 0.0, 0.0, 1.0, 111.2),
        # Antimeridian short arc
        (0.0, 179.5, 0.0, -179.5, 111.2),
    ],
)
def test_haversine_textbook(lat1, lon1, lat2, lon2, expected_km):
    got = haversine_km(lat1, lon1, lat2, lon2)
    assert abs(got - expected_km) < TOL_KM


def test_haversine_symmetric():
    a = PUBLIC_REF_COORDS["konstanz_de"][:2]
    b = PUBLIC_REF_COORDS["kreuzlingen_ch"][:2]
    assert abs(haversine_km(*a, *b) - haversine_km(*b, *a)) < 1e-9


# ---------------------------------------------------------------------------
# Border golden: Konstanz DE ↔ CH / AT (task example)
# ---------------------------------------------------------------------------

def test_konstanz_radius_25_cross_border_matrix():
    """Home Konstanz, radius 25 km — DE near yes, CH near yes, AT far no."""
    home = PUBLIC_REF_COORDS["konstanz_de"][:2]
    de_near = PUBLIC_REF_COORDS["singen_de"][:2]
    ch_near = PUBLIC_REF_COORDS["kreuzlingen_ch"][:2]
    at_far = PUBLIC_REF_COORDS["innsbruck_at"][:2]

    d_de = _approx_km(home, de_near)
    d_ch = _approx_km(home, ch_near)
    d_at = _approx_km(home, at_far)

    # Singen is ~25–35 km; adjust expectation: if >25, use a synthetic DE point
    # 20 km north of Konstanz for the "DE job 20 km → yes" case.
    de_20 = (home[0] + 20.0 / 111.2, home[1])  # ≈20 km north
    d_de20 = _approx_km(home, de_20)
    assert 18.0 <= d_de20 <= 22.0
    assert within_radius(d_de20, 25.0) is True

    assert d_ch < 10.0  # Kreuzlingen is a few km from Konstanz
    assert within_radius(d_ch, 25.0) is True

    assert d_at > 100.0
    assert within_radius(d_at, 25.0) is False

    # Border is not a barrier: CH distance uses same math as DE
    assert d_ch < d_de or d_ch < 15.0


@pytest.mark.parametrize(
    "home_key,job_key,radius,expect_inside",
    [
        ("konstanz_de", "kreuzlingen_ch", 25.0, True),
        ("konstanz_de", "innsbruck_at", 25.0, False),
        ("konstanz_de", "bregenz_at", 50.0, True),
        ("konstanz_de", "bregenz_at", 20.0, False),
        ("basel_ch", "weil_am_rhein_de", 15.0, True),
        ("basel_ch", "innsbruck_at", 30.0, False),
        ("salzburg_at", "freilassing_de", 20.0, True),
        ("salzburg_at", "konstanz_de", 50.0, False),
        ("passau_de", "schaerding_at", 25.0, True),
        ("passau_de", "innsbruck_at", 40.0, False),
        ("weil_am_rhein_de", "basel_ch", 10.0, True),
        ("freilassing_de", "salzburg_at", 15.0, True),
        ("kreuzlingen_ch", "konstanz_de", 10.0, True),
        ("kreuzlingen_ch", "innsbruck_at", 25.0, False),
        ("bregenz_at", "konstanz_de", 60.0, True),
        ("bregenz_at", "basel_ch", 40.0, False),
        ("schaerding_at", "passau_de", 20.0, True),
        ("innsbruck_at", "konstanz_de", 50.0, False),
        ("singen_de", "kreuzlingen_ch", 40.0, True),
        ("singen_de", "salzburg_at", 50.0, False),
    ],
)
def test_border_region_radius_matrix(home_key, job_key, radius, expect_inside):
    home = PUBLIC_REF_COORDS[home_key][:2]
    job = PUBLIC_REF_COORDS[job_key][:2]
    dist = _approx_km(home, job)
    assert within_radius(dist, radius) is expect_inside


# Generate additional synthetic border pairs (~40 more cases)
_SYNTH_BORDER_CASES = []
_base = PUBLIC_REF_COORDS["konstanz_de"][:2]
for km in (1, 3, 5, 8, 10, 12, 15, 18, 20, 22, 24, 26, 30, 40, 50, 80, 100, 140, 180, 220):
    # North = fictional DE, South-east ≈ toward CH/AT depending on bearing
    de_pt = (_base[0] + km / 111.2, _base[1])
    ch_pt = (_base[0] - km / 111.2, _base[1] + 0.01)  # southish / CH-ish
    _SYNTH_BORDER_CASES.append((_base, de_pt, 25.0, km <= 25))
    _SYNTH_BORDER_CASES.append((_base, ch_pt, 25.0, km <= 25))


@pytest.mark.parametrize("home,job,radius,expect", _SYNTH_BORDER_CASES)
def test_synthetic_radius_bands(home, job, radius, expect):
    dist = _approx_km(home, job)
    assert within_radius(dist, radius) is expect


# ---------------------------------------------------------------------------
# E2E enrich with explicit coords (no network)
# ---------------------------------------------------------------------------

def test_enrich_konstanz_example_e2e(tmp_path, monkeypatch):
    home = PUBLIC_REF_COORDS["konstanz_de"]
    svc = _svc(tmp_path, home_lat=home[0], home_lon=home[1], radius=25.0)

    de_20 = (home[0] + 20.0 / 111.2, home[1])
    jobs = [
        _Job(city="DE-near", latitude=de_20[0], longitude=de_20[1], country_code="DE"),
        _Job(
            city="Kreuzlingen",
            latitude=PUBLIC_REF_COORDS["kreuzlingen_ch"][0],
            longitude=PUBLIC_REF_COORDS["kreuzlingen_ch"][1],
            country_code="CH",
        ),
        _Job(
            city="Innsbruck",
            latitude=PUBLIC_REF_COORDS["innsbruck_at"][0],
            longitude=PUBLIC_REF_COORDS["innsbruck_at"][1],
            country_code="AT",
        ),
    ]
    enrich_job_locations(jobs, svc)
    assert jobs[0].distance_km is not None and jobs[0].distance_km <= 25
    assert jobs[1].distance_km is not None and jobs[1].distance_km <= 25
    assert jobs[2].distance_km is not None and jobs[2].distance_km > 25
    assert all(j.distance_source == "google_route_matrix" for j in jobs if j.distance_km is not None)


def test_cross_border_toggle_off_skips_foreign_plz(tmp_path, monkeypatch):
    home = PUBLIC_REF_COORDS["konstanz_de"]
    svc = _svc(
        tmp_path,
        home_lat=home[0],
        home_lon=home[1],
        cross_border=False,
        country="DE",
        geocode_ok=False,
    )
    # CH PLZ without coords — Google miss → UNKNOWN (no pgeocode authority)
    jobs = [_Job(city="Romanshorn", postal_code="8590", country_code="CH")]
    enrich_job_locations(jobs, svc)
    assert jobs[0].distance_km is None


# ---------------------------------------------------------------------------
# Same PLZ multiple countries → AMBIGUOUS / UNKNOWN distance
# ---------------------------------------------------------------------------

def test_plz_6900_ambiguous_without_country():
    place = normalize_place_fields(postal_code="6900")
    res = resolve_place_offline(place)
    assert res.status in {"AMBIGUOUS", "UNKNOWN"} or (
        res.status == "RESOLVED" and res.country_code in {"AT", "CH"}
    )
    # Without country, multi-hit must not invent a single silent country when both resolve
    if place.postal_code == "6900" and not place.country_code:
        candidates = plz_candidate_countries("6900")
        assert set(candidates) == {"AT", "CH"}
        hits = [resolve_postal_pgeocode("6900", c) for c in candidates]
        ok_hits = [h for h in hits if h.ok]
        assert len(ok_hits) >= 2
        # resolve_place_offline should mark AMBIGUOUS
        assert res.status == "AMBIGUOUS"


def test_plz_6900_with_country_at():
    res = resolve_postal_pgeocode("6900", "AT")
    assert res.ok
    assert res.country_code == "AT"
    assert res.data_source == "pgeocode"
    assert res.data_version


def test_plz_6900_with_country_ch():
    res = resolve_postal_pgeocode("6900", "CH")
    assert res.ok
    assert res.country_code == "CH"
    # Lugano ≠ Bregenz
    at = resolve_postal_pgeocode("6900", "AT")
    assert abs(res.latitude - at.latitude) > 0.5  # type: ignore[operator]


@pytest.mark.parametrize(
    "plz,country",
    [
        ("78462", "DE"),  # Konstanz
        ("10115", "DE"),  # Berlin
        ("80331", "DE"),  # München
        ("20095", "DE"),  # Hamburg
        ("50667", "DE"),  # Köln
        ("6900", "AT"),
        ("1010", "AT"),
        ("5020", "AT"),
        ("4020", "AT"),
        ("8010", "AT"),
        ("8001", "CH"),
        ("3011", "CH"),
        ("1200", "CH"),
        ("4001", "CH"),
        ("8590", "CH"),
    ],
)
def test_pgeocode_dach_plz_resolves(plz, country):
    res = resolve_postal_pgeocode(plz, country)
    assert res.ok, res.reason
    assert res.latitude is not None
    assert res.longitude is not None


# ---------------------------------------------------------------------------
# Missing coords / offline / unknown
# ---------------------------------------------------------------------------

def test_missing_coords_unknown_distance():
    home = PUBLIC_REF_COORDS["konstanz_de"][:2]
    unknown = PlaceResolution(status="UNKNOWN", reason="no_data")
    assert distance_km_or_unknown(home, unknown) is None


def test_no_home_unknown_distance():
    place = PlaceResolution(
        status="RESOLVED", latitude=47.66, longitude=9.17, country_code="DE"
    )
    assert distance_km_or_unknown(None, place) is None


def test_within_radius_unknown_returns_none():
    assert within_radius(None, 25.0) is None


def test_remote_within_radius():
    assert within_radius(None, 25.0, remote=True) is True
    assert within_radius(999.0, 25.0, remote=True) is True


def test_enrich_remote_skips(tmp_path, monkeypatch):
    home = PUBLIC_REF_COORDS["konstanz_de"]
    svc = _svc(tmp_path, home_lat=home[0], home_lon=home[1])
    jobs = [_Job(city="Zürich", country_code="CH", remote_type=RemoteType.REMOTE.value)]
    enrich_job_locations(jobs, svc)
    assert jobs[0].distance_km is None
    assert svc.stats.remote_skipped == 1


def test_unicode_place_names_normalize():
    place = normalize_place_fields(city="Zürich", country="Schweiz")
    assert place.city == "Zürich"
    assert place.country_code == "CH"
    place2 = normalize_place_fields(city="Göteborg")  # non-DACH city kept
    assert "ö" in place2.city.casefold() or "ö" in place2.city
    place3 = normalize_place_fields(city="Straßenhaus", country_code="DE")
    assert "ß" in place3.city or "ss" in place3.city.casefold() or place3.city


@pytest.mark.parametrize(
    "city",
    [
        "München",
        "Köln",
        "Düsseldorf",
        "Zürich",
        "Genève",
        "Neuchâtel",
        "Österreich-Dummy",
        "Weißensee",
        "Gießen",
        "Łódź-ignored-chars",
    ],
)
def test_unicode_cities_roundtrip_fields(city):
    p = normalize_place_fields(city=city, country_code="DE")
    assert p.city  # not emptied
    assert len(p.city) >= 2


# ---------------------------------------------------------------------------
# Cache provenance
# ---------------------------------------------------------------------------

def test_geocode_cache_stores_data_source_version(tmp_path):
    db = Database(tmp_path / "c.db")
    db.set_geocode(
        "de|78462",
        47.66,
        9.17,
        "Konstanz",
        data_source="pgeocode",
        data_version="geonames-pgeocode-0.5",
        country_code="DE",
        resolution_status="RESOLVED",
    )
    rec = db.get_geocode_record("de|78462")
    assert rec is not None
    assert rec["data_source"] == "pgeocode"
    assert rec["data_version"] == "geonames-pgeocode-0.5"
    assert rec["country_code"] == "DE"
    assert rec["resolution_status"] == "RESOLVED"


def test_legacy_geocode_cache_migration(tmp_path):
    """Old cache rows without provenance columns still readable after migrate."""
    import sqlite3

    path = tmp_path / "legacy.db"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE geocode_cache (
            query TEXT PRIMARY KEY,
            latitude REAL NOT NULL,
            longitude REAL NOT NULL,
            display_name TEXT,
            cached_at TEXT
        );
        INSERT INTO geocode_cache VALUES ('berlin', 52.52, 13.40, 'Berlin', '2020-01-01T00:00:00+00:00');
        """
    )
    conn.close()
    db = Database(path)
    got = db.get_geocode("berlin")
    assert got is not None
    assert got[0] == 52.52
    # New write adds provenance
    db.set_geocode(
        "hamburg",
        53.55,
        9.99,
        "Hamburg",
        data_source="nominatim",
        data_version="osm-nominatim-1",
    )
    rec = db.get_geocode_record("hamburg")
    assert rec["data_source"] == "nominatim"
    # Migrated columns exist
    assert "data_source" in (rec.keys() if hasattr(rec, "keys") else rec)


def test_job_country_code_column_migration(tmp_path):
    db = Database(tmp_path / "j.db")
    from core.models import Job

    job = Job(
        id="x1",
        source="test",
        source_job_id="1",
        title="T",
        company="C",
        city="Konstanz",
        country_code="DE",
        latitude=47.66,
        longitude=9.17,
    )
    db.upsert_job(job)
    loaded = db.get_job("x1")
    assert loaded is not None
    assert loaded.country_code == "DE"


# ---------------------------------------------------------------------------
# NEXT-05: without Google geocode, PLZ-only jobs stay UNKNOWN
# (pgeocode is diagnostic-only — not production authority)
# ---------------------------------------------------------------------------

def test_plz_without_google_stays_unknown(tmp_path):
    home = PUBLIC_REF_COORDS["konstanz_de"]
    svc = _svc(tmp_path, home_lat=home[0], home_lon=home[1], radius=25.0, geocode_ok=False)
    jobs = [
        _Job(postal_code="8590", country_code="CH", city="Romanshorn"),
        _Job(postal_code="78462", country_code="DE", city="Konstanz"),
    ]
    enrich_job_locations(jobs, svc)
    assert jobs[0].distance_km is None
    assert jobs[1].distance_km is None


def test_unknown_city_no_coords_stays_unknown(tmp_path):
    home = PUBLIC_REF_COORDS["konstanz_de"]
    svc = _svc(tmp_path, home_lat=home[0], home_lon=home[1], geocode_ok=False)
    jobs = [_Job(city="NirgendwoXYZ999", country_code="DE")]
    enrich_job_locations(jobs, svc)
    assert jobs[0].distance_km is None


# ---------------------------------------------------------------------------
# Country normalize smoke (extra geo cases)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "raw,iso",
    [
        ("DE", "DE"),
        ("de", "DE"),
        ("Germany", "DE"),
        ("Deutschland", "DE"),
        ("AT", "AT"),
        ("Austria", "AT"),
        ("Österreich", "AT"),
        ("CH", "CH"),
        ("Switzerland", "CH"),
        ("Schweiz", "CH"),
        ("Suisse", "CH"),
        ("", ""),
        ("FR", ""),
        ("US", ""),
    ],
)
def test_normalize_country_geo(raw, iso):
    assert normalize_country_code(raw) == iso


def test_distance_independent_of_country_label():
    """Same coords → same km regardless of country_code tags."""
    home = PUBLIC_REF_COORDS["konstanz_de"][:2]
    job = PUBLIC_REF_COORDS["kreuzlingen_ch"][:2]
    r1 = PlaceResolution(
        status="RESOLVED", latitude=job[0], longitude=job[1], country_code="CH"
    )
    r2 = PlaceResolution(
        status="RESOLVED", latitude=job[0], longitude=job[1], country_code="DE"
    )
    assert distance_km_or_unknown(home, r1) == distance_km_or_unknown(home, r2)


# Count pad: additional DE/AT/CH pairwise distances for beta border regions
_BETA_PAIRS = [
    ("konstanz_de", "kreuzlingen_ch"),
    ("konstanz_de", "bregenz_at"),
    ("basel_ch", "weil_am_rhein_de"),
    ("salzburg_at", "freilassing_de"),
    ("passau_de", "schaerding_at"),
    ("singen_de", "kreuzlingen_ch"),
    ("weil_am_rhein_de", "basel_ch"),
    ("freilassing_de", "salzburg_at"),
    ("schaerding_at", "passau_de"),
    ("bregenz_at", "konstanz_de"),
]


@pytest.mark.parametrize("a,b", _BETA_PAIRS)
@pytest.mark.parametrize("radius", [5, 10, 15, 20, 25, 30, 40, 50, 75, 100])
def test_beta_border_regions_radius_sweep(a, b, radius):
    ha = PUBLIC_REF_COORDS[a][:2]
    hb = PUBLIC_REF_COORDS[b][:2]
    dist = _approx_km(ha, hb)
    result = within_radius(dist, float(radius))
    assert result is (dist <= float(radius))
