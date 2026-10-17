#!/usr/bin/env python3
"""Assemble a Windows release without bundled model weights.

The public EXE must launch by itself from a clean directory. The user
chooses and installs a model during first-run setup.

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

Starten Sie Karrierekrake.exe. Der Einrichtungsassistent empfiehlt ein passendes lokales KI-Modell.

Nach dem Start:
  - Beim ersten Start optional ein geeignetes KI-Modell auswählen und herunterladen
  - Nach erfolgreicher Modellinstallation sind lokale KI-Funktionen offline nutzbar
  - Daten unter %LOCALAPPDATA%\\Karrierekrake

Bei der Meldung \"lokales Lebenslauf-Modell fehlt\":
  Bitte den Einrichtungsassistenten öffnen und ein Modell installieren.
"""


def require_release_layout(dist: Path) -> Path:
    """Reject a release whose EXE cannot run without adjacent files."""
    exe = dist / "Karrierekrake.exe"
    if not exe.is_file():
        raise SystemExit(f"EXE missing: {exe}")
    from scripts.scan_release_artifact import require_cv_model_embedded

    # Model-free distribution: the old embedded-model requirement must NOT pass.
    if not require_cv_model_embedded(exe):
        raise SystemExit("Unexpected bundled CV model: ship weights only on user request")
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


def compliance_members(directory: Path) -> list[tuple[Path, str]]:
    required = [(Path(directory) / name, name) for name in
                ('release-sbom.json', 'THIRD_PARTY_NOTICES.txt', 'license-review.json')]
    required.extend((_ROOT / name, name) for name in ('LICENSE', 'NOTICE'))
    if any(not path.is_file() or path.stat().st_size == 0 for path, _ in required):
        raise ValueError('windows_compliance_inventory_missing')
    return required


def build_zip(dist: Path, out_zip: Path, *, compliance_dir: Path | None = None) -> dict:
    exe = require_release_layout(dist)
    compliance = compliance_members(compliance_dir) if compliance_dir is not None else []
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
        for path, name in compliance:
            zf.write(path, arcname=name)
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
        "model_embedded": False,
        "model_sha256": None,
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
    parser.add_argument('--compliance-dir', type=Path,
                        default=_ROOT / 'build/release-compliance',
                        help='Required resolved build inventory and notices for the release ZIP')
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
    meta = build_zip(dist, out, compliance_dir=args.compliance_dir)
    print(json.dumps(meta, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
