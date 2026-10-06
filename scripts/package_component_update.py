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
from core.app_updates import CURRENT, MODEL_PATH, REPOSITORY, TARGETS, digest, validate_manifest
from core.cv_llm_runtime import CV_MODEL_SHA256


def build(exe: Path, model: Path, out: Path, *, sequence: int, commit: str) -> dict:
    if digest(model) != CV_MODEL_SHA256:
        raise ValueError('bundled_model_hash_mismatch')
    out.mkdir(parents=True, exist_ok=True)
    tag = f'update-{sequence}-{commit[:12]}'
    manifest = {'protocol': 1, 'tag': tag, 'sequence': sequence, 'commit': commit, 'components': {}}
    for name, source in [('app', exe), ('model', model)]:
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
    shutil.copy2(exe, install / TARGETS['app'])
    model_target = install / MODEL_PATH
    model_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(model, model_target)
    (install / CURRENT).write_text(text, encoding='utf-8')
    (install / 'INSTALL.txt').write_text('Karrierekrake\nEntpacke den gesamten Ordner an einen beschreibbaren Ort und starte Karrierekrake.exe.\nBei Erstinstallation lade das KI-Modell über Einstellungen → Allgemein → KI-Modell herunterladen. Dafür ist einmal Internet nötig. Danach läuft es lokal; spätere Programmupdates behalten das Modell. Updates findest du unter Einstellungen → Allgemein.\nNutzerdaten liegen weiterhin unter %LOCALAPPDATA%\\Karrierekrake.\n', encoding='utf-8')
    with zipfile.ZipFile(out / 'Karrierekrake-Setup.zip', 'w', compression=zipfile.ZIP_STORED) as archive:
        for file in sorted(install.rglob('*')):
            if file.is_file() and file.relative_to(install).as_posix() != MODEL_PATH:
                archive.write(file, file.relative_to(install))
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--exe', type=Path, required=True)
    parser.add_argument('--model', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--sequence', type=int, required=True)
    parser.add_argument('--commit', required=True)
    args = parser.parse_args()
    result = build(args.exe, args.model, args.out, sequence=args.sequence, commit=args.commit)
    print(result['tag'])
