"""T03.04: helpers and CI wiring of the installed Windows upgrade check."""
from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from scripts import ci_windows_upgrade as upgrade

ROOT = Path(__file__).resolve().parents[1]


def test_db_path_comes_from_the_smoke_marker():
    text = "token=abc\ndb=C:\\tmp\\la\\Karrierekrake\\data\\jobs.db\npages=8\nSMOKE_TEST_OK"
    assert upgrade._db_path(text) == Path("C:\\tmp\\la\\Karrierekrake\\data\\jobs.db")
    with pytest.raises(ValueError):
        upgrade._db_path("SMOKE_TEST_OK")


def test_old_zip_is_found_in_the_downloaded_artifact(tmp_path):
    nested = tmp_path / "dist" / "Karrierekrake-Windows.zip"
    nested.parent.mkdir()
    with zipfile.ZipFile(nested, "w") as archive:
        archive.writestr("Karrierekrake.exe", b"MZ")
    assert upgrade._old_zip(tmp_path) == nested
    assert upgrade._old_zip(nested) == nested
    with pytest.raises(FileNotFoundError):
        upgrade._old_zip(tmp_path / "dist" / "missing")


def test_failure_is_reported_not_raised(tmp_path):
    out = tmp_path / "r.json"
    exe = tmp_path / "Karrierekrake.exe"
    exe.write_bytes(b"MZ")
    assert upgrade.main(["--old-zip", str(tmp_path / "none"), "--new-exe", str(exe), "--out", str(out)]) == 1
    assert '"ok": false' in out.read_text(encoding="utf-8")


def test_windows_smoke_runs_the_upgrade_against_an_older_package():
    workflow = (ROOT / ".github" / "workflows" / "windows-smoke.yml").read_text(encoding="utf-8")
    assert "native_upgrade_baseline.py --target Windows-Smoke --workflow windows-smoke.yml" in workflow
    assert "scripts/ci_windows_upgrade.py --old-zip" in workflow
    assert "actions: read" in workflow
