"""Replace NEXT-05 Google Maps suite — Maps must stay gone."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest


def test_integrations_maps_removed():
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("integrations.maps")
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("integrations.maps.proxy")


def test_no_maps_key_env_in_examples():
    root = Path(__file__).resolve().parents[1]
    for name in (".env.example", "config/settings.yaml.example", "config/settings.yaml"):
        path = root / name
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        assert "GOOGLE_MAPS" not in text
        assert "MAPS_API_KEY" not in text


def test_location_module_is_local_first():
    src = (Path(__file__).resolve().parents[1] / "core" / "location.py").read_text(
        encoding="utf-8"
    )
    assert "integrations.maps" not in src
    assert "haversine" in src.lower() or "HAVERSINE" in src
    assert "get_maps_service" not in src
