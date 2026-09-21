"""Versioned local DACH geo dataset (GeoNames postal codes via pgeocode layout).

No Karrierekrake server. Downloads (optional updates) go directly to the
documented GeoNames / postal-codes-data mirrors. Never send user addresses
or coordinates as query parameters.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger("karrierekrake.geo")

DACH_COUNTRIES = ("DE", "AT", "CH")
HAVERSINE_ALGORITHM = "haversine_v1"
EARTH_RADIUS_KM = 6371.0088

# Documented mirrors — same order as pgeocode; no Nominatim.
DOWNLOAD_URLS = (
    "https://download.geonames.org/export/zip/{country}.zip",
    "https://symerio.github.io/postal-codes-data/data/geonames/{country}.txt",
)

REQUIRED_COLUMNS = (
    "country_code",
    "postal_code",
    "place_name",
    "latitude",
    "longitude",
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def bundled_geo_dir() -> Path:
    """Shipped snapshot inside the repo / PyInstaller bundle."""
    # PyInstaller onefile extracts to sys._MEIPASS
    import sys

    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        cand = Path(meipass) / "data" / "geo"
        if (cand / "manifest.json").is_file():
            return cand
    return _repo_root() / "data" / "geo"


def user_geo_dir(config_root: Path | None = None) -> Path:
    """Writable active dataset (updates land here; never mutate the bundle)."""
    if config_root is not None:
        return Path(config_root) / "data" / "geo_active"
    env = os.environ.get("KARRIEREKRAKE_GEO_DATA_DIR", "").strip()
    if env:
        return Path(env)
    return Path.home() / ".cache" / "karrierekrake" / "geo"


@dataclass(frozen=True)
class GeoDatasetInfo:
    dataset_id: str
    version: str
    source: str
    source_url: str
    license: str
    attribution: str
    countries: tuple[str, ...]
    algorithm: str
    earth_radius_km: float
    path: Path
    valid: bool
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset_id": self.dataset_id,
            "version": self.version,
            "source": self.source,
            "source_url": self.source_url,
            "license": self.license,
            "attribution": self.attribution,
            "countries": list(self.countries),
            "algorithm": self.algorithm,
            "earth_radius_km": self.earth_radius_km,
            "path": str(self.path),
            "valid": self.valid,
            "message": self.message,
        }


def _read_manifest(path: Path) -> dict[str, Any] | None:
    mf = path / "manifest.json"
    if not mf.is_file():
        return None
    try:
        return json.loads(mf.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("geo manifest unreadable: %s", type(exc).__name__)
        return None


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def validate_country_file(path: Path, country: str) -> tuple[bool, str]:
    if not path.is_file():
        return False, f"missing {country}.txt"
    size = path.stat().st_size
    if size < 1024:
        return False, f"{country}.txt too small"
    if size > 50 * 1024 * 1024:
        return False, f"{country}.txt suspiciously large"
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            header = fh.readline()
            sample = [fh.readline() for _ in range(20)]
    except OSError as exc:
        return False, f"read error: {type(exc).__name__}"
    low = header.casefold()
    for col in REQUIRED_COLUMNS:
        if col not in low:
            # GeoNames raw zip uses tab-separated without header; pgeocode adds CSV header.
            if "\t" in header and header.count("\t") >= 10:
                break
            return False, f"missing column {col}"
    # Spot-check coordinates in sample rows when CSV-shaped
    if "," in header and "latitude" in low:
        parts_h = [p.strip() for p in header.split(",")]
        try:
            i_lat = parts_h.index("latitude")
            i_lon = parts_h.index("longitude")
            i_cc = parts_h.index("country_code")
        except ValueError:
            return False, "header columns incomplete"
        ok_rows = 0
        for line in sample:
            if not line.strip():
                continue
            cols = line.split(",")
            if len(cols) <= max(i_lat, i_lon, i_cc):
                continue
            if cols[i_cc].strip().upper() != country:
                continue
            try:
                lat = float(cols[i_lat])
                lon = float(cols[i_lon])
            except ValueError:
                continue
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                return False, f"out-of-range coords in {country}"
            ok_rows += 1
        if ok_rows == 0:
            return False, f"no valid sample rows for {country}"
    return True, "ok"


def validate_dataset(path: Path) -> tuple[bool, str]:
    mf = _read_manifest(path)
    if not mf:
        return False, "missing manifest"
    geo = path / "geonames"
    if not geo.is_dir():
        return False, "missing geonames/"
    for cc in DACH_COUNTRIES:
        ok, msg = validate_country_file(geo / f"{cc}.txt", cc)
        if not ok:
            return False, msg
        expected = ((mf.get("files") or {}).get(cc) or {}).get("sha256")
        if expected:
            actual = _sha256(geo / f"{cc}.txt")
            if actual != expected:
                return False, f"hash mismatch {cc}"
    return True, "ok"


def info_from_path(path: Path) -> GeoDatasetInfo:
    mf = _read_manifest(path) or {}
    ok, msg = validate_dataset(path)
    return GeoDatasetInfo(
        dataset_id=str(mf.get("dataset_id") or "unknown"),
        version=str(mf.get("version") or "unknown"),
        source=str(mf.get("source") or "geonames"),
        source_url=str(mf.get("source_url") or DOWNLOAD_URLS[0]),
        license=str(mf.get("license") or ""),
        attribution=str(mf.get("attribution") or "GeoNames.org"),
        countries=tuple(mf.get("countries") or DACH_COUNTRIES),
        algorithm=str(mf.get("algorithm") or HAVERSINE_ALGORITHM),
        earth_radius_km=float(mf.get("earth_radius_km") or EARTH_RADIUS_KM),
        path=path,
        valid=ok,
        message=msg,
    )


class GeoDatasetManager:
    """Ensure a valid local DACH snapshot; optional controlled update + rollback."""

    def __init__(self, config_root: Path | None = None) -> None:
        self.bundled = bundled_geo_dir()
        self.active_root = user_geo_dir(config_root)

    def ensure_active(self) -> GeoDatasetInfo:
        """Return active dataset, seeding from bundle if needed."""
        active = self.active_root
        if (active / "manifest.json").is_file():
            info = info_from_path(active)
            if info.valid:
                self._export_pgeocode_env(active)
                return info
            logger.warning("active geo dataset invalid (%s) — reseeding from bundle", info.message)
        return self._seed_from_bundle()

    def _seed_from_bundle(self) -> GeoDatasetInfo:
        src = self.bundled
        if not (src / "manifest.json").is_file():
            info = GeoDatasetInfo(
                dataset_id="missing",
                version="",
                source="",
                source_url="",
                license="",
                attribution="",
                countries=DACH_COUNTRIES,
                algorithm=HAVERSINE_ALGORITHM,
                earth_radius_km=EARTH_RADIUS_KM,
                path=src,
                valid=False,
                message="bundled geo snapshot missing",
            )
            return info
        self.active_root.parent.mkdir(parents=True, exist_ok=True)
        backup = self.active_root.with_name(self.active_root.name + ".bak")
        if backup.exists():
            shutil.rmtree(backup, ignore_errors=True)
        if self.active_root.exists():
            try:
                self.active_root.rename(backup)
            except OSError:
                shutil.rmtree(self.active_root, ignore_errors=True)
        shutil.copytree(src, self.active_root)
        info = info_from_path(self.active_root)
        if info.valid:
            self._export_pgeocode_env(self.active_root)
            shutil.rmtree(backup, ignore_errors=True)
        elif backup.exists():
            shutil.rmtree(self.active_root, ignore_errors=True)
            backup.rename(self.active_root)
            info = info_from_path(self.active_root)
            self._export_pgeocode_env(self.active_root)
        return info

    def current_info(self) -> GeoDatasetInfo:
        if (self.active_root / "manifest.json").is_file():
            return info_from_path(self.active_root)
        return info_from_path(self.bundled)

    @staticmethod
    def _export_pgeocode_env(dataset_path: Path) -> None:
        """Point pgeocode at our geonames/ directory (no silent Nominatim)."""
        geo = dataset_path / "geonames"
        os.environ["PGEOCODE_DATA_DIR"] = str(geo)

    def update_from_upstream(self, *, timeout_s: float = 60.0) -> GeoDatasetInfo:
        """Download DACH files to temp, validate, atomic activate; else keep old."""
        previous = self.ensure_active()
        tmp_root = Path(tempfile.mkdtemp(prefix="kk-geo-"))
        try:
            geo_dir = tmp_root / "geonames"
            geo_dir.mkdir(parents=True)
            files_meta: dict[str, Any] = {}
            for cc in DACH_COUNTRIES:
                dest = geo_dir / f"{cc}.txt"
                self._download_country(cc, dest, timeout_s=timeout_s)
                ok, msg = validate_country_file(dest, cc)
                if not ok:
                    raise RuntimeError(msg)
                files_meta[cc] = {
                    "path": f"geonames/{cc}.txt",
                    "sha256": _sha256(dest),
                    "bytes": dest.stat().st_size,
                }
            from datetime import date

            manifest = {
                "dataset_id": "dach-geonames-postal-v1",
                "version": f"{date.today().isoformat()}-geonames",
                "source": "geonames",
                "source_url": "https://download.geonames.org/export/zip/",
                "license": "Creative Commons Attribution 4.0 (GeoNames)",
                "attribution": "GeoNames.org — https://www.geonames.org/",
                "countries": list(DACH_COUNTRIES),
                "algorithm": HAVERSINE_ALGORITHM,
                "earth_radius_km": EARTH_RADIUS_KM,
                "files": files_meta,
            }
            (tmp_root / "manifest.json").write_text(
                json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
            )
            ok, msg = validate_dataset(tmp_root)
            if not ok:
                raise RuntimeError(msg)
            # Atomic swap via rename
            backup = self.active_root.parent / (self.active_root.name + ".prev")
            if backup.exists():
                shutil.rmtree(backup, ignore_errors=True)
            self.active_root.parent.mkdir(parents=True, exist_ok=True)
            if self.active_root.exists():
                self.active_root.rename(backup)
            shutil.copytree(tmp_root, self.active_root)
            info = info_from_path(self.active_root)
            if not info.valid:
                shutil.rmtree(self.active_root, ignore_errors=True)
                if backup.exists():
                    backup.rename(self.active_root)
                raise RuntimeError(info.message)
            shutil.rmtree(backup, ignore_errors=True)
            self._export_pgeocode_env(self.active_root)
            return info
        except Exception as exc:
            logger.warning("geo update failed — keeping previous: %s", type(exc).__name__)
            self._export_pgeocode_env(previous.path if previous.valid else self.bundled)
            return previous
        finally:
            shutil.rmtree(tmp_root, ignore_errors=True)

    def _download_country(self, country: str, dest: Path, *, timeout_s: float) -> None:
        last_err: Exception | None = None
        for template in DOWNLOAD_URLS:
            url = template.format(country=country)
            try:
                # No user PII in URL — country code only.
                req = urllib.request.Request(
                    url,
                    headers={"User-Agent": "Karrierekrake-GeoDataset/1.0 (local desktop)"},
                )
                with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                    data = resp.read()
                if url.endswith(".zip") or data[:2] == b"PK":
                    import zipfile
                    from io import BytesIO

                    with zipfile.ZipFile(BytesIO(data)) as zf:
                        names = [n for n in zf.namelist() if n.upper().endswith(".TXT")]
                        if not names:
                            raise RuntimeError("zip has no txt")
                        raw = zf.read(names[0])
                    # Convert GeoNames TSV to pgeocode CSV header format
                    dest.write_text(self._tsv_to_pgeocode_csv(raw), encoding="utf-8")
                else:
                    text = data.decode("utf-8", errors="replace")
                    if not text.lstrip().lower().startswith("country_code"):
                        dest.write_text(
                            self._tsv_to_pgeocode_csv(data), encoding="utf-8"
                        )
                    else:
                        dest.write_bytes(data)
                return
            except Exception as exc:
                last_err = exc
                continue
        raise RuntimeError(f"download failed for {country}: {last_err}")

    @staticmethod
    def _tsv_to_pgeocode_csv(raw: bytes) -> str:
        header = ",".join(
            [
                "country_code",
                "postal_code",
                "place_name",
                "state_name",
                "state_code",
                "county_name",
                "county_code",
                "community_name",
                "community_code",
                "latitude",
                "longitude",
                "accuracy",
            ]
        )
        lines = [header]
        for line in raw.decode("utf-8", errors="replace").splitlines():
            if not line.strip() or line.startswith("country"):
                continue
            parts = line.split("\t")
            if len(parts) < 12:
                continue
            # Escape commas in fields by stripping problematic commas
            cleaned = [p.replace(",", " ").strip() for p in parts[:12]]
            lines.append(",".join(cleaned))
        return "\n".join(lines) + "\n"


_manager: GeoDatasetManager | None = None


def get_geo_dataset_manager(config_root: Path | None = None) -> GeoDatasetManager:
    global _manager
    if _manager is None or config_root is not None:
        _manager = GeoDatasetManager(config_root)
    return _manager


def reset_geo_dataset_manager_for_tests() -> None:
    global _manager
    _manager = None
