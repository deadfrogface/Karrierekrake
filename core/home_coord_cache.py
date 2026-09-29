"""Resolved search-home coordinates, outside profile.yaml.

The directory is always ``ConfigService.dirs["cache"]``. Callers pass that
path in. Nothing here builds an AppData path of its own.

One record. The key is exactly the arguments ``resolve_place`` receives
(normalized place, ``cross_border``, ``home_country``, ``allow_network``)
plus the geo-index version. The resolved country is stored beside the
coordinates and returned on a hit. A mismatch is ignored. The write is
atomic and skipped when the bytes would not change.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from core.geo_normalize import normalize_country_code, normalize_place_fields
from core.geo_resolve import geo_index_stamp

CACHE_FILENAME = "home_coordinates.json"


def cache_file(cache_dir: Path | str) -> Path:
    return Path(cache_dir) / CACHE_FILENAME


def cache_dir_of(config: Any) -> Path | None:
    raw = getattr(config, "home_coord_cache_dir", None)
    if not raw:
        return None
    return Path(raw)


def _fingerprint(text: str) -> str:
    return " ".join((text or "").strip().lower().split())


def normalized_home_place(location: Any):
    """The place object ``resolve_place`` receives for this home.

    An empty country stays empty. ``home_country`` is a separate argument.
    City and PLZ fallbacks are the same helpers ``location`` uses.
    """
    from core.location import _city_from_address, _plz_from_address

    address = (getattr(location, "home_address", "") or "").strip()
    postal = (getattr(location, "postal_code", "") or "").strip()
    city = (getattr(location, "city", "") or "").strip()
    country = (getattr(location, "country", "") or "").strip()
    return normalize_place_fields(
        address=address,
        city=city or _city_from_address(address),
        postal_code=postal or _plz_from_address(address),
        country_code=normalize_country_code(country),
    )


def home_disk_key(
    location: Any,
    *,
    cross_border: bool,
    home_country: str,
    allow_network: bool = False,
    geo_index: str | None = None,
) -> dict[str, Any]:
    """File key: ``resolve_place`` arguments plus the geo-index version."""
    place = normalized_home_place(location)
    home_cc = normalize_country_code(home_country) or "DE"
    return {
        "address": _fingerprint(place.address),
        "postal_code": place.postal_code,
        "city": _fingerprint(place.city),
        "country_code": place.country_code,
        "cross_border": bool(cross_border),
        "home_country": home_cc,
        "allow_network": bool(allow_network),
        "geo_index": geo_index if geo_index is not None else geo_index_stamp(),
    }


def _payload(
    location: Any,
    latitude: float,
    longitude: float,
    display_name: str = "",
    *,
    cross_border: bool,
    home_country: str,
    allow_network: bool = False,
    resolved_country: str = "",
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "key": home_disk_key(
            location,
            cross_border=cross_border,
            home_country=home_country,
            allow_network=allow_network,
        ),
        "latitude": float(latitude),
        "longitude": float(longitude),
        "resolved_country": normalize_country_code(resolved_country),
    }
    shown = (display_name or "").strip()
    if shown:
        data["display_name"] = shown
    return data


def _canonical(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"


def read_home_record(
    cache_dir: Path | str | None,
    location: Any,
    *,
    cross_border: bool = True,
    home_country: str = "",
    allow_network: bool = False,
) -> tuple[float, float, str, str] | None:
    """Coordinates, label and resolved country when the key matches."""
    if not cache_dir:
        return None
    path = cache_file(cache_dir)
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    home_cc = normalize_country_code(home_country) or normalize_country_code(
        getattr(location, "country", "") or ""
    ) or "DE"
    expected = home_disk_key(
        location,
        cross_border=cross_border,
        home_country=home_cc,
        allow_network=allow_network,
    )
    if data.get("key") != expected:
        return None
    try:
        lat = float(data["latitude"])
        lon = float(data["longitude"])
    except (KeyError, TypeError, ValueError):
        return None
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        return None
    shown = data.get("display_name")
    resolved = normalize_country_code(data.get("resolved_country") or "")
    return lat, lon, shown if isinstance(shown, str) else "", resolved


def read_home_coordinates(
    cache_dir: Path | str | None,
    location: Any,
    *,
    cross_border: bool = True,
    home_country: str = "",
    allow_network: bool = False,
) -> tuple[float, float] | None:
    """Return coordinates only when the stored key matches. Otherwise ignore."""
    record = read_home_record(
        cache_dir,
        location,
        cross_border=cross_border,
        home_country=home_country,
        allow_network=allow_network,
    )
    if record is None:
        return None
    return record[0], record[1]


def write_home_coordinates(
    cache_dir: Path | str | None,
    location: Any,
    latitude: float,
    longitude: float,
    display_name: str = "",
    *,
    cross_border: bool = True,
    home_country: str = "",
    allow_network: bool = False,
    resolved_country: str = "",
) -> bool:
    """Atomically replace the cache file. Return False when nothing changed."""
    if not cache_dir:
        return False
    path = cache_file(cache_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    home_cc = normalize_country_code(home_country) or normalize_country_code(
        getattr(location, "country", "") or ""
    ) or "DE"
    text = _canonical(
        _payload(
            location,
            latitude,
            longitude,
            display_name,
            cross_border=cross_border,
            home_country=home_cc,
            allow_network=allow_network,
            resolved_country=resolved_country,
        )
    )
    try:
        if path.is_file() and path.read_text(encoding="utf-8") == text:
            return False
    except OSError:
        pass
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)
    return True
