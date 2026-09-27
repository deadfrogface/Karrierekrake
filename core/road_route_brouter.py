"""Optional local BRouter road routing (opt-in; NOT wired into production distance filter).

Karrierekrake continues to use Haversine airline distance for the live radius
filter until a separate product decision enables road-km. This module provides:

- automatic start/stop of a local BRouter RouteServer (no user terminal)
- segment directory management + documented OSM attribution
- driving-km queries that return UNKNOWN on failure (never invent km)

Measurements: see docs/project/ROAD_DISTANCE_BAKEOFF.md (Agent-VM bakeoff).
"""

from __future__ import annotations

import json
import logging
import os
import socket
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger("karrierekrake.road_route")

OSM_ATTRIBUTION = (
    "© OpenStreetMap contributors — ODbL. "
    "Routing: BRouter (local). Map data not Google."
)

DEFAULT_PROFILE = "car-fast"
DEFAULT_PORT = 17777

# 5°×5° BRouter tiles covering DE–NL–BE bakeoff region (lon 0–10, lat 45–55).
DEFAULT_SEGMENTS = ("E0_N45", "E0_N50", "E5_N45", "E5_N50")
SEGMENT_BASE_URL = "https://brouter.de/brouter/segments4"


@dataclass(frozen=True)
class RoadRouteResult:
    ok: bool
    distance_km: float | None
    engine: str = "brouter"
    profile: str = DEFAULT_PROFILE
    error: str = ""
    attribution: str = OSM_ATTRIBUTION
    elapsed_s: float | None = None

    @property
    def unknown(self) -> bool:
        return not self.ok or self.distance_km is None


def segment_filename(name: str) -> str:
    return name if name.endswith(".rd5") else f"{name}.rd5"


def ensure_segments(
    segment_dir: Path,
    names: tuple[str, ...] = DEFAULT_SEGMENTS,
    *,
    base_url: str = SEGMENT_BASE_URL,
    timeout_s: float = 600.0,
) -> list[Path]:
    """Download missing .rd5 tiles. No silent cloud use during routing — call at setup."""
    segment_dir.mkdir(parents=True, exist_ok=True)
    out: list[Path] = []
    for name in names:
        dest = segment_dir / segment_filename(name)
        if dest.exists() and dest.stat().st_size > 1_000_000:
            out.append(dest)
            continue
        url = f"{base_url.rstrip('/')}/{segment_filename(name)}"
        logger.info("brouter_segment_download file=%s", dest.name)
        req = urllib.request.Request(url, headers={"User-Agent": "Karrierekrake/BRouterSetup"})
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            data = resp.read()
        tmp = dest.with_suffix(".partial")
        tmp.write_bytes(data)
        tmp.replace(dest)
        out.append(dest)
    return out


class BRouterServer:
    """Manage a local BRouter RouteServer child process."""

    def __init__(
        self,
        *,
        jar: Path,
        segment_dir: Path,
        profile_dir: Path,
        custom_profile_dir: Path | None = None,
        port: int = DEFAULT_PORT,
        java_bin: str = "java",
        xmx: str = "512M",
    ) -> None:
        self.jar = Path(jar)
        self.segment_dir = Path(segment_dir)
        self.profile_dir = Path(profile_dir)
        self.custom_profile_dir = Path(custom_profile_dir or (segment_dir.parent / "customprofiles"))
        self.port = int(port)
        self.java_bin = java_bin
        self.xmx = xmx
        self._proc: subprocess.Popen[str] | None = None

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def is_port_open(self) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.3)
            try:
                return s.connect_ex(("127.0.0.1", self.port)) == 0
            except OSError:
                return False

    def start(self, *, wait_s: float = 30.0) -> None:
        self.custom_profile_dir.mkdir(parents=True, exist_ok=True)
        if self.is_port_open():
            return
        if not self.jar.is_file():
            raise FileNotFoundError(f"BRouter jar missing: {self.jar}")
        cmd = [
            self.java_bin,
            f"-Xmx{self.xmx}",
            "-cp",
            str(self.jar),
            "btools.server.RouteServer",
            str(self.segment_dir),
            str(self.profile_dir),
            str(self.custom_profile_dir),
            str(self.port),
            "2",
        ]
        self._proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        deadline = time.time() + wait_s
        while time.time() < deadline:
            if self.is_port_open():
                return
            if self._proc.poll() is not None:
                raise RuntimeError("BRouter RouteServer exited during start")
            time.sleep(0.2)
        raise TimeoutError("BRouter RouteServer did not open port in time")

    def stop(self) -> None:
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        self._proc = None


def route_driving_km(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
    *,
    base_url: str,
    profile: str = DEFAULT_PROFILE,
    timeout_s: float = 120.0,
) -> RoadRouteResult:
    """Query local BRouter. On failure return unknown — never invent distance."""
    lonlats = f"{lon1},{lat1}|{lon2},{lat2}"
    q = urllib.parse.urlencode(
        {
            "lonlats": lonlats,
            "profile": profile,
            "alternativeidx": "0",
            "format": "geojson",
        }
    )
    url = f"{base_url.rstrip('/')}/brouter?{q}"
    t0 = time.perf_counter()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Karrierekrake/BRouter"})
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            body = resp.read()
            code = resp.status
    except urllib.error.HTTPError as e:
        err = e.read()[:300].decode("utf-8", errors="replace") if e.fp else str(e)
        return RoadRouteResult(ok=False, distance_km=None, error=f"http_{e.code}:{err}", elapsed_s=time.perf_counter() - t0)
    except Exception as e:  # noqa: BLE001
        return RoadRouteResult(ok=False, distance_km=None, error=str(e), elapsed_s=time.perf_counter() - t0)

    elapsed = time.perf_counter() - t0
    if code != 200:
        return RoadRouteResult(ok=False, distance_km=None, error=body[:300].decode("utf-8", errors="replace"), elapsed_s=elapsed)
    try:
        gj = json.loads(body)
        props = (gj.get("features") or [{}])[0].get("properties") or {}
        raw = props.get("track-length")
        dist_m = float(raw)
    except Exception as e:  # noqa: BLE001
        return RoadRouteResult(ok=False, distance_km=None, error=f"parse:{e}", elapsed_s=elapsed)
    if dist_m <= 0:
        return RoadRouteResult(ok=False, distance_km=None, error="empty_track", elapsed_s=elapsed)
    return RoadRouteResult(ok=True, distance_km=round(dist_m / 1000.0, 3), elapsed_s=round(elapsed, 3))


def default_runtime_dirs(root: Path | None = None) -> dict[str, Path]:
    """Suggested local data layout under the app data root."""
    base = Path(root or os.environ.get("KARRIEREKRAKE_BROUTER_DIR") or Path.home() / ".karrierekrake" / "brouter")
    return {
        "root": base,
        "segments": base / "segments4",
        "profiles": base / "profiles2",
        "custom_profiles": base / "customprofiles",
        "jar": base / "brouter-all.jar",
    }


def describe_status(server: BRouterServer) -> dict[str, Any]:
    return {
        "engine": "brouter",
        "port": server.port,
        "running": server.is_port_open(),
        "attribution": OSM_ATTRIBUTION,
        "production_distance_filter": "unchanged_airline_haversine_v1",
    }
