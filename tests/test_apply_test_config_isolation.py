"""Apply-test must not persist dry_run/mode overrides via home_updated save."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from desktop.services import ConfigService


def _fake_dirs(tmp_path: Path):
    root = tmp_path / "Karrierekrake"
    dirs = {
        "root": root,
        "config": root / "config",
        "data": root / "data",
        "logs": root / "logs",
        "browser_profile": root / "browser_profile",
        "browsers": root / "browsers",
        "cvs": root / "cvs",
        "cache": root / "cache",
        "cover_letters": root / "cover_letters",
    }
    for p in dirs.values():
        p.mkdir(parents=True, exist_ok=True)
    return dirs


def test_apply_test_deepcopy_does_not_mutate_cached_config(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    from desktop import paths as paths_mod

    monkeypatch.setattr(paths_mod, "ensure_app_dirs", lambda: _fake_dirs(tmp_path))
    monkeypatch.setattr("desktop.services.ensure_app_dirs", lambda: _fake_dirs(tmp_path))

    svc = ConfigService()
    cfg = svc.load()
    cfg.settings.dry_run = False
    cfg.settings.mode = "fully_automatic"
    svc.save(cfg)

    # Simulate run_application_test: deepcopy then override.
    override = deepcopy(svc.load())
    override.settings.dry_run = True
    override.settings.mode = "review_before_submit"

    cached = svc.config
    assert cached.settings.dry_run is False
    assert cached.settings.mode == "fully_automatic"
    assert override.settings.dry_run is True
    assert override is not cached


def test_save_home_coords_from_does_not_persist_dry_run_or_mode(
    tmp_path: Path, monkeypatch
):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    from desktop import paths as paths_mod

    monkeypatch.setattr(paths_mod, "ensure_app_dirs", lambda: _fake_dirs(tmp_path))
    monkeypatch.setattr("desktop.services.ensure_app_dirs", lambda: _fake_dirs(tmp_path))

    svc = ConfigService()
    cfg = svc.load()
    cfg.settings.dry_run = False
    cfg.settings.mode = "fully_automatic"
    cfg.profile.location.home_address = "Musterstraße 1, 10115 Berlin"
    svc.save(cfg)

    # Worker config after apply-test: mutated dry_run/mode + new geocoded coords.
    run_cfg = deepcopy(svc.load())
    run_cfg.settings.dry_run = True
    run_cfg.settings.mode = "review_before_submit"
    run_cfg.profile.location.home_latitude = 52.52
    run_cfg.profile.location.home_longitude = 13.405

    assert not hasattr(svc, "save_home_coords_from")
    from core.home_coord_cache import cache_file

    assert not cache_file(svc.dirs["cache"]).exists()
    assert "home_latitude" not in svc.profile_path.read_text(encoding="utf-8")

    reloaded = svc.load()
    assert reloaded.settings.dry_run is False
    assert reloaded.settings.mode == "fully_automatic"
    assert reloaded.profile.location.home_latitude is None
    assert reloaded.profile.location.home_longitude is None
