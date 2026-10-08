"""Publish a single Alpha release atomically from all validated platform builds.

Download/upload one artifact at a time to avoid retaining every OS bundle on
one runner. Keep the release a draft until every platform asset is attached.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.app_updates import REPOSITORY, validate_manifest
from core.native_updates import ASSETS
from core.release_identity import RELEASE_TITLE, VERSION, WINDOWS_ASSET, WINDOWS_TARGET
from scripts.publish_native_assets import manifests


def gh(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(['gh', *args], check=check, capture_output=True, text=True)


def current_main() -> str:
    return gh('api', f'repos/{REPOSITORY}/branches/main', '--jq', '.commit.sha').stdout.strip()


def windows_assets(folder: Path, commit: str) -> tuple[dict, list[Path]]:
    manifest = json.loads((folder / 'update-manifest.json').read_text(encoding='utf-8'))
    validate_manifest(manifest, manifest.get('tag', ''))
    acceptance = json.loads((folder / 'acceptance.json').read_text(encoding='utf-8'))
    if (manifest.get('target') != WINDOWS_TARGET or manifest.get('version') != VERSION
            or manifest.get('commit') != commit or acceptance.get('ok') is not True
            or not (folder / WINDOWS_ASSET).is_file()):
        raise ValueError('windows_release_gate_failed')
    from core.app_updates import digest
    assets = [folder / WINDOWS_ASSET, folder / 'update-manifest.json']
    for component in manifest['components'].values():
        for part in component['parts']:
            path = folder / part['url'].rsplit('/', 1)[-1]
            if not path.is_file() or path.stat().st_size != part['size'] or digest(path) != part['sha256']:
                raise ValueError('windows_asset_integrity_failed')
            assets.append(path)
    return manifest, assets


def notes() -> str:
    lines = [f'# {RELEASE_TITLE}', '', 'Gleicher Programmstand und Funktionsumfang auf Windows, macOS und Linux.',
             '', 'Lade nur das Paket für dein Betriebssystem herunter:', '',
             f'- **Windows (64 Bit):** `{WINDOWS_ASSET}`']
    labels = {'macos-arm64': 'macOS – Apple Silicon (M-Chips)',
              'macos-x86_64': 'macOS – Intel', 'linux-x86_64': 'Linux (64 Bit, Ubuntu/Linux Mint)'}
    lines.extend(f'- **{labels[target]}:** `{name}`' for target, name in ASSETS.items())
    lines += ['', 'Jedes Paket enthält ausschließlich die jeweilige Betriebssystem-Version.',
              'Die .bin- und Manifest-Dateien sind technische Update-Dateien. Windows lädt nur seine Komponenten; macOS/Linux wählen nur ihr eigenes Plattform-/Architektur-Paket.',
              '', 'Windows: ZIP vollständig entpacken und Karrierekrake.exe starten; das lokale KI-Modell beim ersten Start im Updatebereich laden.',
              'macOS: Passendes DMG öffnen und die App in Programme ziehen. Die Alpha ist noch nicht mit Apple Developer ID notarisiert.',
              'Linux: Den gesamten Ordner entpacken und Karrierekrake starten. Den _internal-Ordner behalten.',
              '', 'macOS/Linux prüfen Updates automatisch; das heruntergeladene Paket wird zunächst manuell ersetzt.',
              'Alle Pakete wurden auf demselben Quellcode-Commit gebaut und mit Offline-Lebenslaufimport geprüft.']
    return '\n'.join(lines) + '\n'


def publish(native_run: str, windows_run: str, commit: str) -> bool:
    if not re.fullmatch(r'[a-f0-9]{40}', commit) or not native_run.isdecimal() or not windows_run.isdecimal():
        raise ValueError('invalid_release_build_identity')
    if current_main() != commit:
        return False
    with tempfile.TemporaryDirectory(prefix='kk-alpha-') as temporary:
        root = Path(temporary)
        windows = root / 'windows'
        gh('run', 'download', windows_run, '--repo', REPOSITORY, '--name', 'Karrierekrake-windows-x86_64', '--dir', str(windows))
        manifest, files = windows_assets(windows, commit)
        tag = manifest['tag']
        existing = gh('release', 'view', tag, '--repo', REPOSITORY, '--json', 'isDraft', check=False)
        if existing.returncode == 0 and not json.loads(existing.stdout)['isDraft']:
            return False
        body = root / 'release-notes.md'
        body.write_text(notes(), encoding='utf-8')
        if existing.returncode:
            gh('release', 'create', tag, '--repo', REPOSITORY, '--draft', '--target', commit,
               '--title', RELEASE_TITLE, '--notes-file', str(body))
        else:
            gh('release', 'edit', tag, '--repo', REPOSITORY, '--title', RELEASE_TITLE, '--notes-file', str(body))
        gh('release', 'upload', tag, '--repo', REPOSITORY, *map(str, files), '--clobber')
        import shutil
        shutil.rmtree(windows)
        for target in ASSETS:
            folder = root / f'Karrierekrake-{target}'
            gh('run', 'download', native_run, '--repo', REPOSITORY, '--name', f'Karrierekrake-{target}', '--dir', str(folder))
            files = manifests(root, tag, commit, targets=(target,))
            gh('release', 'upload', tag, '--repo', REPOSITORY, *map(str, files), '--clobber')
            shutil.rmtree(folder)
        if current_main() != commit:
            return False  # Leave superseded releases as drafts.
        gh('release', 'edit', tag, '--repo', REPOSITORY, '--draft=false', '--latest')
        return True


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-run', required=True)
    parser.add_argument('--windows-run', required=True)
    parser.add_argument('--commit', required=True)
    args = parser.parse_args()
    print('Alpha release published' if publish(args.native_run, args.windows_run, args.commit) else 'No publication (already published or main advanced)')
