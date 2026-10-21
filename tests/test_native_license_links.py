"""T08.05.04: native files are linked to the text that covers them, never guessed, never silently dropped."""
from __future__ import annotations

import json

from scripts import export_release_sbom as sbom
from scripts.ci_license_review_check import check
from scripts.native_license_links import evidence_for, ms_redistributable_family


def test_microsoft_runtime_files_get_their_own_family_whatever_folder_they_sit_in():
    assert ms_redistributable_family("api-ms-win-crt-heap-l1-1-0.dll") == "ucrt"
    assert ms_redistributable_family(r"PySide6\MSVCP140.dll") == "vcrt"
    assert ms_redistributable_family("sqlite3.dll") is None


def test_evidence_follows_owner_and_available_text():
    os_owner = {"name": "libz1", "bom-ref": "os-package:libz1"}
    assert evidence_for("libz.so.1", os_owner, set(), None, False) == "distro-copyright:os-package:libz1"
    assert evidence_for("libz.so.1", os_owner, {"libz1"}, None, False) is None  # copyright text missing -> unresolved
    assert evidence_for("libpython3.12.so", None, set(), {"bom-ref": "runtime:cpython"}, True) == "python-license-file:CPython"
    assert evidence_for("libpython3.12.so", None, set(), {"bom-ref": "runtime:cpython"}, False) is None
    assert evidence_for("libmystery.so", None, set(), None, False) is None


def test_windows_runtime_file_is_linked_not_unresolved_and_the_notice_ships(tmp_path, monkeypatch):
    monkeypatch.setattr(sbom.metadata, "packages_distributions", dict)
    monkeypatch.setattr(sbom.metadata, "distributions", list)
    geo = tmp_path / "data/geo"
    geo.mkdir(parents=True)
    (geo / "DE.txt").write_bytes(b"x")
    import hashlib

    (geo / "manifest.json").write_text(json.dumps({
        "files": {"DE": {"path": "DE.txt", "sha256": hashlib.sha256(b"x").hexdigest()}}, "version": "t",
        "license": "t", "source_url": "https://example.org/", "attribution": "a"}))
    dll = tmp_path / "ucrtbase.dll"
    dll.write_bytes(b"MZ")
    other = tmp_path / "mystery.dll"
    other.write_bytes(b"MZ2")
    out = tmp_path / "out"
    sbom.export_release_inventory(tmp_path, out, [("ucrtbase.dll", dll, "BINARY"), ("mystery.dll", other, "BINARY")], [], [])
    review = json.loads((out / "license-review.json").read_text())
    assert "native:ucrtbase.dll" not in review["unresolved"] and "native:mystery.dll" in review["unresolved"]
    assert "--- Microsoft redistributable runtime files ---" in (out / "THIRD_PARTY_NOTICES.txt").read_text(encoding="utf-8")
    assert check(out)["ok"], check(out)["problems"]
    document = json.loads((out / "release-sbom.json").read_text())
    for component in document["components"]:
        if component["name"] == "ucrtbase.dll":
            component["properties"].append({"name": "kk:license-evidence", "value": "ms-redistributable:ucrt"})
    review["unresolved"].append("native:ucrtbase.dll")
    review["unresolved"].sort()
    (out / "release-sbom.json").write_text(json.dumps(document))
    (out / "license-review.json").write_text(json.dumps(review))
    assert any("license-linked and unresolved at once" in p for p in check(out)["problems"])
