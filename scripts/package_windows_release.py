#!/usr/bin/env python3
"""Assemble the Windows release unit: EXE + CV model sidecar + install notes.

Users who download only ``Karrierekrake.exe`` hit ``model_missing`` because the
~2.6 GiB GGUF ships as ``models/qwen3.5-4b/*.gguf`` next to the EXE (not inside
the onefile archive by default). This script builds one zip that must stay
intact after extract.

Usage::

    python scripts/package_windows_release.py --dist dist --out dist/Karrierekrake-Windows.zip
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.cv_llm_runtime import CV_MODEL_FILENAME, CV_MODEL_REL, CV_MODEL_SHA256

INSTALL_TXT = """Karrierekrake — Windows-Paket

Dieses Zip enthält:
  Karrierekrake.exe
  models/qwen3.5-4b/<Modelldatei>
  INSTALL.txt (diese Datei)

WICHTIG:
  Beide Teile gehören zusammen. Entpacken Sie den kompletten Ordner und
  starten Sie Karrierekrake.exe aus diesem Ordner. Verschieben Sie die EXE
  nicht allein ohne den Ordner \"models\".

Nach dem Start:
  - Kein Internet nötig für Lebenslauf-Import und Anschreiben
  - Kein separater Modell-Download, kein Terminal, kein Modellpfad
  - Daten unter %LOCALAPPDATA%\\Karrierekrake

Bei der Meldung \"lokales Lebenslauf-Modell fehlt\":
  Paket erneut vollständig entpacken (EXE + models) und neu starten.
"""


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def require_release_layout(dist: Path) -> Path:
    """Return the sidecar GGUF path or raise SystemExit."""
    exe = dist / "Karrierekrake.exe"
    if not exe.is_file():
        raise SystemExit(f"EXE missing: {exe}")
    gguf = dist / CV_MODEL_REL
    if not gguf.is_file():
        raise SystemExit(
            f"CV model sidecar missing: {gguf}. "
            "Run: python scripts/prepare_bundled_cv_model.py --also-sidecar dist"
        )
    if gguf.stat().st_size < 1_000_000_000:
        raise SystemExit(f"CV model too small: {gguf.stat().st_size} bytes")
    digest = _sha256(gguf)
    if digest != CV_MODEL_SHA256:
        raise SystemExit(
            f"CV model SHA-256 mismatch:\n  got  {digest}\n  want {CV_MODEL_SHA256}"
        )
    return gguf


def stage_install_dir(dist: Path, dest: Path) -> Path:
    """Copy EXE + models into an empty install folder (simulates user extract)."""
    import shutil

    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    shutil.copy2(dist / "Karrierekrake.exe", dest / "Karrierekrake.exe")
    models_src = dist / "models"
    models_dst = dest / "models"
    shutil.copytree(models_src, models_dst)
    (dest / "INSTALL.txt").write_text(INSTALL_TXT, encoding="utf-8")
    return dest / "Karrierekrake.exe"


def build_zip(dist: Path, out_zip: Path) -> dict:
    gguf = require_release_layout(dist)
    out_zip.parent.mkdir(parents=True, exist_ok=True)
    if out_zip.exists():
        out_zip.unlink()

    members = [
        dist / "Karrierekrake.exe",
        gguf,
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

    meta = {
        "zip": str(out_zip),
        "zip_bytes": out_zip.stat().st_size,
        "exe_bytes": (dist / "Karrierekrake.exe").stat().st_size,
        "model_rel": CV_MODEL_REL.as_posix(),
        "model_bytes": gguf.stat().st_size,
        "model_sha256": CV_MODEL_SHA256,
        "members": sorted(
            [Path(i.filename).as_posix() for i in zipfile.ZipFile(out_zip).infolist()]
        ),
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
        help="Also copy EXE+models into this fresh folder (CI install simulation)",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Only verify layout (no zip)",
    )
    args = parser.parse_args(argv)

    dist = args.dist.resolve()
    gguf = require_release_layout(dist)
    print(f"OK layout: {gguf} ({gguf.stat().st_size} bytes)", flush=True)

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
