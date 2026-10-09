"""One version and explicit, disjoint downloads for all desktop platforms."""
VERSION = '1.0.0-alpha.1'
DISPLAY_VERSION = 'Alpha 1.0'
RELEASE_TITLE = 'Karrierekrake Alpha 1.0'
WINDOWS_TARGET = 'windows-x86_64'
WINDOWS_ASSET = 'Karrierekrake-Alpha-1.0-Windows-x86_64.zip'
NATIVE_ASSETS = {
    'macos-arm64': 'Karrierekrake-Alpha-1.0-macOS-AppleSilicon.dmg',
    'macos-x86_64': 'Karrierekrake-Alpha-1.0-macOS-Intel.dmg',
    'linux-x86_64': 'Karrierekrake-Alpha-1.0-Linux-x86_64.tar.gz',
}

ASSET_SUFFIXES = {
    'macos-arm64': 'macOS-AppleSilicon.dmg',
    'macos-x86_64': 'macOS-Intel.dmg',
    'linux-x86_64': 'Linux-x86_64.tar.gz',
}
