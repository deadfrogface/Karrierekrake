"""DACH country / place field normalization (DE, AT, CH).

No tax, visa, or legal advice. Normalization is string/ISO only.
Ambiguous places must stay UNKNOWN — never invent coordinates or distances.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal

# ISO 3166-1 alpha-2 used by Karrierekrake for commute math.
DACH_COUNTRY_CODES = frozenset({"DE", "AT", "CH"})

ResolutionStatus = Literal["RESOLVED", "UNKNOWN", "AMBIGUOUS"]

# Source/display aliases → ISO. Names only; no invented jurisdiction rules.
_COUNTRY_ALIASES: dict[str, str] = {
    "de": "DE",
    "deu": "DE",
    "ger": "DE",
    "germany": "DE",
    "deutschland": "DE",
    "bundesrepublik deutschland": "DE",
    "federal republic of germany": "DE",
    "at": "AT",
    "aut": "AT",
    "austria": "AT",
    "österreich": "AT",
    "oesterreich": "AT",
    "osterreich": "AT",
    "republik österreich": "AT",
    "ch": "CH",
    "che": "CH",
    "switzerland": "CH",
    "schweiz": "CH",
    "suisse": "CH",
    "svizzera": "CH",
    "swiss confederation": "CH",
    "schweizerische eidgenossenschaft": "CH",
}

_COUNTRY_TOKEN_RE = re.compile(
    r"(?i)(?:"
    r"\b(?:deutschland|germany|österreich|oesterreich|osterreich|austria|"
    r"schweiz|switzerland|suisse|svizzera)\b|"
    r"\((?:de|at|ch)\)"
    r")"
)

# PLZ patterns (structural only — do not claim uniqueness without country).
_PLZ_DE_RE = re.compile(r"^\d{5}$")
_PLZ_AT_CH_RE = re.compile(r"^\d{4}$")


def normalize_country_code(value: Any, *, default: str = "") -> str:
    """Map free-text / ISO / source labels to DE|AT|CH or empty.

    Empty means unknown — callers must not invent a country.
    """
    if value is None:
        return default
    text = str(value).strip()
    if not text:
        return default
    # Strip punctuation wrappers: "(DE)", "DE,", "CH."
    cleaned = text.strip("()[]{},.;: ").casefold()
    cleaned = " ".join(cleaned.split())
    if cleaned in _COUNTRY_ALIASES:
        return _COUNTRY_ALIASES[cleaned]
    # Two-letter ISO already
    if len(cleaned) == 2 and cleaned.upper() in DACH_COUNTRY_CODES:
        return cleaned.upper()
    # Trailing ", Germany" style
    for alias, iso in _COUNTRY_ALIASES.items():
        if cleaned.endswith(alias) or cleaned.startswith(alias):
            # Prefer whole-token match
            parts = re.split(r"[\s,/|-]+", cleaned)
            if alias in parts or any(p == alias for p in parts):
                return iso
    return default


def extract_country_hint(*texts: str) -> str:
    """Best-effort country hint from free text. Empty if none / conflicting."""
    found: set[str] = set()
    for raw in texts:
        if not raw:
            continue
        blob = str(raw)
        for m in _COUNTRY_TOKEN_RE.finditer(blob):
            tok = m.group(0).casefold()
            if tok in {"deutschland", "germany"} or tok == "(de)":
                found.add("DE")
            elif tok in {
                "österreich",
                "oesterreich",
                "osterreich",
                "austria",
            } or tok == "(at)":
                found.add("AT")
            elif tok in {
                "schweiz",
                "switzerland",
                "suisse",
                "svizzera",
            } or tok == "(ch)":
                found.add("CH")
        # ISO suffix after comma: "Konstanz, DE"
        for part in re.split(r"[,;/|]", blob):
            code = normalize_country_code(part.strip())
            if code:
                found.add(code)
    if len(found) == 1:
        return next(iter(found))
    return ""


def normalize_postal_code(value: Any, *, country_code: str = "") -> str:
    """Strip and keep digits for DACH PLZ; empty if blank/unusable."""
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    digits = re.sub(r"\D", "", text)
    cc = normalize_country_code(country_code)
    if cc == "DE":
        return digits if _PLZ_DE_RE.match(digits) else digits
    if cc in {"AT", "CH"}:
        return digits if _PLZ_AT_CH_RE.match(digits) else digits
    # Unknown country: accept 4 or 5 digit forms only
    if _PLZ_DE_RE.match(digits) or _PLZ_AT_CH_RE.match(digits):
        return digits
    return digits if digits else ""


def plz_candidate_countries(postal_code: str) -> list[str]:
    """Countries where this PLZ shape is structurally valid.

    Same numeric PLZ can exist in AT and CH (e.g. 6900) — callers must
    disambiguate; this only lists structural candidates.
    """
    digits = re.sub(r"\D", "", str(postal_code or ""))
    if _PLZ_DE_RE.match(digits):
        return ["DE"]
    if _PLZ_AT_CH_RE.match(digits):
        return ["AT", "CH"]
    return []


def normalize_city_name(value: Any) -> str:
    """Light Unicode-safe city cleanup (no synonym invention)."""
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    # Collapse whitespace; keep umlauts / ß
    text = " ".join(text.split())
    # Drop trailing country tokens when present as ", Schweiz"
    parts = [p.strip() for p in text.split(",") if p.strip()]
    if len(parts) >= 2:
        last_cc = normalize_country_code(parts[-1])
        if last_cc:
            parts = parts[:-1]
        text = ", ".join(parts)
    return text


@dataclass(frozen=True)
class NormalizedPlace:
    """Normalized user/job place fields for resolution + cache keys."""

    city: str = ""
    postal_code: str = ""
    address: str = ""
    country_code: str = ""  # DE|AT|CH|""
    latitude: float | None = None
    longitude: float | None = None
    remote_type: str = ""

    @property
    def has_coords(self) -> bool:
        return self.latitude is not None and self.longitude is not None

    @property
    def is_remote(self) -> bool:
        return (self.remote_type or "").casefold() == "remote"


def normalize_place_fields(
    *,
    city: str = "",
    postal_code: str = "",
    address: str = "",
    country: str = "",
    country_code: str = "",
    latitude: float | None = None,
    longitude: float | None = None,
    remote_type: str = "",
    description: str = "",
) -> NormalizedPlace:
    """Normalize source/user place fields without inventing missing data."""
    cc = normalize_country_code(country_code) or normalize_country_code(country)
    if not cc:
        cc = extract_country_hint(address, city, description, country)
    city_n = normalize_city_name(city)
    plz = normalize_postal_code(postal_code, country_code=cc)
    addr = " ".join(str(address or "").split()).strip()
    # Pull PLZ/city from address when fields empty (common JobSpy shape)
    if not plz and addr:
        m5 = re.search(r"\b(\d{5})\b", addr)
        m4 = re.search(r"\b(\d{4})\b", addr)
        if m5 and (not cc or cc == "DE"):
            plz = m5.group(1)
            if not cc:
                cc = "DE"
        elif m4 and (not cc or cc in {"AT", "CH"}):
            plz = m4.group(1)
    if not city_n and addr:
        # First segment often city for "Kreuzlingen, Switzerland"
        city_n = normalize_city_name(addr.split(",")[0])
    lat = longitude_ok = None
    try:
        lat = float(latitude) if latitude is not None else None
    except (TypeError, ValueError):
        lat = None
    try:
        longitude_ok = float(longitude) if longitude is not None else None
    except (TypeError, ValueError):
        longitude_ok = None
    if lat is not None and not (-90.0 <= lat <= 90.0):
        lat = None
    if longitude_ok is not None and not (-180.0 <= longitude_ok <= 180.0):
        longitude_ok = None
    if lat is None or longitude_ok is None:
        lat, longitude_ok = None, None
    return NormalizedPlace(
        city=city_n,
        postal_code=plz,
        address=addr,
        country_code=cc,
        latitude=lat,
        longitude=longitude_ok,
        remote_type=(remote_type or "").strip().lower(),
    )


def dach_countries_for_intent(
    countries: list[str],
    *,
    cross_border_enabled: bool,
    home_country: str = "DE",
) -> list[str]:
    """When cross-border is on and home is DACH, treat DE/AT/CH as in-scope.

    Does not claim commercial AT/CH job-board coverage — only commute geography.
    """
    if not cross_border_enabled:
        return list(countries)
    home = normalize_country_code(home_country) or "DE"
    if home not in DACH_COUNTRY_CODES:
        return list(countries)
    if not countries:
        return ["DE", "AT", "CH"]
    normalized = [normalize_country_code(c) for c in countries]
    normalized = [c for c in normalized if c]
    if not normalized:
        return ["DE", "AT", "CH"]
    # If user listed any DACH country, expand to full DACH for radius math.
    if any(c in DACH_COUNTRY_CODES for c in normalized):
        out = sorted(DACH_COUNTRY_CODES)
        return out
    return normalized


def source_location_blob_to_fields(blob: str) -> dict[str, str]:
    """Parse common ATS/JobSpy location strings into city/plz/country fields."""
    raw = " ".join(str(blob or "").split()).strip()
    if not raw:
        return {"city": "", "postal_code": "", "country_code": "", "address": ""}
    cc = extract_country_hint(raw)
    plz = ""
    m5 = re.search(r"\b(\d{5})\b", raw)
    m4 = re.search(r"\b(\d{4})\b", raw)
    if m5:
        plz = m5.group(1)
        if not cc:
            cc = "DE"
    elif m4:
        plz = m4.group(1)
    city = normalize_city_name(raw.split(",")[0])
    return {
        "city": city,
        "postal_code": plz,
        "country_code": cc,
        "address": raw,
    }
