"""Hash-bound origin of the packaged graphics, fonts and templates (T08.05.05).

Every file under ``assets/brand`` and ``templates`` must be listed here with its SHA-256 and an
origin. Unlisted files, missing files and changed hashes fail the check, so a swapped or newly
added asset cannot enter the package without a documented origin. Text files are hashed with
LF line endings so the result does not depend on the checkout.

Usage: python scripts/asset_origins.py [--out asset-origins.json]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCAN_DIRS = ("assets/brand", "templates")
TEXT_SUFFIXES = {".txt", ".md"}

# Origin kinds: master = original project artwork; derived = produced from masters by
# scripts/generate_brand_assets.py; template = project text from the initial commit.
MASTER_SOURCE = "commit 9bb01dba (Karrierekrake: final branding, UI, icons & media)"
GENERATOR = "scripts/generate_brand_assets.py"

ORIGINS: dict[str, dict] = {
    "assets/brand/karrierekrake-app-icon-master.png": {
        "sha256": "9b184c71e16469992f0e486143aa2f595a8f8a7f581216b162a9479fe22c9a58",
        "kind": "master", "source": MASTER_SOURCE, "derived_from": [],
    },
    "assets/brand/karrierekrake-logo-master.png": {
        "sha256": "dc2db1b83f071c51bfe2f99bd566b6409ed82d73db11d7d373aa21823964faec",
        "kind": "master", "source": MASTER_SOURCE, "derived_from": [],
    },
    "assets/brand/logo.png": {
        "sha256": "0e3db142d4011d3f75e4f0c7ded8712585180b26b610c1d353bc4d52c95538a7",
        "kind": "derived", "source": GENERATOR,
        "derived_from": ["assets/brand/karrierekrake-logo-master.png"],
    },
    "assets/brand/social-preview.png": {
        "sha256": "6bf99600156258322522415e7a81331e8ff73550a6f05dc13698b0f64f26db6d",
        "kind": "derived", "source": GENERATOR,
        "derived_from": ["assets/brand/karrierekrake-logo-master.png"],
        "embedded_font": "DejaVu Sans Bold, rendered into the PNG by the generator (no font file is packaged); "
                        "its font license text is not yet part of the notices (open item)",
    },
    "assets/brand/app.ico": {
        "sha256": "54d4c1a0e6575efcde238243f53e733d590588b726d47c67c4b04171b6bf6b9c",
        "kind": "derived", "source": GENERATOR,
        "derived_from": ["assets/brand/karrierekrake-app-icon-master.png"],
    },
    "templates/cover_letter.txt": {
        "sha256": "4ea8041beae8d61a8e7354c451209ab2822bc1c7c38f67a2792f057cbfcd5c57",
        "kind": "template",
        "source": "project text, created in commit 7a340c13 (Initial commit), current wording from "
                  "a3124286; text hash with LF line endings",
        "derived_from": [],
    },
}
_ICON_HASHES = {
    1024: "6ad0e67f5100371e234515076d38c4ebc7cc6dec079967b7cb0ee12ba645368d",
    512: "1f17ff20677db8a9f391ec5b88ed1cee9a1d9a38ab1c5ee8b94d82087a4bde19",
    256: "7c50e372af12df2d47aa8c8d67db8143ae3b61d1b5fd5874b0ef6115c753f9ab",
    128: "7e399767a1eae2dc4193a412407c6e2198143ab4bb56f1b858cab6617dfa1a16",
    64: "b00f5cb6af589af08f1e1ebf82492b8171fa275ecf38c7fa585f363e1bd6795b",
    48: "8dd254942a2ced0a49ff83328de22f42540cf5f71c28a41181f2fe65d73aea84",
    32: "d1782bb312527cc60d140cb5b46db03d2f35114009e36c2dd787a09eaa04bce0",
    24: "f4c335055047e76596775efa9aace4d599bb4ac021d9d127e26ef21248c3d568",
    16: "93c5a0df5aa219637e0c18cdb2429007661c25c01ebc220e14db8a2cf7a66976",
}
for _size, _digest in _ICON_HASHES.items():
    ORIGINS[f"assets/brand/icons/icon-{_size}.png"] = {
        "sha256": _digest, "kind": "derived", "source": GENERATOR,
        "derived_from": ["assets/brand/karrierekrake-app-icon-master.png"],
    }


def file_digest(path: Path) -> str:
    data = path.read_bytes()
    if path.suffix.lower() in TEXT_SUFFIXES:
        data = data.replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def packaged_files(root: Path = ROOT) -> list[str]:
    found: list[str] = []
    for directory in SCAN_DIRS:
        base = root / directory
        if base.is_dir():
            found += [p.relative_to(root).as_posix() for p in base.rglob("*") if p.is_file()]
    return sorted(found)


def check(root: Path = ROOT, origins: dict[str, dict] | None = None) -> dict:
    origins = ORIGINS if origins is None else origins
    present = packaged_files(root)
    problems: list[str] = []
    entries = []
    for rel in present:
        if rel not in origins:
            problems.append(f"unlisted asset: {rel}")
    for rel, meta in sorted(origins.items()):
        path = root / rel
        if not path.is_file():
            problems.append(f"missing asset: {rel}")
            continue
        actual = file_digest(path)
        if actual != meta["sha256"]:
            problems.append(f"hash mismatch: {rel} (actual {actual})")
        for parent in meta["derived_from"]:
            if parent not in origins or origins[parent]["kind"] != "master":
                problems.append(f"{rel}: derived_from {parent} is not a listed master")
        entries.append({"path": rel, "sha256": actual, **{k: v for k, v in meta.items() if k != "sha256"}})
    return {"status": "ok" if not problems else "failed", "files": entries, "problems": problems}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, help="write the origin report as JSON")
    args = parser.parse_args(argv)
    report = check()
    if args.out:
        args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for problem in report["problems"]:
        print(problem, file=sys.stderr)
    print(f"asset origins: {report['status']} ({len(report['files'])} files)")
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
