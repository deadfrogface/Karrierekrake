"""T06.05.07.06.*: native files of the built package are hash-checked and grouped into families."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.ci_native_family_inventory import build

ROOT = Path(__file__).resolve().parents[1]


def _sbom(tmp: Path, entries: list[dict], extra: list[dict]) -> Path:
    path = tmp / "release-sbom.json"
    path.write_text(json.dumps({"components": entries + extra}), encoding="utf-8")
    return path


def _native(name: str, data: bytes, **props) -> dict:
    return {"type": "file", "name": name, "bom-ref": "native:" + name,
            "hashes": [{"alg": "SHA-256", "content": hashlib.sha256(data).hexdigest()}],
            "properties": [{"name": k.replace("_", ":", 1).replace("_", "-"), "value": v} for k, v in props.items()]}


def _package(tmp: Path, files: dict[str, bytes]) -> Path:
    root = tmp / "Karrierekrake"
    for rel, data in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_bytes(data)
    return root


ELF_A, ELF_B, ELF_C = b"\x7fELFa", b"\x7fELFb", b"\x7fELFc"


def test_files_are_grouped_by_owner_with_versions(tmp_path):
    package = _package(tmp_path, {"Karrierekrake": b"\x7fELFboot", "_internal/libz.so.1": ELF_A,
                                  "_internal/numpy/core/x.so": ELF_B, "_internal/libpython3.12.so.1.0": ELF_C,
                                  "_internal/data.txt": b"not native"})
    sbom = _sbom(tmp_path, [
        _native("libz.so.1", ELF_A, kk_os_package="os-package:zlib1g"),
        _native("numpy/core/x.so", ELF_B, kk_distribution="numpy"),
        _native("libpython3.12.so.1.0", ELF_C, kk_python_runtime="runtime:cpython"),
    ], [
        {"type": "library", "name": "zlib1g", "version": "1:1.2.11", "bom-ref": "os-package:zlib1g"},
        {"type": "library", "name": "numpy", "version": "1.26.4", "bom-ref": "pkg:pypi/numpy@1.26.4"},
        {"type": "library", "name": "CPython", "version": "3.12.15", "bom-ref": "runtime:cpython"},
    ])
    report = build(package, sbom)
    assert report["ok"], report
    owners = {f["owner"]: (f["version"], f["count"], f["source"]) for f in report["families"]}
    assert owners["zlib1g"] == ("1:1.2.11", 1, "os-package")
    assert owners["numpy"] == ("1.26.4", 1, "python-distribution")
    assert owners["CPython"] == ("3.12.15", 1, "python-runtime")
    assert owners["PyInstaller bootloader"][1] == 1
    assert report["native_files"] == 4 and not report["no_family"]


def test_hash_mismatch_and_unknown_file_fail(tmp_path):
    package = _package(tmp_path, {"_internal/libz.so.1": ELF_A, "_internal/libnew.so": ELF_B})
    sbom = _sbom(tmp_path, [_native("libz.so.1", b"\x7fELFother", kk_os_package="os-package:zlib1g")],
                 [{"type": "library", "name": "zlib1g", "version": "1", "bom-ref": "os-package:zlib1g"}])
    report = build(package, sbom)
    assert not report["ok"]
    assert report["missing_from_sbom"] == ["_internal/libnew.so"]
    assert report["hash_mismatches"] and "libz.so.1" in report["hash_mismatches"][0]


def test_file_without_owner_is_listed_not_dropped(tmp_path):
    package = _package(tmp_path, {"_internal/libx.so": ELF_A})
    report = build(package, _sbom(tmp_path, [_native("libx.so", ELF_A)], []))
    assert report["ok"] and report["no_family"] == ["_internal/libx.so"]


def test_every_platform_runs_the_inventory_on_the_built_package():
    desktop = (ROOT / ".github" / "workflows" / "desktop-platforms.yml").read_text(encoding="utf-8")
    windows = (ROOT / ".github" / "workflows" / "windows-smoke.yml").read_text(encoding="utf-8")
    assert "scripts/ci_native_family_inventory.py --package" in desktop
    assert "scripts/ci_native_family_inventory.py --package dist/Karrierekrake.exe" in windows


MZ_ROOT, MZ_QT, MZ_SHIBOKEN = b"MZroot-vcruntime", b"MZpyside-vcruntime", b"MZshiboken-vcruntime"


def test_same_dll_name_in_several_packages_matches_its_own_bytes(tmp_path):
    # Windows: PySide6 and shiboken6 ship their own VCRUNTIME140.dll beside the root copy,
    # and the SBOM names carry PyInstaller's backslash destinations.
    package = _package(tmp_path, {"_internal/VCRUNTIME140.dll": MZ_ROOT,
                                  "_internal/PySide6/VCRUNTIME140.dll": MZ_QT,
                                  "_internal/shiboken6/VCRUNTIME140.dll": MZ_SHIBOKEN})
    sbom = _sbom(tmp_path, [_native("VCRUNTIME140.dll", MZ_ROOT),
                            _native(r"PySide6\VCRUNTIME140.dll", MZ_QT),
                            _native(r"shiboken6\VCRUNTIME140.dll", MZ_SHIBOKEN)], [])
    report = build(package, sbom)
    assert report["ok"], report
    assert not report["hash_mismatches"] and not report["missing_from_sbom"]


def test_same_name_with_unrecorded_bytes_still_fails(tmp_path):
    package = _package(tmp_path, {"_internal/VCRUNTIME140.dll": MZ_ROOT,
                                  "_internal/PySide6/VCRUNTIME140.dll": b"MZtampered"})
    report = build(package, _sbom(tmp_path, [_native("VCRUNTIME140.dll", MZ_ROOT)], []))
    assert not report["ok"]
    assert report["hash_mismatches"] and "PySide6/VCRUNTIME140.dll" in report["hash_mismatches"][0]
