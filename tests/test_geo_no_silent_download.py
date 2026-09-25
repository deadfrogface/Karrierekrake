"""pgeocode must not download when the offline geo bundle is unusable."""

from __future__ import annotations

import logging
import os
import socket
import urllib.request
from pathlib import Path

import pytest

from core import geo_dataset
from core.geo_dataset import (
    bundled_geo_dir,
    get_geo_dataset_manager,
    reset_geo_dataset_manager_for_tests,
)
from core.geo_resolve import reset_pgeocode_index_for_tests, resolve_postal_pgeocode


@pytest.fixture(autouse=True)
def _isolate_geo_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    reset_geo_dataset_manager_for_tests()
    reset_pgeocode_index_for_tests()
    monkeypatch.delenv("PGEOCODE_DATA_DIR", raising=False)
    monkeypatch.setenv("KARRIEREKRAKE_GEO_DATA_DIR", str(tmp_path / "geo_active"))
    yield
    reset_geo_dataset_manager_for_tests()
    reset_pgeocode_index_for_tests()


def _block_downloads(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Record every pgeocode download entry point and refuse the call."""
    calls: list[str] = []

    def _blocked(*args, **kwargs):
        if args:
            target = str(args[0])
        else:
            target = str(kwargs.get("url") or "<network>")
        calls.append(target)
        raise RuntimeError(f"blocked network call: {target}")

    monkeypatch.setattr(urllib.request, "urlopen", _blocked)
    import pgeocode

    monkeypatch.setattr(pgeocode, "_open_extract_url", _blocked)
    monkeypatch.setattr(pgeocode, "_open_extract_cycle_url", _blocked)
    try:
        import requests
    except ImportError:
        requests = None
    if requests is not None:
        monkeypatch.setattr(requests, "get", _blocked)
        monkeypatch.setattr(requests.sessions.Session, "request", _blocked)
    return calls


def _assert_unresolved(res) -> None:
    assert res.status == "UNKNOWN"
    assert not res.ok
    assert res.latitude is None
    assert res.longitude is None
    assert res.data_source == "unresolved"


def test_missing_bundle_does_not_download(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog
):
    caplog.set_level(logging.WARNING, logger="karrierekrake")
    calls = _block_downloads(monkeypatch)
    empty = tmp_path / "empty_bundle"
    empty.mkdir()
    active = tmp_path / "active"
    monkeypatch.setenv("KARRIEREKRAKE_GEO_DATA_DIR", str(active))
    monkeypatch.setattr(geo_dataset, "bundled_geo_dir", lambda: empty)
    reset_geo_dataset_manager_for_tests()
    reset_pgeocode_index_for_tests()
    info = get_geo_dataset_manager().ensure_active()
    assert info.valid is False

    import pgeocode

    stale = tmp_path / "stale_cache"
    stale.mkdir()
    pgeocode.STORAGE_DIR = str(stale)

    res = resolve_postal_pgeocode("10115", "DE")
    again = resolve_postal_pgeocode("10115", "DE")
    _assert_unresolved(res)
    _assert_unresolved(again)
    assert res.reason == "pgeocode_unavailable"
    assert calls == []
    refused = [
        rec
        for rec in caplog.records
        if rec.levelno == logging.WARNING
        and "refusing silent pgeocode download" in rec.getMessage()
    ]
    assert len(refused) == 1


def test_missing_country_file_does_not_download(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog
):
    caplog.set_level(logging.WARNING, logger="karrierekrake")
    calls = _block_downloads(monkeypatch)
    active = tmp_path / "active"
    monkeypatch.setenv("KARRIEREKRAKE_GEO_DATA_DIR", str(active))
    reset_geo_dataset_manager_for_tests()
    reset_pgeocode_index_for_tests()
    mgr = get_geo_dataset_manager()
    info = mgr.ensure_active()
    assert info.valid, info.message
    country = Path(info.path) / "geonames" / "DE.txt"
    assert country.is_file()
    country.unlink()
    # Manifest cache stays valid after the delete. Pin ensure_active so a
    # reseed cannot restore DE.txt before the country-file stat runs.
    monkeypatch.setattr(mgr, "ensure_active", lambda: info)

    import pgeocode

    stale = tmp_path / "stale_cache"
    stale.mkdir()
    pgeocode.STORAGE_DIR = str(stale)

    res = resolve_postal_pgeocode("10115", "DE")
    again = resolve_postal_pgeocode("10115", "DE")
    _assert_unresolved(res)
    _assert_unresolved(again)
    assert res.reason == "pgeocode_unavailable"
    assert calls == []
    refused = [
        rec
        for rec in caplog.records
        if rec.levelno == logging.WARNING
        and "refusing silent pgeocode download" in rec.getMessage()
    ]
    assert len(refused) == 1

    at = resolve_postal_pgeocode("6900", "AT")
    assert at.ok
    assert at.latitude is not None and at.longitude is not None
    assert calls == []
    assert (
        Path(pgeocode.STORAGE_DIR).resolve() == (Path(info.path) / "geonames").resolve()
    )


def test_valid_bundle_resolves_offline_with_network_blocked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    calls = _block_downloads(monkeypatch)
    active = tmp_path / "active"
    monkeypatch.setenv("KARRIEREKRAKE_GEO_DATA_DIR", str(active))
    reset_geo_dataset_manager_for_tests()
    reset_pgeocode_index_for_tests()

    import pgeocode

    # Import-time STORAGE_DIR must not win over the active dataset.
    stale = tmp_path / "stale_cache"
    stale.mkdir()
    pgeocode.STORAGE_DIR = str(stale)

    res = resolve_postal_pgeocode("10115", "DE")
    assert res.ok
    assert res.status == "RESOLVED"
    assert res.latitude is not None and res.longitude is not None
    assert res.data_source == "geonames"
    assert calls == []
    geonames = Path(get_geo_dataset_manager().ensure_active().path) / "geonames"
    assert Path(pgeocode.STORAGE_DIR).resolve() == geonames.resolve()
    assert (geonames / "DE.txt").is_file()
    assert bundled_geo_dir().joinpath("manifest.json").is_file()


def test_invalid_dataset_does_not_stick_when_bundle_appears(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """A failed lookup must not cache None and block a later valid dataset."""
    calls = _block_downloads(monkeypatch)
    empty = tmp_path / "empty_bundle"
    empty.mkdir()
    active = tmp_path / "active"
    monkeypatch.setenv("KARRIEREKRAKE_GEO_DATA_DIR", str(active))
    real_bundle = geo_dataset.bundled_geo_dir()
    monkeypatch.setattr(geo_dataset, "bundled_geo_dir", lambda: empty)
    reset_geo_dataset_manager_for_tests()
    reset_pgeocode_index_for_tests()

    bad = resolve_postal_pgeocode("10115", "DE")
    _assert_unresolved(bad)
    assert calls == []
    from core import geo_resolve

    assert "DE" not in geo_resolve._pgeocode_index
    assert all(value is not None for value in geo_resolve._pgeocode_index.values())

    monkeypatch.setattr(geo_dataset, "bundled_geo_dir", lambda: real_bundle)
    reset_geo_dataset_manager_for_tests()
    good = resolve_postal_pgeocode("10115", "DE")
    assert good.ok
    assert good.latitude is not None and good.longitude is not None
    assert calls == []


_LINE_A = 'DE,10115,Berlin,Berlin,BE,,0.0,"Berlin, Stadt",11000.0,52.5323,13.3846,6.0'
_LINE_B = 'DE,10115,Berlin,Berlin,BE,,0.0,"Berlin, Stadt",11000.0,48.1111,13.3846,6.0'


def _ready_dataset(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    active = tmp_path / "active"
    monkeypatch.setenv("KARRIEREKRAKE_GEO_DATA_DIR", str(active))
    reset_geo_dataset_manager_for_tests()
    reset_pgeocode_index_for_tests()
    info = get_geo_dataset_manager().ensure_active()
    assert info.valid, info.message
    return info


def _count_nominatim(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    import pgeocode

    constructed: list[str] = []
    original = pgeocode.Nominatim

    class _Counting(original):
        def __init__(self, country: str = "fr", unique: bool = True) -> None:
            constructed.append(str(country).upper())
            super().__init__(country, unique=unique)

    monkeypatch.setattr(pgeocode, "Nominatim", _Counting)
    return constructed


def _write_country_from_active(
    active: Path, country: str, dest: Path, *, variant_b: bool
) -> None:
    text = (active / "geonames" / f"{country}.txt").read_text(encoding="utf-8")
    if variant_b and country == "DE":
        assert _LINE_A in text
        text = text.replace(_LINE_A, _LINE_B, 1)
    dest.write_text(text, encoding="utf-8")


def test_two_resolutions_construct_nominatim_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _block_downloads(monkeypatch)
    constructed = _count_nominatim(monkeypatch)
    _ready_dataset(tmp_path, monkeypatch)
    first = resolve_postal_pgeocode("10115", "DE")
    second = resolve_postal_pgeocode("01067", "DE")
    assert first.ok and second.ok
    assert constructed == ["DE"]


def test_resolution_does_not_hash_active_dataset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _block_downloads(monkeypatch)
    _ready_dataset(tmp_path, monkeypatch)
    hashes = {"n": 0}
    real = geo_dataset._sha256

    def _counting(path: Path) -> str:
        hashes["n"] += 1
        return real(path)

    monkeypatch.setattr(geo_dataset, "_sha256", _counting)
    for _ in range(5):
        res = resolve_postal_pgeocode("10115", "DE")
        assert res.ok
    assert hashes["n"] == 0


def test_dataset_b_is_used_and_nominatim_is_built_once_more(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _block_downloads(monkeypatch)
    constructed = _count_nominatim(monkeypatch)
    info = _ready_dataset(tmp_path, monkeypatch)
    first = resolve_postal_pgeocode("10115", "DE")
    second = resolve_postal_pgeocode("10115", "DE")
    assert first.ok and second.ok
    assert constructed == ["DE"]
    assert first.latitude == pytest.approx(52.5323, abs=1e-4)

    def _download(self, country: str, dest: Path, timeout_s: float = 60.0) -> None:
        del self, timeout_s
        _write_country_from_active(info.path, country, dest, variant_b=True)

    monkeypatch.setattr(geo_dataset.GeoDatasetManager, "_download_country", _download)
    updated = get_geo_dataset_manager().update_from_upstream()
    assert updated.valid
    assert updated.version != info.version

    third = resolve_postal_pgeocode("10115", "DE")
    assert third.ok
    assert third.latitude == pytest.approx(48.1111, abs=1e-4)
    assert third.data_version == updated.version
    assert constructed == ["DE", "DE"]

    fourth = resolve_postal_pgeocode("10115", "DE")
    assert fourth.latitude == pytest.approx(third.latitude)
    assert constructed == ["DE", "DE"]


def test_rollback_drops_nominatim_and_keeps_dataset_a(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _block_downloads(monkeypatch)
    constructed = _count_nominatim(monkeypatch)
    info = _ready_dataset(tmp_path, monkeypatch)
    first = resolve_postal_pgeocode("10115", "DE")
    assert first.ok
    assert constructed == ["DE"]
    active = info.path

    def _download(self, country: str, dest: Path, timeout_s: float = 60.0) -> None:
        del self, timeout_s
        _write_country_from_active(active, country, dest, variant_b=False)

    real_info = geo_dataset.info_from_path

    def _force_invalid(path: Path):
        loaded = real_info(path)
        if path == active:
            from dataclasses import replace

            return replace(loaded, valid=False, message="forced rollback")
        return loaded

    monkeypatch.setattr(geo_dataset.GeoDatasetManager, "_download_country", _download)
    monkeypatch.setattr(geo_dataset, "info_from_path", _force_invalid)
    after = get_geo_dataset_manager().update_from_upstream()
    assert after.valid
    assert after.version == info.version

    again = resolve_postal_pgeocode("10115", "DE")
    assert again.ok
    assert again.latitude == pytest.approx(first.latitude)
    assert constructed == ["DE", "DE"]


_COUNTRY_FILES = {"DE.txt", "AT.txt", "CH.txt"}


def _track_country_stats(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    seen: list[str] = []
    real_stat = os.stat

    def _counting(path, *args, **kwargs):
        base = os.path.basename(os.fspath(path))
        if base in _COUNTRY_FILES:
            seen.append(base)
        return real_stat(path, *args, **kwargs)

    monkeypatch.setattr(os, "stat", _counting)
    return seen


def test_country_file_is_stat_once_per_dataset_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """One fresh stat per index build. A cleared index stats once more."""
    _block_downloads(monkeypatch)
    _ready_dataset(tmp_path, monkeypatch)
    stats = _track_country_stats(monkeypatch)
    from core import geo_resolve

    geo_dataset.invalidate_dataset_caches()
    first = resolve_postal_pgeocode("10115", "DE")
    second = resolve_postal_pgeocode("01067", "DE")
    assert first.ok and second.ok
    assert stats == ["DE.txt"]
    assert "DE" in geo_resolve._pgeocode_index

    geo_dataset.invalidate_dataset_caches()
    third = resolve_postal_pgeocode("10115", "DE")
    fourth = resolve_postal_pgeocode("10115", "DE")
    assert third.ok and fourth.ok
    assert stats == ["DE.txt", "DE.txt"]


def test_deleted_country_file_does_not_connect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Warm validation cache, missing DE.txt, no socket and no cached None."""
    _ready_dataset(tmp_path, monkeypatch)
    info = get_geo_dataset_manager().ensure_active()
    assert info.valid
    country = Path(info.path) / "geonames" / "DE.txt"
    original = country.read_bytes()
    country.unlink()
    assert get_geo_dataset_manager().ensure_active().valid

    attempts = {"connect": 0, "dns": 0}
    stats = _track_country_stats(monkeypatch)

    def _blocked_connect(self, address):
        del address
        if self.family in (socket.AF_INET, socket.AF_INET6):
            attempts["connect"] += 1
        raise OSError("network blocked")

    def _blocked_dns(*args, **kwargs):
        del args, kwargs
        attempts["dns"] += 1
        raise OSError("dns blocked")

    monkeypatch.setattr(socket.socket, "connect", _blocked_connect)
    monkeypatch.setattr(socket, "getaddrinfo", _blocked_dns)

    from core import geo_resolve

    first = resolve_postal_pgeocode("10115", "DE")
    second = resolve_postal_pgeocode("80331", "DE")
    _assert_unresolved(first)
    _assert_unresolved(second)
    assert first.reason == "pgeocode_unavailable"
    assert attempts == {"connect": 0, "dns": 0}
    assert stats == ["DE.txt", "DE.txt"]
    assert "DE" not in geo_resolve._pgeocode_index
    assert all(value is not None for value in geo_resolve._pgeocode_index.values())

    country.write_bytes(original)
    repaired = resolve_postal_pgeocode("10115", "DE")
    assert repaired.ok
    assert repaired.latitude == pytest.approx(52.5323, abs=1e-4)
    assert stats == ["DE.txt", "DE.txt", "DE.txt"]
    assert attempts == {"connect": 0, "dns": 0}
    again = resolve_postal_pgeocode("10115", "DE")
    assert again.ok
    assert stats == ["DE.txt", "DE.txt", "DE.txt"]
