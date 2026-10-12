"""Locate Chromium profiles and validate dedicated automation directories."""
from __future__ import annotations

import os
import sys
from pathlib import Path


def system_profile_roots() -> dict[str, Path]:
    home = Path.home()
    if sys.platform == 'win32':
        root = Path(os.environ.get('LOCALAPPDATA') or home / 'AppData' / 'Local')
        return {'chrome': root / 'Google/Chrome/User Data',
                'edge': root / 'Microsoft/Edge/User Data',
                'brave': root / 'BraveSoftware/Brave-Browser/User Data',
                'chromium': root / 'Chromium/User Data'}
    if sys.platform == 'darwin':
        root = home / 'Library/Application Support'
        return {'chrome': root / 'Google/Chrome', 'edge': root / 'Microsoft Edge',
                'brave': root / 'BraveSoftware/Brave-Browser', 'chromium': root / 'Chromium'}
    root = Path(os.environ.get('XDG_CONFIG_HOME') or home / '.config')
    return {'chrome': root / 'google-chrome', 'edge': root / 'microsoft-edge',
            'brave': root / 'BraveSoftware/Brave-Browser', 'chromium': root / 'chromium'}


def discover_profiles() -> dict[str, Path]:
    """Return existing profile roots; never read or copy private cookies."""
    return {name: path for name, path in system_profile_roots().items() if path.is_dir()}


def automation_profile(path: Path) -> Path:
    path = Path(path).expanduser().resolve()
    for root in system_profile_roots().values():
        if path == root.resolve() or path.is_relative_to(root.resolve()):
            raise ValueError('Alltagsprofil nicht für Automatisierung unterstützt. '
                             'Bitte ein separates Karrierekrake-Profil verwenden.')
    return path
