"""pgeocode must not download when the offline geo bundle is unusable."""

from __future__ import annotations

import logging
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
    # Keep the valid info so the country-file gate is what rejects Nominatim.
    # A real ensure_active() would reseed and restore DE.txt.
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

    monkeypatch.setattr(geo_dataset, "bundled_geo_dir", lambda: real_bundle)
    reset_geo_dataset_manager_for_tests()
    good = resolve_postal_pgeocode("10115", "DE")
    assert good.ok
    assert good.latitude is not None and good.longitude is not None
    assert calls == []
