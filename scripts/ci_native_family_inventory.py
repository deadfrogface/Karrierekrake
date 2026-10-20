"""T06.05.07.06.*: hash-check every native file of the BUILT package and group it into families.

Reads the actual package (Linux onedir, macOS .app bundle or Windows onefile EXE) and the
release SBOM of the same build. Every native file (ELF, Mach-O, PE) must be in the SBOM
with the same SHA-256; each is assigned to a review family (OS package, Python
distribution, CPython runtime, PyInstaller bootloader). Families without a version and
files without a family are listed explicitly, never dropped.

Usage: python scripts/ci_native_family_inventory.py --package <exe or bundle> --sbom release-sbom.json --out inventory.json
Exit 1 on a hash mismatch or a native file missing from the SBOM.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections import defaultdict
from pathlib import Path, PurePosixPath

MAGIC = (b"\x7fELF", b"\xfe\xed\xfa\xce", b"\xfe\xed\xfa\xcf", b"\xce\xfa\xed\xfe", b"\xcf\xfa\xed\xfe",
         b"\xca\xfe\xba\xbe", b"MZ")
BUNDLE_PREFIXES = ("_internal/", "Contents/Frameworks/", "Contents/Resources/", "Contents/MacOS/")


def _is_native(head: bytes) -> bool:
    return head.startswith(MAGIC)


def package_files(package: Path) -> dict[str, tuple[str, str]]:
    """{relative path: (sha256, kind)} of the native files in the built package."""
    files: dict[str, tuple[str, str]] = {}
    if package.is_file():  # Windows onefile: native entries live in the CArchive
        from PyInstaller.archive.readers import CArchiveReader

        archive = CArchiveReader(str(package))
        for name in archive.toc:
            data = archive.extract(name)
            if isinstance(data, bytes) and _is_native(data[:4]):
                files[name.replace("\\", "/")] = (hashlib.sha256(data).hexdigest(), "archive")
        files["(bootloader) " + package.name] = (hashlib.sha256(package.read_bytes()).hexdigest(), "bootloader")
        return files
    for path in sorted(package.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        with path.open("rb") as handle:
            head = handle.read(4)
        if not _is_native(head):
            continue
        rel = path.relative_to(package).as_posix()
        kind = "bootloader" if rel in {"Karrierekrake", "Contents/MacOS/Karrierekrake"} else "file"
        files[rel] = (hashlib.sha256(path.read_bytes()).hexdigest(), kind)
    return files


def _sbom_key(rel: str) -> str:
    for prefix in BUNDLE_PREFIXES:
        if rel.startswith(prefix):
            return rel[len(prefix):]
    return rel


def build(package: Path, sbom_path: Path) -> dict:
    sbom = json.loads(sbom_path.read_text(encoding="utf-8"))
    components = {c.get("bom-ref"): c for c in sbom.get("components", [])}
    # Windows SBOM names carry PyInstaller's backslash destinations (PySide6\VCRUNTIME140.dll).
    native = {str(c["name"]).replace("\\", "/"): c for c in sbom.get("components", [])
              if str(c.get("bom-ref", "")).startswith("native:")}
    by_hash = defaultdict(list)
    for name, comp in native.items():
        for h in comp.get("hashes", []):
            by_hash[h.get("content")].append(name)
    families: dict[str, dict] = {}
    problems, no_family, missing = [], [], []
    files = package_files(package)
    for rel, (digest, kind) in sorted(files.items()):
        if kind == "bootloader":
            fam = families.setdefault("pyinstaller-bootloader", {"owner": "PyInstaller bootloader", "version": None,
                                                                  "source": "built executable", "files": []})
            fam["files"].append({"path": rel, "sha256": digest})
            continue
        key = _sbom_key(rel)
        comp = native.get(key)
        if comp is None:
            # macOS keeps a second copy/symlink target under another prefix, and
            # PySide6/shiboken6 ship their own VCRUNTIME140.dll beside the root
            # copy: match by content before falling back to the bare file name.
            names = by_hash.get(digest, [])
            comp = native.get(names[0]) if names else native.get(PurePosixPath(key).name)
        if comp is None:
            missing.append(rel)
            continue
        sbom_hash = next((h.get("content") for h in comp.get("hashes", []) if h.get("alg") == "SHA-256"), None)
        if sbom_hash != digest:
            problems.append(f"{rel}: sha256 {digest} != SBOM {sbom_hash}")
        props = {p.get("name"): p.get("value") for p in comp.get("properties", [])}
        owner_ref = props.get("kk:os-package") or props.get("kk:python-runtime")
        owner = components.get(owner_ref) if owner_ref else None
        if owner is not None:
            fam_key, name, version = owner_ref, owner.get("name"), owner.get("version")
            source = "os-package" if props.get("kk:os-package") else "python-runtime"
        elif props.get("kk:distribution"):
            dist = next((c for c in components.values() if c.get("type") == "library"
                         and c.get("name") == props["kk:distribution"] and not str(c.get("bom-ref", "")).startswith(("os-package:", "embedded:"))), None)
            fam_key, name, version, source = "dist:" + props["kk:distribution"], props["kk:distribution"], (dist or {}).get("version"), "python-distribution"
        elif comp.get("version") and props.get("kk:native-product"):
            fam_key, name, version, source = "product:" + props["kk:native-product"], props["kk:native-product"], comp["version"], "embedded-version"
        else:
            no_family.append(rel)
            continue
        fam = families.setdefault(fam_key, {"owner": name, "version": version, "source": source, "files": []})
        fam["files"].append({"path": rel, "sha256": digest})
    family_list = sorted(families.values(), key=lambda f: (f["source"], str(f["owner"]).lower()))
    for fam in family_list:
        fam["count"] = len(fam["files"])
    return {
        "ok": not problems and not missing,
        "package": package.name,
        "native_files": len(files),
        "families": family_list,
        "family_count": len(family_list),
        "version_unknown": sorted(f["owner"] for f in family_list if not f["version"]),
        "no_family": no_family,
        "missing_from_sbom": missing,
        "hash_mismatches": problems,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--sbom", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    report = build(args.package.resolve(strict=True), args.sbom)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    summary = {k: report[k] for k in ("ok", "native_files", "family_count")}
    summary.update(version_unknown=report["version_unknown"], no_family=len(report["no_family"]),
                   missing_from_sbom=report["missing_from_sbom"][:20], hash_mismatches=report["hash_mismatches"][:10])
    print(json.dumps(summary, ensure_ascii=False))
    if os.environ.get("GITHUB_ACTIONS") == "true":
        level = "notice" if report["ok"] else "error"
        print(f"::{level} title=Native family inventory::" + json.dumps(summary, ensure_ascii=False).replace("%", "%25"))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
