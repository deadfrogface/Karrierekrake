"""Application data paths under %LOCALAPPDATA%\\Karrierekrake.

On first launch after upgrade, legacy AppData may be migrated once via
``desktop.legacy_migration`` (isolated legacy folder recognition).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from desktop.branding import DATA_DIR_NAME
from desktop.legacy_migration import migrate_legacy_appdata_if_needed

APP_NAME = DATA_DIR_NAME


def project_root() -> Path:
    """Source tree root (or frozen bundle root)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def app_data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    canonical = Path(base) / APP_NAME
    # Skip migration when tests/CI point LOCALAPPDATA at an isolated temp tree
    # that already is the intended root parent — still run migrate (cheap/idempotent).
    path = migrate_legacy_appdata_if_needed(canonical)
    path.mkdir(parents=True, exist_ok=True)
    return path


def ensure_app_dirs() -> dict[str, Path]:
    root = app_data_dir()
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
