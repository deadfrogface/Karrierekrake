"""T08.05.05: every packaged graphic/template has a hash-bound origin."""
from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("asset_origins", ROOT / "scripts" / "asset_origins.py")
asset_origins = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(asset_origins)


def _copy_assets(tmp_path: Path) -> Path:
    for directory in asset_origins.SCAN_DIRS:
        shutil.copytree(ROOT / directory, tmp_path / directory)
    return tmp_path


def test_repository_assets_match_their_origins():
    report = asset_origins.check()
    assert report["problems"] == []
    assert {e["path"] for e in report["files"]} == set(asset_origins.packaged_files())


def test_unlisted_file_is_reported(tmp_path):
    root = _copy_assets(tmp_path)
    (root / "assets" / "brand" / "extra.png").write_bytes(b"x")
    assert "unlisted asset: assets/brand/extra.png" in asset_origins.check(root)["problems"]


def test_changed_file_is_reported(tmp_path):
    root = _copy_assets(tmp_path)
    (root / "assets" / "brand" / "logo.png").write_bytes(b"changed")
    problems = asset_origins.check(root)["problems"]
    assert any(p.startswith("hash mismatch: assets/brand/logo.png") for p in problems)


def test_missing_file_is_reported(tmp_path):
    root = _copy_assets(tmp_path)
    (root / "assets" / "brand" / "app.ico").unlink()
    assert "missing asset: assets/brand/app.ico" in asset_origins.check(root)["problems"]


def test_text_hash_ignores_line_endings(tmp_path):
    root = _copy_assets(tmp_path)
    path = root / "templates" / "cover_letter.txt"
    path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
    assert asset_origins.check(root)["problems"] == []
