"""BRouter road-route + production distance-filter wiring tests."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import core.hard_filter as hard_filter
import core.location as location
import core.road_route_brouter as br
from core.config import AppConfig, LocationConfig, ProfileConfig
from core.models import Job


def test_osm_attribution_mentions_openstreetmap():
    assert "OpenStreetMap" in br.OSM_ATTRIBUTION
    assert "BRouter" in br.OSM_ATTRIBUTION
    assert "Google" in br.OSM_ATTRIBUTION  # negation clause


def test_route_driving_km_parses_track_length():
    geo = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"track-length": "38696"},
                "geometry": {"type": "LineString", "coordinates": []},
            }
        ],
    }
    body = json.dumps(geo).encode()

    class _Resp:
        status = 200

        def read(self):
            return body

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    with patch("urllib.request.urlopen", return_value=_Resp()):
        r = br.route_driving_km(
            50.7753, 6.0839, 50.8514, 5.6910, base_url="http://127.0.0.1:17777"
        )
    assert r.ok
    assert r.distance_km == 38.696
    assert not r.unknown


def test_island_error_triggers_snap_retry_then_unknown():
    """Island responses must retry nearby offsets; still unknown if all fail."""
    calls: list[str] = []

    def _urlopen(req, timeout=120):  # noqa: ANN001
        import io
        import urllib.error

        calls.append(str(getattr(req, "full_url", req)))
        raise urllib.error.HTTPError(
            str(getattr(req, "full_url", "http://x")),
            400,
            "Bad Request",
            hdrs=None,  # type: ignore[arg-type]
            fp=io.BytesIO(b"target island detected for section 0\n"),
        )

    with patch("urllib.request.urlopen", side_effect=_urlopen):
        r = br.route_driving_km(
            50.8455,
            4.3571,
            50.9014,
            4.4844,
            base_url="http://127.0.0.1:9",
            allow_snap_retry=True,
        )
    assert not r.ok
    assert r.distance_km is None
    assert r.unknown
    assert "island" in (r.error or "").casefold()
    assert len(calls) > 1  # spiral retries


def test_island_snap_recovers_on_nearby_offset():
    island_body = b"target island detected for section 0\n"
    ok_geo = json.dumps(
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {"track-length": "14494"},
                    "geometry": {"type": "LineString", "coordinates": []},
                }
            ],
        }
    ).encode()
    state = {"n": 0}

    class _Ok:
        status = 200

        def read(self):
            return ok_geo

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def _urlopen(req, timeout=120):  # noqa: ANN001
        import io
        import urllib.error

        state["n"] += 1
        if state["n"] == 1:
            raise urllib.error.HTTPError(
                "http://x",
                400,
                "Bad",
                hdrs=None,  # type: ignore[arg-type]
                fp=io.BytesIO(island_body),
            )
        return _Ok()

    with patch("core.road_route_brouter.urllib.request.urlopen", side_effect=_urlopen):
        r = br.route_driving_km(
            50.8455, 4.3571, 50.9014, 4.4844, base_url="http://127.0.0.1:9"
        )
    assert r.ok
    assert r.distance_km == 14.494
    assert r.snap_offset_m is not None and r.snap_offset_m > 0


def test_border_pair_ids_present_in_bakeoff_fixture():
    pairs = json.loads(
        Path("artifacts/road_distance_bakeoff/PAIRS_30.json").read_text(encoding="utf-8")
    )
    cross = [p for p in pairs["pairs"] if p["cat"] == "cross_border"]
    assert len(cross) == 6
    ids = {p["id"] for p in cross}
    assert ids == {"X01", "X02", "X03", "X04", "X05", "X06"}


def test_production_distance_modules_import_brouter():
    """Productive filter path must be able to use BRouter (wired)."""
    import inspect

    src = Path(inspect.getfile(location)).read_text(encoding="utf-8")
    assert "road_route_brouter" in src
    src_hf = Path(inspect.getfile(hard_filter)).read_text(encoding="utf-8")
    assert "brouter" in src_hf.casefold() or "BROUTER" in src_hf or "road" in src_hf.casefold()


def test_ensure_segments_skips_existing(tmp_path: Path):
    seg = tmp_path / "segments4"
    seg.mkdir()
    f = seg / "E5_N50.rd5"
    f.write_bytes(b"x" * 2_000_000)
    with patch("urllib.request.urlopen") as mock_url:
        out = br.ensure_segments(seg, names=("E5_N50",))
    mock_url.assert_not_called()
    assert out == [f]


def test_distance_exclude_airline_prefilter_only():
    cfg = AppConfig(
        profile=ProfileConfig(location=LocationConfig(max_distance_km=20.0))
    )
    far = Job(
        title="Far",
        company="X",
        airline_km=35.0,
        distance_km=None,
        distance_source="",
    )
    reason = hard_filter.distance_exclude(far, cfg)
    assert reason is not None
    assert "Luftlinie" in reason


def test_distance_exclude_keeps_unknown_road():
    cfg = AppConfig(
        profile=ProfileConfig(location=LocationConfig(max_distance_km=50.0))
    )
    job = Job(
        title="Near",
        company="Y",
        airline_km=12.0,
        distance_km=None,
        distance_source="",
        distance_error="Kartensegment fehlt",
    )
    assert hard_filter.distance_exclude(job, cfg) is None


def test_distance_exclude_road_over_limit():
    cfg = AppConfig(
        profile=ProfileConfig(location=LocationConfig(max_distance_km=20.0))
    )
    job = Job(
        title="Drive",
        company="Z",
        airline_km=15.0,
        distance_km=28.0,
        distance_source=br.BROUTER_ENGINE_ID,
    )
    reason = hard_filter.distance_exclude(job, cfg)
    assert reason is not None
    assert "Fahrstrecke" in reason


def test_format_driving_unknown():
    assert "Fahrstrecke nicht bestimmbar" in br.format_driving_unknown("x")
