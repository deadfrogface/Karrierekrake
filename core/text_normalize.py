"""Domain-boundary text normalization (NaN / null / blank → empty).

Call at ingest and again at display / cover-letter boundaries so UI never
shows ``bei nan`` and matchers never treat placeholder tokens as evidence.
"""

from __future__ import annotations

import math
import re
from typing import Any

_BLANK_TOKENS = frozenset(
    {
        "",
        "nan",
        "none",
        "null",
        "n/a",
        "na",
        "undefined",
        "-",
        "--",
        "—",
        "unknown",
        "unbekannt",
        "nicht angegeben",
    }
)


def is_blankish(value: Any) -> bool:
    """True for None, NaN floats, and blank / placeholder strings."""
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    if isinstance(value, str):
        return value.strip().lower() in _BLANK_TOKENS
    text = str(value).strip()
    if not text:
        return True
    return text.lower() in _BLANK_TOKENS


def clean_text(value: Any, *, default: str = "") -> str:
    """Return stripped text or ``default`` when the value is blankish."""
    if is_blankish(value):
        return default
    if isinstance(value, float):
        # Avoid "12.0" for whole numbers; still reject nan via is_blankish.
        if value.is_integer():
            return str(int(value))
        return str(value).strip()
    return str(value).strip()


def clean_company(value: Any, *, fallback: str = "") -> str:
    """Normalize employer names; never return nan/null placeholders."""
    return clean_text(value, default=fallback)


def display_or_dash(value: Any) -> str:
    """UI helper: blankish → em dash."""
    text = clean_text(value)
    return text if text else "—"


_PHONE_CANDIDATE = re.compile(
    r"(?<!\w)(?:"
    r"\+\d{1,3}[\s\-./()]*(?:\d[\s\-./()]*){6,}\d"
    r"|"
    r"0\d[\s\-./()]*(?:\d[\s\-./()]*){5,}\d"
    r"|"
    r"\(0\d{2,4}\)[\s\-./]*(?:\d[\s\-./]*){4,}\d"
    r")"
)

# Dates / employment periods that the phone regex may falsely match.
_PHONE_DATE_FALSE = re.compile(
    r"(?:"
    r"\d{1,2}[./]\d{1,2}[./]\d{2,4}"  # DOB / calendar date
    r"|"
    r"\d{1,2}/\d{4}"  # MM/YYYY employment
    r"|"
    r"\d{4}\s*[-–—]\s*\d{4}"  # year range
    r")"
)


def extract_german_phones(text: str) -> list[str]:
    """Extract German-friendly phone numbers (incl. ``(0xxx) …`` layouts)."""
    found: list[str] = []
    for m in _PHONE_CANDIDATE.finditer(text or ""):
        raw = m.group(0).strip()
        if _PHONE_DATE_FALSE.search(raw):
            continue
        digits = re.sub(r"\D", "", raw)
        if len(digits) < 7 or len(digits) > 15:
            continue
        # Employment snippets like "01/2019 - 04/2022" leave only year digits.
        if re.search(r"(?i)\b(heute|present|current|seit)\b", raw):
            continue
        cleaned = re.sub(r"\s+", " ", raw).strip(" .-/")
        if cleaned not in found:
            found.append(cleaned)
    return found
