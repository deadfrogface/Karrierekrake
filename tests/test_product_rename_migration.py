"""Regression: AppData migration Jobhuntsaver → Karrierekrake and branding identity."""

from __future__ import annotations

from pathlib import Path

import pytest

from desktop.branding import DATA_DIR_NAME, DISPLAY_NAME, EXE_BASENAME, TECHNICAL_NAME
from desktop.legacy_migration import legacy_data_dir_name, migrate_legacy_appdata_if_needed
from desktop.paths import app_data_dir, ensure_app_dirs


def test_canonical_product_identity():
    assert DISPLAY_NAME == "Karrierekrake"
    assert TECHNICAL_NAME == "Karrierekrake"
    assert DATA_DIR_NAME == "Karrierekrake"
    assert EXE_BASENAME == "Karrierekrake"
    assert legacy_data_dir_name() == "Jobhuntsaver"
    assert legacy_data_dir_name() != DATA_DIR_NAME


def test_fresh_install_uses_only_karrierekrake(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    root = app_data_dir()
    assert root == tmp_path / "Karrierekrake"
    assert root.is_dir()
    assert not (tmp_path / "Jobhuntsaver").exists()
    dirs = ensure_app_dirs()
    assert dirs["data"].is_dir()


def test_legacy_migration_copies_and_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    legacy = tmp_path / "Jobhuntsaver"
    (legacy / "config").mkdir(parents=True)
    profile = legacy / "config" / "profile.yaml"
    profile.write_text("full_name: Ada Beispiel\n", encoding="utf-8")
    db = legacy / "data"
    db.mkdir()
    (db / "app.db").write_bytes(b"sqlite-fake")

    first = migrate_legacy_appdata_if_needed(tmp_path / "Karrierekrake")
    assert first == tmp_path / "Karrierekrake"
    assert (first / "config" / "profile.yaml").read_text(encoding="utf-8") == (
        "full_name: Ada Beispiel\n"
    )
    assert (first / "data" / "app.db").read_bytes() == b"sqlite-fake"
    assert (first / ".karrierekrake_migration.json").is_file()
    # Legacy preserved
    assert profile.is_file()

    # Second run must not fail or wipe
    profile.write_text("full_name: CHANGED_LEGACY\n", encoding="utf-8")
    second = migrate_legacy_appdata_if_needed(tmp_path / "Karrierekrake")
    assert second == first
    assert (first / "config" / "profile.yaml").read_text(encoding="utf-8") == (
        "full_name: Ada Beispiel\n"
    )


def test_existing_canonical_preferred_over_legacy(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    legacy = tmp_path / "Jobhuntsaver" / "config"
    legacy.mkdir(parents=True)
    (legacy / "profile.yaml").write_text("full_name: Legacy\n", encoding="utf-8")
    canonical = tmp_path / "Karrierekrake" / "config"
    canonical.mkdir(parents=True)
    (canonical / "profile.yaml").write_text("full_name: Canonical\n", encoding="utf-8")

    root = migrate_legacy_appdata_if_needed(tmp_path / "Karrierekrake")
    assert (root / "config" / "profile.yaml").read_text(encoding="utf-8") == (
        "full_name: Canonical\n"
    )


def test_repo_has_no_active_jobhuntsaver_identity():
    """Active tree must not advertise Jobhuntsaver except migration boundary."""
    root = Path(".")
    allowed = {
        Path("desktop/legacy_migration.py"),
        Path("tests/test_product_rename_migration.py"),
    }
    # needle split so this file is not a self-hit beyond the allowed set
    needle = "jobhunt" + "saver"
    offenders: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(
            p in path.parts
            for p in (".git", ".venv", "__pycache__", "dist", "build", ".pytest_cache", ".hypothesis")
        ):
            continue
        if path.resolve() in {p.resolve() for p in allowed}:
            continue
        if _find_name_variants(path, (needle, "job_hunt_saver", "job-hunt-saver"), lower=True):
            offenders.append(str(path))
    assert offenders == []


def _find_name_variants(path, variants, *, chunk_size=65536, lower=False):
    # Scan complete text with bounded memory. Downloaded GGUFs must not be
    # read wholesale into a Unicode string just to establish they are binary.
    found = set()
    overlap = max(map(len, variants)) - 1
    tail = ""
    try:
        with path.open(encoding="utf-8") as stream:
            while block := stream.read(chunk_size):
                combined = tail + (block.lower() if lower else block)
                found.update(value for value in variants if value in combined)
                tail = combined[-overlap:] if overlap else ""
    except (UnicodeDecodeError, OSError):
        return []  # Same all-or-nothing UTF-8 policy as read_text previously.
    return [value for value in variants if value in found]


def test_name_scan_catches_chunk_boundary_and_rejects_binary(tmp_path):
    path = tmp_path / "source.txt"
    variant = "synthetic-variant"
    path.write_text("1234567" + variant + "x" * 100000, encoding="utf-8")
    assert _find_name_variants(path, (variant,), chunk_size=8) == [variant]
    assert _find_name_variants(path, (variant.upper(),), chunk_size=8) == []
    assert _find_name_variants(path, (variant,), chunk_size=8, lower=True) == [variant]
    path.write_bytes((variant + "x" * 100000).encode() + b"\xff")
    assert _find_name_variants(path, (variant,), chunk_size=8) == []


def test_no_wrong_karrierekrake_capitalization():
    root = Path(".")
    bad = (
        "Karriere" + "Krake",
        "Karriere" + " Krake",
        "Karriere" + "-Krake",
        "karriere" + "Krake",
    )
    offenders: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(
            p in path.parts
            for p in (
                ".git",
                ".venv",
                "__pycache__",
                "dist",
                "build",
                ".pytest_cache",
                ".hypothesis",
                "artifacts",
            )
        ):
            continue
        if path.name == "test_product_rename_migration.py":
            continue
        for item in _find_name_variants(path, bad):
            offenders.append(f"{path}: {item}")
    assert offenders == []
