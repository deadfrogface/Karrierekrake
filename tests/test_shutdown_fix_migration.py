"""Shutdown-fix migration must not recurse, and must retry if the commit fails."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from desktop.services import ConfigService


def _isolate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    from desktop import paths as paths_mod

    def fake_dirs() -> dict[str, Path]:
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
            "models": root / "models",
        }
        for path in dirs.values():
            path.mkdir(parents=True, exist_ok=True)
        return dirs

    monkeypatch.setattr(paths_mod, "ensure_app_dirs", fake_dirs)
    monkeypatch.setattr("desktop.services.ensure_app_dirs", fake_dirs)
    return tmp_path / "Karrierekrake"


def _meta_text(svc: ConfigService) -> str:
    if not svc.meta_path.exists():
        return ""
    return svc.meta_path.read_text(encoding="utf-8")


def test_fresh_profile_load_does_not_recurse_shutdown_migration(tmp_path, monkeypatch):
    """Loading a fresh profile runs the shutdown migration once and does not recurse."""
    _isolate(tmp_path, monkeypatch)
    load_calls = {"n": 0}
    meta_writes = {"n": 0}
    recursion_errors: list[str] = []

    orig_load = ConfigService.load
    orig_save_meta = ConfigService.save_meta

    def counting_load(self: ConfigService) -> object:
        load_calls["n"] += 1
        return orig_load(self)

    def counting_save_meta(self: ConfigService, meta: dict) -> None:
        meta_writes["n"] += 1
        return orig_save_meta(self, meta)

    monkeypatch.setattr(ConfigService, "load", counting_load)
    monkeypatch.setattr(ConfigService, "save_meta", counting_save_meta)

    def _trace(frame, event, arg):
        if event == "exception" and arg and arg[0] is RecursionError:
            recursion_errors.append(frame.f_code.co_name)
        return _trace

    svc = ConfigService()
    previous_limit = sys.getrecursionlimit()
    previous_trace = sys.gettrace()
    # Low enough that the old save()->load() cycle hits RecursionError quickly,
    # high enough for one real load (YAML + dataclasses).
    sys.setrecursionlimit(400)
    sys.settrace(_trace)
    try:
        cfg = svc.load()
    finally:
        sys.settrace(previous_trace)
        sys.setrecursionlimit(previous_limit)

    assert recursion_errors == []
    assert load_calls["n"] == 1
    assert meta_writes["n"] == 1
    text = _meta_text(svc)
    assert text.count("shutdown_fix_v1") == 1
    meta = json.loads(text)
    assert meta["shutdown_fix_v1"] is True
    assert cfg.settings.minimize_to_tray is False

    load_calls["n"] = 0
    again = svc.load()
    assert load_calls["n"] == 1
    assert meta_writes["n"] == 1
    assert _meta_text(svc).count("shutdown_fix_v1") == 1
    assert again.settings.minimize_to_tray is False

    again.settings.language = "en"
    saved = svc.save(again)
    assert load_calls["n"] == 1
    assert saved.settings.language == "en"
    assert svc.load().settings.language == "en"
    assert load_calls["n"] == 2


def test_shutdown_fix_migration_retries_when_commit_fails_midway(tmp_path, monkeypatch):
    """A failed commit must not persist the flag; the next load runs the migration again."""
    _isolate(tmp_path, monkeypatch)
    import desktop.services as services_mod

    real_save_config = services_mod.save_config
    calls = {"n": 0}

    def fail_midway(*args, **kwargs):
        calls["n"] += 1
        raise OSError("migration commit failed midway")

    monkeypatch.setattr(services_mod, "save_config", fail_midway)
    svc = ConfigService()
    with pytest.raises(OSError, match="midway"):
        svc.load()

    assert calls["n"] == 1
    assert "shutdown_fix_v1" not in _meta_text(svc)
    assert not svc.load_meta().get("shutdown_fix_v1")

    monkeypatch.setattr(services_mod, "save_config", real_save_config)
    cfg = svc.load()
    text = _meta_text(svc)
    assert text.count("shutdown_fix_v1") == 1
    assert json.loads(text)["shutdown_fix_v1"] is True
    assert cfg.settings.minimize_to_tray is False

    cfg.settings.minimize_to_tray = True
    svc.save(cfg)
    kept = svc.load()
    assert kept.settings.minimize_to_tray is True
    assert _meta_text(svc).count("shutdown_fix_v1") == 1


def test_save_meta_keeps_previous_file_if_replace_fails(tmp_path, monkeypatch):
    """A failure after the temp file is written must leave the old meta.json readable."""
    _isolate(tmp_path, monkeypatch)
    import desktop.services as services_mod

    svc = ConfigService()
    original = {
        "first_run_completed": True,
        "shutdown_fix_v1": True,
        "note": "alt",
    }
    svc.save_meta(original)
    assert json.loads(svc.meta_path.read_text(encoding="utf-8")) == original

    def abort_replace(src, dst):
        assert Path(src).is_file()
        assert Path(src).read_text(encoding="utf-8")
        raise OSError("replace aborted after temp write")

    monkeypatch.setattr(services_mod.os, "replace", abort_replace)
    with pytest.raises(OSError, match="replace aborted after temp write"):
        svc.save_meta(
            {
                "first_run_completed": False,
                "shutdown_fix_v1": False,
                "note": "neu",
            }
        )

    again = json.loads(svc.meta_path.read_text(encoding="utf-8"))
    assert again == original
    tmp = svc.meta_path.with_suffix(svc.meta_path.suffix + ".tmp")
    assert json.loads(tmp.read_text(encoding="utf-8"))["note"] == "neu"


def test_existing_profile_with_shutdown_flag_keeps_minimize_to_tray(tmp_path, monkeypatch):
    """Profiles that already recorded the migration keep the user's tray setting."""
    _isolate(tmp_path, monkeypatch)
    svc = ConfigService()
    settings = svc.settings_path.read_text(encoding="utf-8")
    assert "minimize_to_tray:" in settings
    svc.settings_path.write_text(
        settings.replace("minimize_to_tray: false", "minimize_to_tray: true"),
        encoding="utf-8",
    )
    meta = svc.load_meta()
    meta["shutdown_fix_v1"] = True
    meta["first_run_completed"] = True
    svc.save_meta(meta)

    cfg = svc.load()
    assert cfg.settings.minimize_to_tray is True
    assert svc.load_meta()["shutdown_fix_v1"] is True
    assert svc.load_meta()["first_run_completed"] is True

    cfg.settings.language = "en"
    saved = svc.save(cfg)
    assert saved.settings.language == "en"
    assert saved.settings.minimize_to_tray is True
    reloaded = svc.load()
    assert reloaded.settings.language == "en"
    assert reloaded.settings.minimize_to_tray is True
