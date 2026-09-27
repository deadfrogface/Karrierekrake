"""DE/NL/BE place resolution — country-aware PLZ, no silent CH for NL."""

from __future__ import annotations

import pytest

from core.geo_normalize import (
    normalize_place_fields,
    plz_candidate_countries,
    source_location_blob_to_fields,
)
from core.geo_resolve import (
    reset_pgeocode_index_for_tests,
    resolve_place,
    resolve_place_offline,
    resolve_postal_pgeocode,
)
from core.geo_dataset import reset_geo_dataset_manager_for_tests


@pytest.fixture(autouse=True)
def _geo_reset(tmp_path, monkeypatch):
    reset_geo_dataset_manager_for_tests()
    reset_pgeocode_index_for_tests()
    monkeypatch.setenv("KARRIEREKRAKE_GEO_DATA_DIR", str(tmp_path / "geo_active"))


def test_plz_6211_nl_not_switzerland():
    place = normalize_place_fields(
        city="Maastricht", postal_code="6211", country_code="NL"
    )
    assert place.country_code == "NL"
    res = resolve_place(place)
    assert res.ok, res.reason
    assert res.country_code == "NL"
    assert res.latitude is not None and res.latitude > 50.0  # Limburg, not CH
    assert "CH" not in (res.display_name or "")
    assert "Buchs" not in (res.display_name or "")


def test_plz_6211_without_country_ambiguous():
    place = normalize_place_fields(postal_code="6211")
    assert not place.country_code
    res = resolve_place_offline(place)
    assert res.status == "AMBIGUOUS"
    assert set(plz_candidate_countries("6211")) == {"AT", "CH", "NL", "BE"}


def test_blob_6211_nl_keeps_country():
    fields = source_location_blob_to_fields("6211 Maastricht NL")
    assert fields["country_code"] == "NL"
    assert fields["postal_code"] == "6211"
    place = normalize_place_fields(**fields)
    res = resolve_place(place)
    assert res.ok
    assert res.country_code == "NL"


def test_be_eupen_plz_resolves_or_honest_unknown():
    place = normalize_place_fields(
        city="Eupen", postal_code="4700", country_code="BE"
    )
    res = resolve_place(place)
    # With bundled BE data → RESOLVED; without → UNKNOWN (never a wrong country).
    if res.ok:
        assert res.country_code == "BE"
        assert abs(float(res.latitude) - 50.63) < 0.2
    else:
        assert res.status == "UNKNOWN"
        assert res.country_code == "BE"


def test_be_city_without_data_stays_unknown_not_dach():
    res = resolve_postal_pgeocode("4700", "BE")
    if res.ok:
        assert res.country_code == "BE"
    else:
        assert res.status == "UNKNOWN"
        assert res.country_code == "BE"


def test_frankfurt_stays_ambiguous():
    place = normalize_place_fields(city="Frankfurt", country_code="DE")
    res = resolve_place(place)
    assert res.status == "AMBIGUOUS"
