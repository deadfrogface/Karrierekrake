"""Resolved search-home coordinates, outside profile.yaml.

The directory is always ``ConfigService.dirs["cache"]``. Callers pass that
path in. Nothing here builds an AppData path of its own.

One record. The key is the normalized address, postal code, city, country
and the geo-index version. A mismatch is ignored. The write is atomic and
skipped when the bytes would not change.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from core.geo_normalize import normalize_country_code
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


def home_cache_key(location: Any, *, geo_index: str | None = None) -> dict[str, str]:
    address = (getattr(location, "home_address", "") or "").strip()
    postal = (getattr(location, "postal_code", "") or "").strip()
    city = (getattr(location, "city", "") or "").strip()
    country = normalize_country_code(getattr(location, "country", "") or "") or "DE"
    return {
        "address": _fingerprint(address),
        "postal_code": postal,
        "city": _fingerprint(city),
        "country": country,
        "geo_index": geo_index if geo_index is not None else geo_index_stamp(),
    }


def _payload(
    location: Any, latitude: float, longitude: float, display_name: str = ""
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "key": home_cache_key(location),
        "latitude": float(latitude),
        "longitude": float(longitude),
    }
    shown = (display_name or "").strip()
    if shown:
        data["display_name"] = shown
    return data


def _canonical(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"


def read_home_record(
    cache_dir: Path | str | None, location: Any
) -> tuple[float, float, str] | None:
    """Coordinates and the place label, only when the stored key matches."""
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
    stored = data.get("key")
    if stored != home_cache_key(location):
        return None
    try:
        lat = float(data["latitude"])
        lon = float(data["longitude"])
    except (KeyError, TypeError, ValueError):
        return None
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        return None
    shown = data.get("display_name")
    return lat, lon, shown if isinstance(shown, str) else ""


def read_home_coordinates(
    cache_dir: Path | str | None, location: Any
) -> tuple[float, float] | None:
    """Return coordinates only when the stored key matches. Otherwise ignore."""
    record = read_home_record(cache_dir, location)
    if record is None:
        return None
    return record[0], record[1]


def write_home_coordinates(
    cache_dir: Path | str | None,
    location: Any,
    latitude: float,
    longitude: float,
    display_name: str = "",
) -> bool:
    """Atomically replace the cache file. Return False when nothing changed."""
    if not cache_dir:
        return False
    path = cache_file(cache_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = _canonical(_payload(location, latitude, longitude, display_name))
    try:
        if path.is_file() and path.read_text(encoding="utf-8") == text:
            return False
    except OSError:
        pass
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)
    return True
