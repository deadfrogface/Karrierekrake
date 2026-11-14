"""Postal codes and place names of one country, read from the local GeoNames file.

The table is a plain CSV (see ``GeoDatasetManager._tsv_to_pgeocode_csv`` for the columns). It is read with the
standard library: no pandas, no pgeocode, and no code in here that can open a network connection. A missing
or unreadable file is an error for the caller; nothing is ever fetched to replace it.

Results are the ones the earlier pgeocode-based lookup gave:

* a postal code resolves to the mean of the coordinates of all its rows, and its place name is the names of
  those rows joined by ``", "`` in file order;
* a place name matches rows whose name is equal to it after ``str.casefold``.
"""
from __future__ import annotations

import csv
import math
import os
from dataclasses import dataclass

_COLUMNS = ("postal_code", "place_name", "latitude", "longitude")
# Cells that mean "no value", as in the table reader used before (a place called "Null" stays unnamed).
_NO_VALUE = frozenset({
    "", "#N/A", "#N/A N/A", "#NA", "-1.#IND", "-1.#QNAN", "-NaN", "-nan", "1.#IND", "1.#QNAN", "<NA>", "N/A",
    "NA", "NULL", "NaN", "None", "n/a", "nan", "null",
})


@dataclass(frozen=True)
class PostalRow:
    """Answer for one postal code. ``latitude`` and ``longitude`` are NaN when the code is unknown."""

    latitude: float
    longitude: float
    place_name: str


_UNKNOWN = PostalRow(math.nan, math.nan, "")


def _number(cell: str) -> float | None:
    if cell in _NO_VALUE:
        return None
    try:
        value = float(cell)
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def _mean(values: list[float]) -> float:
    return math.fsum(values) / len(values) if values else math.nan


class PostalIndex:
    """Lookup by postal code and by exact place name for one country file."""

    def __init__(self, rows: list[tuple[str, str, float | None, float | None]], data_path: str = "") -> None:
        """``rows`` are ``(postal_code, place_name, latitude, longitude)`` in file order."""
        self._data_path = data_path
        by_code: dict[str, list[tuple[str, float | None, float | None]]] = {}
        places: dict[str, list[tuple[str, float | None, float | None]]] = {}
        for code, name, lat, lon in rows:
            by_code.setdefault(code, []).append((name, lat, lon))
            places.setdefault(name.casefold(), []).append((name, lat, lon))
        self._postal: dict[str, PostalRow] = {
            code: PostalRow(
                _mean([lat for _n, lat, _l in group if lat is not None]),
                _mean([lon for _n, _l, lon in group if lon is not None]),
                ", ".join(name for name, _a, _b in group),
            )
            for code, group in by_code.items()
        }
        self._places = places
        self._folded_names = tuple(places)

    @classmethod
    def load(cls, path: str | os.PathLike[str]) -> "PostalIndex":
        """Read one country file. Raises ``OSError`` or ``ValueError`` when it cannot be used."""
        data_path = os.fspath(path)
        rows: list[tuple[str, str, float | None, float | None]] = []
        with open(data_path, encoding="utf-8", newline="") as handle:
            reader = csv.reader(handle)
            header = next(reader, None)
            if header is None:
                raise ValueError("empty postal table")
            try:
                code_at, name_at, lat_at, lon_at = (header.index(column) for column in _COLUMNS)
            except ValueError as exc:
                raise ValueError("postal table without the expected columns") from exc
            width = max(code_at, name_at, lat_at, lon_at) + 1
            for cells in reader:
                if len(cells) < width:
                    continue
                code = cells[code_at]
                if code in _NO_VALUE:
                    continue
                name = cells[name_at]
                rows.append((code, "nan" if name in _NO_VALUE else name, _number(cells[lat_at]), _number(cells[lon_at])))
        return cls(rows, data_path)

    def query_postal_code(self, code: str) -> PostalRow:
        return self._postal.get(str(code or "").strip().upper(), _UNKNOWN)

    def exact_places(self, folded_name: str) -> list[tuple[str, float | None, float | None]]:
        """Rows ``(place_name, latitude, longitude)`` whose casefolded name equals ``folded_name``."""
        return list(self._places.get(folded_name, ()))

    def names_containing(self, folded_part: str) -> set[str]:
        """Distinct casefolded place names that contain ``folded_part``."""
        return {name for name in self._folded_names if name and folded_part in name}
