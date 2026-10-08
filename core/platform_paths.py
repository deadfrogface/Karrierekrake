"""Writable user data locations shared by all desktop platforms."""
from __future__ import annotations

import os
import sys
from pathlib import Path


def user_data_dir() -> Path:
    override = os.environ.get("KARRIEREKRAKE_DATA_DIR", "").strip()
    if override:
        path = Path(override).expanduser()
        if not path.is_absolute():
            raise ValueError("KARRIEREKRAKE_DATA_DIR must be absolute")
        return path
    # Preserve the explicit isolation mechanism used by existing CI/tests.
    local = os.environ.get("LOCALAPPDATA", "").strip()
    if local:
        return Path(local) / "Karrierekrake"
    if sys.platform == "win32":
        return Path.home() / "AppData" / "Local" / "Karrierekrake"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Karrierekrake"
    xdg = Path(os.environ.get("XDG_DATA_HOME", "")).expanduser()
    base = xdg if xdg.is_absolute() else Path.home() / ".local" / "share"
    return base / "Karrierekrake"
