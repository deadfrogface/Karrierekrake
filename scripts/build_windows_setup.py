"""Build the Windows setup program (Inno Setup) from an installed-layout folder.

    python scripts/build_windows_setup.py --source component-release/install --out component-release
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.release_identity import DISPLAY_VERSION, WINDOWS_SETUP_ASSET

SCRIPT = ROOT / 'packaging' / 'windows' / 'Karrierekrake.iss'


def find_iscc() -> Path:
    found = shutil.which('iscc') or shutil.which('ISCC')
    candidates = [Path(found)] if found else []
    for base in (os.environ.get('ProgramFiles(x86)'), os.environ.get('ProgramFiles'), os.environ.get('LOCALAPPDATA')):
        if base:
            candidates += [Path(base) / 'Inno Setup 6' / 'ISCC.exe', Path(base) / 'Programs' / 'Inno Setup 6' / 'ISCC.exe']
    for path in candidates:
        if path.is_file():
            return path
    raise FileNotFoundError('inno_setup_not_installed')


def build(source: Path, out: Path) -> Path:
    if not (source / 'Karrierekrake.exe').is_file():
        raise FileNotFoundError('setup_source_without_exe')
    out.mkdir(parents=True, exist_ok=True)
    name = WINDOWS_SETUP_ASSET.removesuffix('.exe')
    subprocess.run([str(find_iscc()), '/Qp', f'/DAppVersion={DISPLAY_VERSION.replace(" ", "-")}',
                    f'/DSourceDir={source.resolve()}', f'/DOutputDir={out.resolve()}', f'/DOutputName={name}', str(SCRIPT)],
                   check=True)
    result = out / WINDOWS_SETUP_ASSET
    if not result.is_file():
        raise FileNotFoundError('setup_not_created')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    print(build(args.source, args.out))
