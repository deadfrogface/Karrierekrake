"""Local BRouter road routing for Karrierekrake (Fahrstrecke).

Automatic start/stop of a local BRouter RouteServer (no user terminal).
Segment directory management, safe HTTP updates, cache layout, OSM attribution.

Driving-km queries return UNKNOWN on failure — never invent km and never
substitute airline distance as road kilometres.

Island / snap: when BRouter reports a disconnected snap ("target island
detected" / similar), retry with a general nearby-offset spiral on the
endpoints. No place-name special cases.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger("karrierekrake.road_route")

OSM_ATTRIBUTION = (
    "© OpenStreetMap contributors — ODbL. "
    "Routing: BRouter (local). Map data not Google."
)

DEFAULT_PROFILE = "car-fast"
DEFAULT_PORT = 17777
BROUTER_ENGINE_ID = "brouter_v1"

# 5°×5° BRouter tiles covering DE–NL–BE (lon 0–10, lat 45–55).
DEFAULT_SEGMENTS = ("E0_N45", "E0_N50", "E5_N45", "E5_N50")
SEGMENT_BASE_URL = "https://brouter.de/brouter/segments4"
BROUTER_JAR_URL = (
    "https://github.com/abrensch/brouter/releases/download/"
    "v1.7.10/brouter-1.7.10.zip"
)

# Spiral offsets in degrees (~111 m per 0.001° latitude).
_SNAP_RING_STEP_DEG = 0.001
_SNAP_MAX_RINGS = 6


@dataclass(frozen=True)
class RoadRouteResult:
    ok: bool
    distance_km: float | None
    engine: str = BROUTER_ENGINE_ID
    profile: str = DEFAULT_PROFILE
    error: str = ""
    attribution: str = OSM_ATTRIBUTION
    elapsed_s: float | None = None
    snap_offset_m: float | None = None

    @property
    def unknown(self) -> bool:
        return not self.ok or self.distance_km is None


def segment_filename(name: str) -> str:
    return name if name.endswith(".rd5") else f"{name}.rd5"


def segment_names_for_bbox(
    min_lon: float,
    min_lat: float,
    max_lon: float,
    max_lat: float,
) -> tuple[str, ...]:
    """BRouter 5° tile names covering a lon/lat bounding box."""
    names: set[str] = set()
    lon0 = int(min_lon // 5) * 5
    lon1 = int(max_lon // 5) * 5
    lat0 = int(min_lat // 5) * 5
    lat1 = int(max_lat // 5) * 5
    for lon in range(lon0, lon1 + 1, 5):
        for lat in range(lat0, lat1 + 1, 5):
            ew = "E" if lon >= 0 else "W"
            ns = "N" if lat >= 0 else "S"
            names.add(f"{ew}{abs(lon)}_{ns}{abs(lat)}")
    return tuple(sorted(names))


def ensure_segments(
    segment_dir: Path,
    names: tuple[str, ...] = DEFAULT_SEGMENTS,
    *,
    base_url: str = SEGMENT_BASE_URL,
    timeout_s: float = 600.0,
    force_update: bool = False,
) -> list[Path]:
    """Download missing .rd5 tiles. Optional Last-Modified refresh when force_update."""
    segment_dir.mkdir(parents=True, exist_ok=True)
    out: list[Path] = []
    for name in names:
        dest = segment_dir / segment_filename(name)
        if dest.exists() and dest.stat().st_size > 1_000_000 and not force_update:
            out.append(dest)
            continue
        url = f"{base_url.rstrip('/')}/{segment_filename(name)}"
        meta = dest.with_suffix(dest.suffix + ".meta.json")
        headers = {"User-Agent": "Karrierekrake/BRouterSetup"}
        if dest.exists() and meta.is_file() and force_update:
            try:
                prev = json.loads(meta.read_text(encoding="utf-8"))
                etag = str(prev.get("etag") or "").strip()
                last_mod = str(prev.get("last_modified") or "").strip()
                if etag:
                    headers["If-None-Match"] = etag
                if last_mod:
                    headers["If-Modified-Since"] = last_mod
            except (OSError, json.JSONDecodeError):
                pass
        logger.info("brouter_segment_download file=%s", dest.name)
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                if getattr(resp, "status", 200) == 304 and dest.exists():
                    out.append(dest)
                    continue
                data = resp.read()
                etag = resp.headers.get("ETag", "")
                last_mod = resp.headers.get("Last-Modified", "")
        except urllib.error.HTTPError as e:
            if e.code == 304 and dest.exists():
                out.append(dest)
                continue
            raise
        if len(data) < 1_000_000:
            raise RuntimeError(f"segment too small: {dest.name} ({len(data)} bytes)")
        tmp = dest.with_suffix(".partial")
        tmp.write_bytes(data)
        tmp.replace(dest)
        meta.write_text(
            json.dumps(
                {
                    "etag": etag,
                    "last_modified": last_mod,
                    "bytes": len(data),
                    "url": url,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        out.append(dest)
    return out


def _spiral_offsets(*, max_rings: int = _SNAP_MAX_RINGS) -> list[tuple[float, float]]:
    """(d_lon, d_lat) offsets, nearest first. Ring r uses step r * 0.001°."""
    out: list[tuple[float, float]] = [(0.0, 0.0)]
    for ring in range(1, max_rings + 1):
        d = _SNAP_RING_STEP_DEG * ring
        for dx, dy in (
            (d, 0.0),
            (-d, 0.0),
            (0.0, d),
            (0.0, -d),
            (d, d),
            (d, -d),
            (-d, d),
            (-d, -d),
        ):
            out.append((dx, dy))
    return out


def _is_island_or_snap_error(message: str) -> bool:
    text = (message or "").casefold()
    return any(
        needle in text
        for needle in (
            "island",
            "no track",
            "no route",
            "not found",
            "cannot find",
            "position not mapped",
            "no way",
        )
    )


def _offset_metres(d_lon: float, d_lat: float, *, lat: float) -> float:
    """Approximate ground distance of a lon/lat offset (metres)."""
    import math

    m_lat = abs(d_lat) * 111_320.0
    m_lon = abs(d_lon) * 111_320.0 * max(0.2, abs(math.cos(math.radians(lat))))
    return (m_lat**2 + m_lon**2) ** 0.5


def _query_once(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
    *,
    base_url: str,
    profile: str,
    timeout_s: float,
) -> tuple[bool, float | None, str, int]:
    """Single BRouter HTTP query. Returns (ok, km, error, http_code)."""
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
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Karrierekrake/BRouter"})
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            body = resp.read()
            code = int(getattr(resp, "status", 200) or 200)
    except urllib.error.HTTPError as e:
        err = e.read()[:300].decode("utf-8", errors="replace") if e.fp else str(e)
        return False, None, f"http_{e.code}:{err}", int(e.code)
    except Exception as e:  # noqa: BLE001
        return False, None, str(e), 0

    if code != 200:
        return False, None, body[:300].decode("utf-8", errors="replace"), code
    # Non-JSON error body with HTTP 200 (defensive)
    text_head = body[:80].decode("utf-8", errors="replace")
    if text_head.lstrip().startswith("{") is False and "island" in text_head.casefold():
        return False, None, text_head, code
    try:
        gj = json.loads(body)
        props = (gj.get("features") or [{}])[0].get("properties") or {}
        raw = props.get("track-length")
        dist_m = float(raw)
    except Exception as e:  # noqa: BLE001
        err = body[:300].decode("utf-8", errors="replace")
        if _is_island_or_snap_error(err):
            return False, None, err, code
        return False, None, f"parse:{e}", code
    if dist_m <= 0:
        return False, None, "empty_track", code
    return True, round(dist_m / 1000.0, 3), "", code


def route_driving_km(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
    *,
    base_url: str,
    profile: str = DEFAULT_PROFILE,
    timeout_s: float = 120.0,
    allow_snap_retry: bool = True,
) -> RoadRouteResult:
    """Query local BRouter. On failure return unknown — never invent distance.

    When the first attempt fails with an island/snap-style error, retry with a
    general nearby-offset spiral on destination, then origin, then both ends.
    """
    t0 = time.perf_counter()
    ok, km, err, _code = _query_once(
        lat1, lon1, lat2, lon2, base_url=base_url, profile=profile, timeout_s=timeout_s
    )
    if ok:
        return RoadRouteResult(
            ok=True,
            distance_km=km,
            profile=profile,
            elapsed_s=round(time.perf_counter() - t0, 3),
            snap_offset_m=0.0,
        )
    if not allow_snap_retry or not _is_island_or_snap_error(err):
        return RoadRouteResult(
            ok=False,
            distance_km=None,
            profile=profile,
            error=err or "route_failed",
            elapsed_s=round(time.perf_counter() - t0, 3),
        )

    offsets = _spiral_offsets()
    # Destination offsets (keep origin fixed)
    for d_lon, d_lat in offsets[1:]:
        ok2, km2, err2, _ = _query_once(
            lat1,
            lon1,
            lat2 + d_lat,
            lon2 + d_lon,
            base_url=base_url,
            profile=profile,
            timeout_s=timeout_s,
        )
        if ok2:
            return RoadRouteResult(
                ok=True,
                distance_km=km2,
                profile=profile,
                elapsed_s=round(time.perf_counter() - t0, 3),
                snap_offset_m=round(_offset_metres(d_lon, d_lat, lat=lat2), 1),
            )
        if err2 and not _is_island_or_snap_error(err2):
            # Hard failure (missing segment etc.) — stop spiral
            err = err2
            break
    else:
        # Origin offsets
        for d_lon, d_lat in offsets[1:]:
            ok2, km2, err2, _ = _query_once(
                lat1 + d_lat,
                lon1 + d_lon,
                lat2,
                lon2,
                base_url=base_url,
                profile=profile,
                timeout_s=timeout_s,
            )
            if ok2:
                return RoadRouteResult(
                    ok=True,
                    distance_km=km2,
                    profile=profile,
                    elapsed_s=round(time.perf_counter() - t0, 3),
                    snap_offset_m=round(_offset_metres(d_lon, d_lat, lat=lat1), 1),
                )
            if err2 and not _is_island_or_snap_error(err2):
                err = err2
                break
        else:
            # Both ends — limited combinations (first 3 rings)
            limited = _spiral_offsets(max_rings=3)[1:]
            for d_lon1, d_lat1 in limited:
                for d_lon2, d_lat2 in limited:
                    ok2, km2, err2, _ = _query_once(
                        lat1 + d_lat1,
                        lon1 + d_lon1,
                        lat2 + d_lat2,
                        lon2 + d_lon2,
                        base_url=base_url,
                        profile=profile,
                        timeout_s=timeout_s,
                    )
                    if ok2:
                        off = _offset_metres(d_lon1, d_lat1, lat=lat1) + _offset_metres(
                            d_lon2, d_lat2, lat=lat2
                        )
                        return RoadRouteResult(
                            ok=True,
                            distance_km=km2,
                            profile=profile,
                            elapsed_s=round(time.perf_counter() - t0, 3),
                            snap_offset_m=round(off, 1),
                        )
                    if err2:
                        err = err2

    return RoadRouteResult(
        ok=False,
        distance_km=None,
        profile=profile,
        error=err or "island_unresolved",
        elapsed_s=round(time.perf_counter() - t0, 3),
    )


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
        on_started: Callable[[subprocess.Popen[str]], None] | None = None,
    ) -> None:
        self.jar = Path(jar)
        self.segment_dir = Path(segment_dir)
        self.profile_dir = Path(profile_dir)
        self.custom_profile_dir = Path(custom_profile_dir or (segment_dir.parent / "customprofiles"))
        self.port = int(port)
        self.java_bin = java_bin
        self.xmx = xmx
        self._on_started = on_started
        self._proc: subprocess.Popen[str] | None = None
        self._lock = threading.Lock()

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    @property
    def pid(self) -> int | None:
        if self._proc and self._proc.poll() is None:
            return self._proc.pid
        return None

    def is_port_open(self) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.3)
            try:
                return s.connect_ex(("127.0.0.1", self.port)) == 0
            except OSError:
                return False

    def start(self, *, wait_s: float = 30.0) -> None:
        with self._lock:
            self.custom_profile_dir.mkdir(parents=True, exist_ok=True)
            if self.is_port_open():
                return
            if not self.jar.is_file():
                raise FileNotFoundError(f"BRouter jar missing: {self.jar}")
            if not self.profile_dir.is_dir():
                raise FileNotFoundError(f"BRouter profiles missing: {self.profile_dir}")
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
            if self._on_started is not None:
                try:
                    self._on_started(self._proc)
                except Exception:  # noqa: BLE001
                    logger.debug("brouter on_started callback failed", exc_info=True)
        deadline = time.time() + wait_s
        while time.time() < deadline:
            if self.is_port_open():
                return
            if self._proc is not None and self._proc.poll() is not None:
                raise RuntimeError("BRouter RouteServer exited during start")
            time.sleep(0.2)
        raise TimeoutError("BRouter RouteServer did not open port in time")

    def stop(self) -> None:
        with self._lock:
            proc = self._proc
            self._proc = None
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()


def default_runtime_dirs(root: Path | None = None) -> dict[str, Path]:
    """Suggested local data layout under the app data root."""
    if root is not None:
        base = Path(root)
    else:
        env = os.environ.get("KARRIEREKRAKE_BROUTER_DIR", "").strip()
        if env:
            base = Path(env)
        else:
            # Packaged Windows: prefer LOCALAPPDATA\Karrierekrake\brouter
            local = os.environ.get("LOCALAPPDATA", "").strip()
            if local:
                base = Path(local) / "Karrierekrake" / "brouter"
            else:
                base = Path.home() / ".karrierekrake" / "brouter"
    return {
        "root": base,
        "segments": base / "segments4",
        "profiles": base / "profiles2",
        "custom_profiles": base / "customprofiles",
        "jar": base / "brouter-all.jar",
        "cache": base / "cache",
    }


def find_java_bin() -> str:
    """Resolve a Java binary — bundled JRE first, then PATH."""
    env = os.environ.get("KARRIEREKRAKE_JAVA", "").strip()
    if env and Path(env).exists():
        return env
    dirs = default_runtime_dirs()
    for cand in (
        dirs["root"] / "jre" / "bin" / "java.exe",
        dirs["root"] / "jre" / "bin" / "java",
        dirs["root"] / "jdk" / "bin" / "java.exe",
        dirs["root"] / "jdk" / "bin" / "java",
    ):
        if cand.is_file():
            return str(cand)
    which = shutil.which("java")
    if which:
        return which
    return "java"


def ensure_brouter_install(
    *,
    root: Path | None = None,
    segment_names: tuple[str, ...] = DEFAULT_SEGMENTS,
    timeout_s: float = 600.0,
) -> dict[str, Path]:
    """Ensure jar, default car profiles, and required segments exist under runtime dirs."""
    dirs = default_runtime_dirs(root)
    dirs["root"].mkdir(parents=True, exist_ok=True)
    dirs["cache"].mkdir(parents=True, exist_ok=True)
    dirs["custom_profiles"].mkdir(parents=True, exist_ok=True)
    jar = dirs["jar"]
    if not jar.is_file() or jar.stat().st_size < 100_000:
        _download_brouter_distribution(dirs["root"], jar, timeout_s=timeout_s)
    if not dirs["profiles"].is_dir() or not any(dirs["profiles"].glob("*.brf")):
        _ensure_profiles_from_dist(dirs["root"], dirs["profiles"], timeout_s=timeout_s)
    ensure_segments(dirs["segments"], names=segment_names, timeout_s=timeout_s)
    attribution = dirs["root"] / "OSM_ATTRIBUTION.txt"
    if not attribution.is_file():
        attribution.write_text(OSM_ATTRIBUTION + "\n", encoding="utf-8")
    return dirs


def _download_brouter_distribution(root: Path, jar_dest: Path, *, timeout_s: float) -> None:
    """Download official BRouter release zip and extract all-jar + profiles."""
    import zipfile
    from io import BytesIO

    logger.info("brouter_jar_download url=%s", BROUTER_JAR_URL)
    req = urllib.request.Request(
        BROUTER_JAR_URL, headers={"User-Agent": "Karrierekrake/BRouterSetup"}
    )
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        data = resp.read()
    with zipfile.ZipFile(BytesIO(data)) as zf:
        jar_members = [
            n
            for n in zf.namelist()
            if n.endswith("-all.jar") or n.endswith("brouter.jar")
        ]
        if not jar_members:
            jar_members = [n for n in zf.namelist() if n.endswith(".jar")]
        if not jar_members:
            raise RuntimeError("BRouter zip has no jar")
        jar_dest.write_bytes(zf.read(jar_members[0]))
        # Extract profiles2/*
        for name in zf.namelist():
            norm = name.replace("\\", "/")
            if "/profiles2/" in norm or norm.endswith("/profiles2") or "/misc/profiles2/" in norm:
                if norm.endswith("/"):
                    continue
                rel = norm.split("profiles2/", 1)[-1]
                if not rel or rel.endswith("/"):
                    continue
                target = root / "profiles2" / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(zf.read(name))


def _ensure_profiles_from_dist(root: Path, profile_dir: Path, *, timeout_s: float) -> None:
    if profile_dir.is_dir() and any(profile_dir.glob("*.brf")):
        return
    # Re-download distribution if profiles missing
    jar = root / "brouter-all.jar"
    _download_brouter_distribution(root, jar, timeout_s=timeout_s)


class BRouterRuntime:
    """Process-wide BRouter lifecycle for the desktop app / EXE."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._server: BRouterServer | None = None
        self._dirs: dict[str, Path] | None = None
        self._enabled = True
        self._install_attempted = False

    @property
    def enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, value: bool) -> None:
        self._enabled = bool(value)

    def is_installed(self) -> bool:
        dirs = self._dirs or default_runtime_dirs()
        jar = dirs["jar"]
        profiles = dirs["profiles"]
        return jar.is_file() and jar.stat().st_size > 100_000 and profiles.is_dir()

    def ensure_install(
        self,
        *,
        segment_names: tuple[str, ...] | None = None,
        timeout_s: float = 600.0,
    ) -> dict[str, Path]:
        """Download jar/segments if needed. Call from app startup, not per job."""
        with self._lock:
            names = segment_names or DEFAULT_SEGMENTS
            dirs = ensure_brouter_install(segment_names=names, timeout_s=timeout_s)
            self._dirs = dirs
            self._install_attempted = True
            return dirs

    def ensure_ready(
        self,
        *,
        segment_names: tuple[str, ...] | None = None,
        wait_s: float = 45.0,
        allow_install: bool = False,
    ) -> BRouterServer:
        with self._lock:
            if not self._enabled:
                raise RuntimeError("BRouter disabled")
            names = segment_names or DEFAULT_SEGMENTS
            if allow_install or not self.is_installed():
                if allow_install:
                    dirs = ensure_brouter_install(segment_names=names)
                    self._dirs = dirs
                elif not self.is_installed():
                    raise RuntimeError("brouter_not_installed")
            dirs = self._dirs or default_runtime_dirs()
            # Ensure requested segment tiles exist when already installed.
            if self.is_installed():
                try:
                    ensure_segments(dirs["segments"], names=names, timeout_s=120.0)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("brouter segment ensure failed: %s", type(exc).__name__)

            def _register(proc: subprocess.Popen[str]) -> None:
                try:
                    from desktop.services.shutdown import get_shutdown_manager

                    get_shutdown_manager().register_process(proc)
                except Exception:  # noqa: BLE001
                    pass

            if self._server is None:
                self._server = BRouterServer(
                    jar=dirs["jar"],
                    segment_dir=dirs["segments"],
                    profile_dir=dirs["profiles"],
                    custom_profile_dir=dirs["custom_profiles"],
                    java_bin=find_java_bin(),
                    on_started=_register,
                )
            self._server.start(wait_s=wait_s)
            return self._server

    def route(
        self,
        lat1: float,
        lon1: float,
        lat2: float,
        lon2: float,
        *,
        profile: str = DEFAULT_PROFILE,
        timeout_s: float = 120.0,
        allow_install: bool = False,
    ) -> RoadRouteResult:
        try:
            names = segment_names_for_bbox(
                min(lon1, lon2), min(lat1, lat2), max(lon1, lon2), max(lat1, lat2)
            )
            if not names:
                names = DEFAULT_SEGMENTS
            merged = tuple(sorted(set(names) | set(DEFAULT_SEGMENTS)))
            server = self.ensure_ready(
                segment_names=merged, allow_install=allow_install
            )
        except Exception as e:  # noqa: BLE001
            return RoadRouteResult(ok=False, distance_km=None, error=f"start:{e}")
        return route_driving_km(
            lat1,
            lon1,
            lat2,
            lon2,
            base_url=server.base_url,
            profile=profile,
            timeout_s=timeout_s,
        )

    def stop(self) -> None:
        with self._lock:
            if self._server is not None:
                self._server.stop()
                self._server = None

    def status(self) -> dict[str, Any]:
        running = bool(self._server and self._server.is_port_open())
        return {
            "engine": BROUTER_ENGINE_ID,
            "enabled": self._enabled,
            "running": running,
            "installed": self.is_installed(),
            "port": self._server.port if self._server else DEFAULT_PORT,
            "dirs": {k: str(v) for k, v in (self._dirs or default_runtime_dirs()).items()},
            "attribution": OSM_ATTRIBUTION,
            "production_distance_filter": "airline_prefilter_then_brouter_road_km",
        }


_runtime: BRouterRuntime | None = None
_runtime_lock = threading.Lock()


def get_brouter_runtime() -> BRouterRuntime:
    global _runtime
    with _runtime_lock:
        if _runtime is None:
            _runtime = BRouterRuntime()
        return _runtime


def reset_brouter_runtime_for_tests() -> None:
    global _runtime
    with _runtime_lock:
        if _runtime is not None:
            try:
                _runtime.stop()
            except Exception:  # noqa: BLE001
                pass
        _runtime = None


def format_driving_km(distance_km: float | None, *, decimals: int = 0) -> str:
    """User-facing road-distance label — never Luftlinie."""
    if distance_km is None:
        return ""
    try:
        val = float(distance_km)
    except (TypeError, ValueError):
        return ""
    if not (val == val):  # NaN
        return ""
    if decimals <= 0:
        return f"ca. {int(round(val))} km Fahrstrecke"
    return f"ca. {val:.{decimals}f} km Fahrstrecke"


def format_driving_unknown(reason: str = "") -> str:
    reason = (reason or "").strip()
    if reason:
        return f"Fahrstrecke nicht bestimmbar ({reason})"
    return "Fahrstrecke nicht bestimmbar"


def describe_status(server: BRouterServer) -> dict[str, Any]:
    return {
        "engine": BROUTER_ENGINE_ID,
        "port": server.port,
        "running": server.is_port_open(),
        "attribution": OSM_ATTRIBUTION,
        "production_distance_filter": "airline_prefilter_then_brouter_road_km",
    }
