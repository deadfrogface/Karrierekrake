"""Native release checks; package replacement is performed by the user.

Never applies Windows component manifests to macOS/Linux bundles.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from core.app_updates import REPOSITORY, _json

METADATA = 'native-current.json'
ASSETS = {
    'macos-arm64': 'Karrierekrake-macOS-AppleSilicon.dmg',
    'macos-x86_64': 'Karrierekrake-macOS-Intel.dmg',
    'linux-x86_64': 'Karrierekrake-Linux-x86_64.tar.gz',
}


def current() -> dict:
    if not getattr(sys, 'frozen', False):
        return {}
    root = Path(getattr(sys, '_MEIPASS', Path(sys.executable).resolve().parent))
    try:
        value = json.loads((root / METADATA).read_text(encoding='utf-8'))
        if value.get('target') not in ASSETS or not re.fullmatch(r'[0-9a-f]{40}', value.get('commit', '')):
            return {}
        if type(value.get('sequence')) is not int or value['sequence'] <= 0:
            return {}
        return value
    except (OSError, ValueError, AttributeError, TypeError):
        return {}


def check_for_update(installed: dict | None = None) -> dict | None:
    installed = installed or current()
    target = installed.get('target')
    if target not in ASSETS:
        return None
    # A Windows release can precede attachment of the native assets. Inspect
    # a bounded list rather than offering a different OS or an older package.
    releases = _json(f'https://api.github.com/repos/{REPOSITORY}/releases?per_page=20')
    if not isinstance(releases, list):
        raise TypeError('invalid_release_list')
    candidates = []
    for release in releases:
        if release.get('draft') or release.get('prerelease'):
            continue
        tag = release.get('tag_name', '')
        if not re.fullmatch(r'(?:update-[0-9]+-[a-f0-9]{12}|v[0-9A-Za-z._-]+)', tag):
            continue
        base = f'https://github.com/{REPOSITORY}/releases/download/{tag}/'
        manifest_url = base + f'native-manifest-{target}.json'
        urls = {asset.get('browser_download_url') for asset in release.get('assets', [])}
        if manifest_url not in urls or base + ASSETS[target] not in urls:
            continue
        manifest = _json(manifest_url)
        if (not isinstance(manifest, dict) or manifest.get('protocol') != 1
                or manifest.get('target') != target or manifest.get('tag') != tag
                or manifest.get('url') != base + ASSETS[target]
                or not re.fullmatch(r'[a-f0-9]{40}', str(manifest.get('commit', '')))
                or not re.fullmatch(r'[a-f0-9]{64}', str(manifest.get('sha256', '')))
                or type(manifest.get('sequence')) is not int
                or type(manifest.get('size')) is not int or not 0 < manifest['size'] < 10_000_000_000):
            raise ValueError('invalid_native_release')
        if manifest['sequence'] > installed['sequence'] and manifest['commit'] != installed['commit']:
            candidates.append(manifest)
    return max(candidates, key=lambda item: item['sequence']) if candidates else None
