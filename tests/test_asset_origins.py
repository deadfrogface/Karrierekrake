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


def _sbom(path: Path, assets: dict[str, str]) -> Path:
    import json

    path.write_text(json.dumps({"components": [
        {"name": name.replace("/", "\\"), "bom-ref": "asset:" + name.replace("/", "\\"),
         "hashes": [{"alg": "SHA-256", "content": digest}]} for name, digest in assets.items()]}), encoding="utf-8")
    return path


def _packaged_hashes(root: Path) -> dict[str, str]:
    return {rel: asset_origins.file_digest(root / rel) for rel in asset_origins.packaged_files(root)}


def test_packaged_assets_match_the_pinned_origins(tmp_path):
    sbom = _sbom(tmp_path / "sbom.json", _packaged_hashes(ROOT))
    assert asset_origins.check_package(sbom) == []


def test_packaged_asset_problems_are_reported(tmp_path):
    packaged = _packaged_hashes(ROOT)
    packaged["assets/brand/logo.png"] = "0" * 64
    packaged["assets/brand/new.png"] = "1" * 64
    del packaged["assets/brand/app.ico"]
    problems = asset_origins.check_package(_sbom(tmp_path / "sbom.json", packaged))
    assert "packaged asset without origin: assets/brand/new.png" in problems
    assert "asset with origin is not packaged: assets/brand/app.ico" in problems
    assert any(p.startswith("packaged bytes differ from the pinned origin: assets/brand/logo.png") for p in problems)


def test_windows_checkout_with_crlf_text_is_accepted(tmp_path):
    import hashlib

    root = _copy_assets(tmp_path)
    text = (root / "templates" / "cover_letter.txt").read_bytes().replace(b"\r\n", b"\n")
    packaged = _packaged_hashes(root)
    packaged["templates/cover_letter.txt"] = hashlib.sha256(text.replace(b"\n", b"\r\n")).hexdigest()
    assert asset_origins.check_package(_sbom(tmp_path / "sbom.json", packaged), root) == []
