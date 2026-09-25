"""Positive/negative tests for CV date semantic equivalence (Scorer V3.1)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from cv_date_normalize import dates_semantically_equal, normalize_partial_date


def test_positive_equivalents() -> None:
    assert dates_semantically_equal("02/2019", "2019-02")
    assert dates_semantically_equal("2/2019", "2019-02")
    assert dates_semantically_equal("08.2021", "2021-08")
    assert dates_semantically_equal("2020/03", "03/2020")
    assert dates_semantically_equal("2019-02-01", "02/2019")
    assert dates_semantically_equal("2014", "2014")
    assert dates_semantically_equal("heute", "present")
    assert dates_semantically_equal("aktuell", "current")


def test_negative_non_equivalents() -> None:
    # Different months
    assert not dates_semantically_equal("02/2019", "2019-03")
    assert not dates_semantically_equal("02/2019", "2020-02")
    # Year-only vs year-month is NOT treated as equal
    assert not dates_semantically_equal("2019", "2019-02")
    assert not dates_semantically_equal("2019-02", "2019")
    # Missing / empty
    assert not dates_semantically_equal("02/2019", "")
    assert not dates_semantically_equal("heute", "")
    assert not dates_semantically_equal("", "2019-02")
    assert not dates_semantically_equal(None, "2019-02")
    # Free-text non-dates
    assert not dates_semantically_equal("ohne Abschluss", "")
    assert not dates_semantically_equal("ohne Abschluss", "2020-01")
    # Present vs concrete date
    assert not dates_semantically_equal("heute", "2021-08")


def test_normalize_shapes() -> None:
    assert normalize_partial_date("02/2019") == ("ym", 2019, 2)
    assert normalize_partial_date("2019-02") == ("ym", 2019, 2)
    assert normalize_partial_date("2019") == ("y", 2019, None)
    assert normalize_partial_date("heute") == ("present", None, None)
    assert normalize_partial_date("") is None
    assert normalize_partial_date("ohne Abschluss") is None


if __name__ == "__main__":
    test_positive_equivalents()
    test_negative_non_equivalents()
    test_normalize_shapes()
    print("cv_date_normalize tests OK")
