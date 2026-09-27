"""BRouter road-route scaffold tests — production distance filter unchanged."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import core.hard_filter as hard_filter
import core.location as location
import core.road_route_brouter as br


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
        r = br.route_driving_km(50.7753, 6.0839, 50.8514, 5.6910, base_url="http://127.0.0.1:17777")
    assert r.ok
    assert r.distance_km == 38.696
    assert not r.unknown


def test_route_failure_is_unknown_not_invented():
    class _Resp:
        status = 200

        def read(self):
            return b"target island detected for section 0"

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    with patch("urllib.request.urlopen", return_value=_Resp()):
        r = br.route_driving_km(50.8455, 4.3571, 50.9014, 4.4844, base_url="http://127.0.0.1:9")
    assert not r.ok
    assert r.distance_km is None
    assert r.unknown


def test_border_pair_ids_present_in_bakeoff_fixture():
    pairs = json.loads(Path("artifacts/road_distance_bakeoff/PAIRS_30.json").read_text(encoding="utf-8"))
    cross = [p for p in pairs["pairs"] if p["cat"] == "cross_border"]
    assert len(cross) == 6
    ids = {p["id"] for p in cross}
    assert ids == {"X01", "X02", "X03", "X04", "X05", "X06"}


def test_production_distance_modules_not_importing_brouter():
    """Guard: productive filter must stay airline until product switch."""
    import inspect

    for mod in (hard_filter, location):
        src = Path(inspect.getfile(mod)).read_text(encoding="utf-8")
        assert "road_route_brouter" not in src
        assert "RouteServer" not in src


def test_ensure_segments_skips_existing(tmp_path: Path):
    seg = tmp_path / "segments4"
    seg.mkdir()
    f = seg / "E5_N50.rd5"
    f.write_bytes(b"x" * 2_000_000)
    with patch("urllib.request.urlopen") as mock_url:
        out = br.ensure_segments(seg, names=("E5_N50",))
    mock_url.assert_not_called()
    assert out == [f]
