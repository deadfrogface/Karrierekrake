"""The reader of the local postal tables (core/geo_postal_index.py)."""
from __future__ import annotations

import math
from pathlib import Path

import pytest

from core.geo_dataset import bundled_geo_dir
from core.geo_postal_index import PostalIndex

HEADER = ("country_code,postal_code,place_name,state_name,state_code,county_name,county_code,"
          "community_name,community_code,latitude,longitude,accuracy\n")


def _table(tmp_path: Path, *lines: str) -> Path:
    path = tmp_path / "DE.txt"
    path.write_text(HEADER + "".join(line + "\n" for line in lines), encoding="utf-8")
    return path


def test_a_postal_code_is_the_mean_of_its_rows_and_names_them_in_file_order(tmp_path):
    index = PostalIndex.load(_table(
        tmp_path,
        "DE,01067,Dresden,Sachsen,SN,,,,,51.0,13.0,",
        'DE,01067,Friedrichstadt,Sachsen,SN,,,"Dresden, Stadt",,52.0,14.0,',
        "DE,10115,Berlin,Berlin,BE,,,,,52.5323,13.3846,6.0",
    ))
    row = index.query_postal_code("01067")
    assert (row.latitude, row.longitude) == (51.5, 13.5)
    assert row.place_name == "Dresden, Friedrichstadt"
    assert index.query_postal_code("10115").place_name == "Berlin"


def test_an_unknown_postal_code_has_no_coordinates(tmp_path):
    index = PostalIndex.load(_table(tmp_path, "DE,10115,Berlin,Berlin,BE,,,,,52.5,13.4,"))
    row = index.query_postal_code("99999")
    assert math.isnan(row.latitude) and math.isnan(row.longitude)
    assert row.place_name == ""


def test_rows_without_coordinates_do_not_move_the_mean(tmp_path):
    index = PostalIndex.load(_table(
        tmp_path,
        "DE,10115,Berlin,Berlin,BE,,,,,52.0,13.0,",
        "DE,10115,Mitte,Berlin,BE,,,,,,,",
        "DE,20095,Hamburg,Hamburg,HH,,,,,,,",
    ))
    row = index.query_postal_code("10115")
    assert (row.latitude, row.longitude) == (52.0, 13.0)
    nowhere = index.query_postal_code("20095")
    assert math.isnan(nowhere.latitude) and math.isnan(nowhere.longitude)


def test_place_names_match_exactly_after_casefold_and_parts_are_only_listed(tmp_path):
    index = PostalIndex.load(_table(
        tmp_path,
        "DE,10115,Berlin,Berlin,BE,,,,,52.5,13.4,",
        "DE,10117,BERLIN,Berlin,BE,,,,,52.6,13.5,",
        "DE,16321,Bernau,Brandenburg,BB,,,,,52.7,13.6,",
        "DE,95030,Straße am Fluß,Bayern,BY,,,,,50.3,11.9,",
    ))
    assert [(name, lat) for name, lat, _lon in index.exact_places("berlin")] == [("Berlin", 52.5), ("BERLIN", 52.6)]
    assert index.exact_places("berl") == []
    assert index.exact_places("strasse am fluss") != []          # casefold: ß equals ss
    assert index.names_containing("ber") == {"berlin", "bernau"}
    assert index.names_containing("(a+)+$") == set()             # plain text, never a pattern


@pytest.mark.parametrize("content", ["", "a,b,c\n1,2,3\n"])
def test_a_file_that_is_not_a_postal_table_is_an_error(tmp_path, content):
    path = tmp_path / "DE.txt"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(ValueError):
        PostalIndex.load(path)


def test_a_missing_file_is_an_error_and_nothing_else_happens(tmp_path):
    with pytest.raises(OSError):
        PostalIndex.load(tmp_path / "DE.txt")
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("country,code,lat,lon", [
    ("DE", "10115", 52.5323, 13.3846),
    ("AT", "6900", 47.5031, 9.7471),
    ("CH", "8001", 47.3667, 8.55),
])
def test_bundled_tables_resolve_known_postal_codes(country, code, lat, lon):
    index = PostalIndex.load(bundled_geo_dir() / "geonames" / f"{country}.txt")
    row = index.query_postal_code(code)
    assert row.latitude == pytest.approx(lat, abs=0.05)
    assert row.longitude == pytest.approx(lon, abs=0.05)


def test_reading_writes_nothing_next_to_the_table(tmp_path):
    path = _table(tmp_path, "DE,10115,Berlin,Berlin,BE,,,,,52.5,13.4,")
    PostalIndex.load(path).query_postal_code("10115")
    assert [item.name for item in tmp_path.iterdir()] == ["DE.txt"]
