"""Isolated product environment for full-product E2E (temp AppData + DB)."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from core.config import AppConfig
from core.database import Database
from core.search_intent import SearchIntent, Strictness
from desktop.services import ConfigService
from tests.e2e.gates import ProductGates


@dataclass
class E2EEnv:
    root: Path
    svc: ConfigService
    cfg: AppConfig
    db: Database
    gates: ProductGates
    tmp_path: Path

    def reload(self) -> AppConfig:
        self.cfg = self.svc.load()
        self.db = Database(self.cfg.db_path)
        return self.cfg

    def save(self) -> None:
        self.svc.save(self.cfg)
        self.cfg = self.svc.load()


def isolate_app_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point LOCALAPPDATA + ensure_app_dirs at an isolated temp tree."""
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
        for p in dirs.values():
            p.mkdir(parents=True, exist_ok=True)
        return dirs

    monkeypatch.setattr(paths_mod, "ensure_app_dirs", fake_dirs)
    monkeypatch.setattr("desktop.services.ensure_app_dirs", fake_dirs)
    return tmp_path / "Karrierekrake"


def make_e2e_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> E2EEnv:
    root = isolate_app_dirs(tmp_path, monkeypatch)
    svc = ConfigService()
    cfg = svc.load()
    # Safety defaults for every E2E session.
    cfg.settings.dry_run = True
    cfg.settings.mode = "search_only"
    svc.save(cfg)
    cfg = svc.load()
    db = Database(cfg.db_path)
    return E2EEnv(
        root=root,
        svc=svc,
        cfg=cfg,
        db=db,
        gates=ProductGates(),
        tmp_path=tmp_path,
    )


def apply_persona(env: E2EEnv, persona: dict[str, Any]) -> None:
    """Apply a synthetic persona profile + search intent onto the env."""
    app = env.cfg.application
    profile = persona.get("profile") or {}
    for key, value in profile.items():
        if hasattr(app, key):
            setattr(app, key, value)
    intent_data = persona.get("search_intent") or {}
    strictness = intent_data.get("strictness")
    if isinstance(strictness, str):
        try:
            strictness = Strictness(strictness)
        except Exception:
            strictness = Strictness.BALANCED
    env.cfg.profile.search_intent = SearchIntent(
        target_roles=list(intent_data.get("target_roles") or []),
        mandatory_skills=list(intent_data.get("mandatory_skills") or []),
        preferred_skills=list(intent_data.get("preferred_skills") or []),
        excluded_skills=list(intent_data.get("excluded_skills") or []),
        countries=list(intent_data.get("countries") or ["DE"]),
        radius_km=intent_data.get("radius_km"),
        remote_mode=intent_data.get("remote_mode"),
        salary_min=intent_data.get("salary_min"),
        strictness=strictness or Strictness.BALANCED,
    )
    env.save()


def snapshot_case_statuses(db: Database) -> dict[str, str]:
    return {c.id: c.status for c in db.list_cases()}


def assert_statuses_unchanged(
    before: dict[str, str], after: dict[str, str], *, except_ids: set[str] | None = None
) -> None:
    except_ids = except_ids or set()
    for cid, status in before.items():
        if cid in except_ids:
            continue
        assert after.get(cid) == status, f"cross-case mutation on {cid}"
