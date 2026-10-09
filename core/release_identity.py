"""One version and explicit, disjoint downloads for all desktop platforms."""
VERSION = '0.1.0-alpha.1'
DISPLAY_VERSION = 'Alpha 0.1'
RELEASE_TITLE = 'Karrierekrake Alpha 0.1'
WINDOWS_TARGET = 'windows-x86_64'
WINDOWS_ASSET = 'Karrierekrake-Alpha-0.1-Windows-x86_64.zip'
NATIVE_ASSETS = {
    'macos-arm64': 'Karrierekrake-Alpha-0.1-macOS-AppleSilicon.dmg',
    'macos-x86_64': 'Karrierekrake-Alpha-0.1-macOS-Intel.dmg',
    'linux-x86_64': 'Karrierekrake-Alpha-0.1-Linux-x86_64.tar.gz',
}

ASSET_SUFFIXES = {
    'macos-arm64': 'macOS-AppleSilicon.dmg',
    'macos-x86_64': 'macOS-Intel.dmg',
    'linux-x86_64': 'Linux-x86_64.tar.gz',
}
