"""Build component release assets plus a complete first-install ZIP."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import zipfile
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.app_updates import (
    APP_ARCHIVE,
    APP_ITEMS,
    CURRENT,
    MODEL_PATH,
    REPOSITORY,
    TARGETS,
    digest,
    validate_manifest,
)
from core.cv_llm_runtime import CV_MODEL_SHA256
from core.release_identity import VERSION, DISPLAY_VERSION, WINDOWS_TARGET, WINDOWS_ASSET


def app_archive(bundle: Path, target: Path) -> Path:
    """The program folder as the 'app' component: Karrierekrake.exe and _internal/, nothing else."""
    if not (bundle / APP_ITEMS[0]).is_file() or not (bundle / APP_ITEMS[1]).is_dir():
        raise ValueError('app_bundle_incomplete')
    with zipfile.ZipFile(target, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        archive.write(bundle / APP_ITEMS[0], APP_ITEMS[0])
        for file in sorted((bundle / APP_ITEMS[1]).rglob('*')):
            if file.is_file():
                archive.write(file, file.relative_to(bundle).as_posix())
    return target


def build(exe: Path, model: Path, out: Path, *, sequence: int, commit: str) -> dict:
    """``exe`` is the Karrierekrake.exe inside the onedir program folder."""
    if digest(model) != CV_MODEL_SHA256:
        raise ValueError('bundled_model_hash_mismatch')
    bundle = exe.parent
    out.mkdir(parents=True, exist_ok=True)
    app_zip = app_archive(bundle, out / APP_ARCHIVE)
    tag = f'update-{sequence}-{commit[:12]}'
    manifest = {'protocol': 1, 'tag': tag, 'sequence': sequence, 'commit': commit, 'version': VERSION, 'display_version': DISPLAY_VERSION, 'target': WINDOWS_TARGET, 'components': {}}
    for name, source in [('app', app_zip), ('model', model)]:
        parts = []
        with source.open('rb') as stream:
            index = 1
            while True:
                data = stream.read(1_000_000_000)
                if not data:
                    break
                asset = f'{name}-{index:03d}.bin'
                (out / asset).write_bytes(data)
                parts.append({'size': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
                    'url': f'https://github.com/{REPOSITORY}/releases/download/{tag}/{asset}'})
                index += 1
        manifest['components'][name] = {'path': TARGETS[name], 'size': source.stat().st_size,
            'sha256': digest(source),
            'parts': parts}
    validate_manifest(manifest, tag)
    text = json.dumps(manifest, indent=2)
    (out / 'update-manifest.json').write_text(text, encoding='utf-8')
    install = out / 'install'
    install.mkdir(exist_ok=True)
    for item in APP_ITEMS:
        if (bundle / item).is_dir():
            shutil.copytree(bundle / item, install / item, dirs_exist_ok=True)
        else:
            shutil.copy2(bundle / item, install / item)
    app_zip.unlink()
    model_target = install / MODEL_PATH
    model_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(model, model_target)
    (install / CURRENT).write_text(text, encoding='utf-8')
    (install / 'INSTALL.txt').write_text('Karrierekrake\nEntpacke den gesamten Ordner an einen beschreibbaren Ort und starte Karrierekrake.exe.\nBei Erstinstallation lade das KI-Modell über Einstellungen → Allgemein → KI-Modell herunterladen. Dafür ist einmal Internet nötig. Danach läuft es lokal; spätere Programmupdates behalten das Modell. Updates findest du unter Einstellungen → Allgemein.\nNutzerdaten liegen weiterhin unter %LOCALAPPDATA%\\Karrierekrake.\n', encoding='utf-8')
    with zipfile.ZipFile(out / WINDOWS_ASSET, 'w', compression=zipfile.ZIP_STORED) as archive:
        for file in sorted(install.rglob('*')):
            if file.is_file() and file.relative_to(install).as_posix() != MODEL_PATH:
                archive.write(file, file.relative_to(install))
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--exe', type=Path, required=True, help='Karrierekrake.exe inside the onedir folder')
    parser.add_argument('--model', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--sequence', type=int, required=True)
    parser.add_argument('--commit', required=True)
    args = parser.parse_args()
    result = build(args.exe, args.model, args.out, sequence=args.sequence, commit=args.commit)
    print(result['tag'])
