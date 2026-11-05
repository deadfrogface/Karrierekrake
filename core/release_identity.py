"""One version and explicit, disjoint downloads for all desktop platforms.

``RELEASE_MINOR`` is the only number to change for a new release: it moves the shown version
(Alpha 1.1, Alpha 1.2, …) and every download name with it. ``VERSION`` is the technical version and stays put.
"""
RELEASE_MINOR = 1
VERSION = '1.0.0-alpha.1'
DISPLAY_VERSION = f'Alpha 1.{RELEASE_MINOR}'
RELEASE_TITLE = f'Karrierekrake {DISPLAY_VERSION}'
_FILE_VERSION = DISPLAY_VERSION.replace(' ', '-')
WINDOWS_TARGET = 'windows-x86_64'
WINDOWS_SETUP_ASSET = f'Karrierekrake-{_FILE_VERSION}-Windows-Setup.exe'
WINDOWS_ASSET = f'Karrierekrake-{_FILE_VERSION}-Windows-x86_64.zip'
NATIVE_ASSETS = {
    'macos-arm64': f'Karrierekrake-{_FILE_VERSION}-macOS-AppleSilicon.dmg',
    'macos-x86_64': f'Karrierekrake-{_FILE_VERSION}-macOS-Intel.dmg',
    'linux-x86_64': f'Karrierekrake-{_FILE_VERSION}-Linux-x86_64.tar.gz',
}

ASSET_SUFFIXES = {
    'macos-arm64': 'macOS-AppleSilicon.dmg',
    'macos-x86_64': 'macOS-Intel.dmg',
    'linux-x86_64': 'Linux-x86_64.tar.gz',
}
