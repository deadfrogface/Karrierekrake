"""Prepare native build identity and package a tested macOS/Linux bundle."""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.native_updates import ASSETS, METADATA
from core.release_identity import DISPLAY_VERSION, VERSION


def prepare(target: str, commit: str, sequence: int) -> dict:
    if target not in ASSETS or not re.fullmatch(r'[a-f0-9]{40}', commit) or sequence <= 0:
        raise ValueError('invalid_native_build_identity')
    if target.startswith('macos-'):
        # Reuse the existing brand artwork with Apple's required iconset names.
        with tempfile.TemporaryDirectory(prefix='kk-icon-') as temporary:
            iconset = Path(temporary) / 'Karrierekrake.iconset'
            iconset.mkdir()
            for size in (16, 32, 128, 256, 512):
                for scale in (1, 2):
                    source = ROOT / 'assets' / 'brand' / 'icons' / f'icon-{size * scale}.png'
                    suffix = '@2x' if scale == 2 else ''
                    shutil.copy2(source, iconset / f'icon_{size}x{size}{suffix}.png')
            subprocess.run(['iconutil', '-c', 'icns', str(iconset), '-o',
                            str(ROOT / 'packaging' / 'native-app.icns')], check=True)
    metadata = {'target': target, 'commit': commit, 'sequence': sequence,
                'version': VERSION, 'display_version': DISPLAY_VERSION}
    (ROOT / 'packaging' / METADATA).write_text(json.dumps(metadata), encoding='utf-8')
    return metadata


def package(target: str, dist: Path, out: Path) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    archive = out / ASSETS[target]
    if target.startswith('macos-'):
        app = dist / 'Karrierekrake.app'
        if not (app / 'Contents' / 'MacOS' / 'Karrierekrake').is_file():
            raise ValueError('native_app_missing')
        # Preserve PyInstaller's framework symlinks and signatures.
        stage = out / 'dmg-root'
        if stage.exists():
            shutil.rmtree(stage)
        stage.mkdir()
        def link_or_copy(source, destination):
            try:
                os.link(source, destination)
            except OSError:
                shutil.copy2(source, destination)
        shutil.copytree(app, stage / app.name, symlinks=True, copy_function=link_or_copy)
        (stage / 'Applications').symlink_to('/Applications')
        subprocess.run(['hdiutil', 'create', '-volname', 'Karrierekrake', '-srcfolder', str(stage),
                        '-ov', '-format', 'UDZO', str(archive)], check=True)
        shutil.rmtree(stage)
    else:
        app = dist / 'Karrierekrake'
        if not (app / 'Karrierekrake').is_file():
            raise ValueError('native_app_missing')
        with tarfile.open(archive, 'w:gz', dereference=False) as bundle:
            bundle.add(app, arcname='Karrierekrake')
    if archive.stat().st_size >= 2 * 1024**3:
        raise ValueError('release_asset_exceeds_github_limit')
    shutil.copy2(ROOT / 'packaging' / METADATA, out / METADATA)
    return archive


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--target', choices=ASSETS, required=True)
    parser.add_argument('--prepare', action='store_true')
    parser.add_argument('--commit')
    parser.add_argument('--sequence', type=int)
    parser.add_argument('--dist', type=Path, default=ROOT / 'dist')
    parser.add_argument('--out', type=Path, default=ROOT / 'native-release')
    args = parser.parse_args()
    if args.prepare:
        prepare(args.target, args.commit or '', args.sequence or 0)
    else:
        print(package(args.target, args.dist, args.out))
