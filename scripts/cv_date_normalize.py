"""Date equivalence for CV scoring (Scorer V3.1).

Does NOT modify Scorer V2 or COMPLETE_GT_ONLY_V3 historical results.
Semantically equal calendar months in different spellings count as equal;
different months/years or missing values do not.
"""

from __future__ import annotations

import re
from typing import Any

_PRESENT = frozenset(
    {
        "heute",
        "present",
        "current",
        "aktuell",
        "now",
        "ongoing",
        "bis heute",
        "to present",
        "till present",
    }
)


def _digits(s: str) -> str:
    return re.sub(r"\D", "", s or "")


def normalize_partial_date(value: Any) -> tuple[str, int | None, int | None] | None:
    """Normalize a CV date token.

    Returns:
      ("ym", year, month) for year-month
      ("y", year, None) for year-only
      ("present", None, None) for ongoing/present markers
      None if empty / unparseable
    """
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    low = s.lower().replace("–", "-").replace("—", "-")
    if low in _PRESENT:
        return ("present", None, None)

    # MM/YYYY or M/YYYY
    m = re.fullmatch(r"(\d{1,2})/(\d{4})", s)
    if m:
        month, year = int(m.group(1)), int(m.group(2))
        if 1 <= month <= 12:
            return ("ym", year, month)

    # MM.YYYY
    m = re.fullmatch(r"(\d{1,2})\.(\d{4})", s)
    if m:
        month, year = int(m.group(1)), int(m.group(2))
        if 1 <= month <= 12:
            return ("ym", year, month)

    # YYYY-MM or YYYY/MM
    m = re.fullmatch(r"(\d{4})[-/](\d{1,2})", s)
    if m:
        year, month = int(m.group(1)), int(m.group(2))
        if 1 <= month <= 12:
            return ("ym", year, month)

    # YYYY-MM-DD → year-month (day ignored for employment spans)
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        year, month = int(m.group(1)), int(m.group(2))
        if 1 <= month <= 12:
            return ("ym", year, month)

    # Year only
    m = re.fullmatch(r"(\d{4})", s)
    if m:
        return ("y", int(m.group(1)), None)

    return None


def dates_semantically_equal(expected: Any, actual: Any) -> bool:
    """True iff both denote the same year-month, same year-only, or both present.

    Negative by design:
    - empty vs non-empty → False
    - year-only vs year-month → False (insufficient precision match)
    - different month/year → False
    - unparseable free text (e.g. 'ohne Abschluss') vs empty → False
    """
    pe = normalize_partial_date(expected)
    pa = normalize_partial_date(actual)
    if pe is None or pa is None:
        return False
    if pe[0] == "present" and pa[0] == "present":
        return True
    if pe[0] == "ym" and pa[0] == "ym":
        return pe[1] == pa[1] and pe[2] == pa[2]
    if pe[0] == "y" and pa[0] == "y":
        return pe[1] == pa[1]
    return False
