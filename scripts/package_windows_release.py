#!/usr/bin/env python3
"""Assemble the Windows release unit with its offline model inside the EXE.

The public EXE must work by itself from a clean directory. A sidecar-only
build is rejected, even when a model exists in the build tree.

Usage::

    python scripts/package_windows_release.py --dist dist --out dist/Karrierekrake-Windows.zip
"""

from __future__ import annotations

import argparse
import json
import sys
import zipfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.cv_llm_runtime import CV_MODEL_REL, CV_MODEL_SHA256

INSTALL_TXT = """Karrierekrake — Windows-Paket

Dieses Zip enthält:
  Karrierekrake.exe
  INSTALL.txt (diese Datei)

Starten Sie Karrierekrake.exe. Die lokale Auswertung ist darin enthalten.

Nach dem Start:
  - Kein Internet nötig für Lebenslauf-Import und Anschreiben
  - Kein separater Modell-Download, kein Terminal, kein Modellpfad
  - Daten unter %LOCALAPPDATA%\\Karrierekrake

Bei der Meldung \"lokales Lebenslauf-Modell fehlt\":
  Bitte ein aktuelles Release-Paket installieren.
"""


def require_release_layout(dist: Path) -> Path:
    """Reject a release whose EXE cannot run without adjacent files."""
    exe = dist / "Karrierekrake.exe"
    if not exe.is_file():
        raise SystemExit(f"EXE missing: {exe}")
    from scripts.scan_release_artifact import require_cv_model_embedded

    hits = require_cv_model_embedded(exe)
    if hits:
        raise SystemExit(f"Standalone EXE model gate failed: {hits}")
    return exe


def stage_install_dir(dist: Path, dest: Path) -> Path:
    """Copy only the EXE into an empty install folder (simulates user extract)."""
    import shutil

    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    shutil.copy2(dist / "Karrierekrake.exe", dest / "Karrierekrake.exe")
    (dest / "INSTALL.txt").write_text(INSTALL_TXT, encoding="utf-8")
    return dest / "Karrierekrake.exe"


def build_zip(dist: Path, out_zip: Path) -> dict:
    exe = require_release_layout(dist)
    out_zip.parent.mkdir(parents=True, exist_ok=True)
    if out_zip.exists():
        out_zip.unlink()

    members = [
        exe,
    ]
    for name in ("build_metadata.txt", "content_manifest.json"):
        p = dist / name
        if p.is_file():
            members.append(p)

    with zipfile.ZipFile(out_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("INSTALL.txt", INSTALL_TXT)
        for path in members:
            arc = path.relative_to(dist).as_posix()
            zf.write(path, arcname=arc)

    with zipfile.ZipFile(out_zip) as archive:
        member_names = sorted(Path(i.filename).as_posix() for i in archive.infolist())

    meta = {
        "zip": str(out_zip),
        "zip_bytes": out_zip.stat().st_size,
        "exe_bytes": (dist / "Karrierekrake.exe").stat().st_size,
        "model_rel": CV_MODEL_REL.as_posix(),
        "model_embedded": True,
        "model_sha256": CV_MODEL_SHA256,
        "members": member_names,
    }
    meta_path = out_zip.with_suffix(out_zip.suffix + ".json")
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist", type=Path, default=_ROOT / "dist")
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Zip path (default: <dist>/Karrierekrake-Windows.zip)",
    )
    parser.add_argument(
        "--stage-install",
        type=Path,
        default=None,
        help="Also copy the standalone EXE into this fresh folder (CI install simulation)",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Only verify layout (no zip)",
    )
    args = parser.parse_args(argv)

    dist = args.dist.resolve()
    exe = require_release_layout(dist)
    print(f"OK standalone EXE: {exe} ({exe.stat().st_size} bytes)", flush=True)

    if args.stage_install is not None:
        exe = stage_install_dir(dist, args.stage_install.resolve())
        print(f"OK staged install: {exe}", flush=True)

    if args.check_only:
        return 0

    out = (args.out or (dist / "Karrierekrake-Windows.zip")).resolve()
    meta = build_zip(dist, out)
    print(json.dumps(meta, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
