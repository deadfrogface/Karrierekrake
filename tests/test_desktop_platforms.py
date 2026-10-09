"""Native user paths, browser layouts and portable archive permissions."""
import sys
import tarfile
from pathlib import Path

import pytest

from core.platform_paths import user_data_dir
from desktop.services.browser_install import find_chromium_executable


@pytest.fixture
def clean_env(monkeypatch, tmp_path):
    for key in ['KARRIEREKRAKE_DATA_DIR', 'LOCALAPPDATA', 'XDG_DATA_HOME']:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(Path, 'home', lambda: tmp_path)
    return tmp_path


@pytest.mark.parametrize('platform,relative', [
    ('win32', 'AppData/Local/Karrierekrake'),
    ('darwin', 'Library/Application Support/Karrierekrake'),
    ('linux', '.local/share/Karrierekrake'),
])
def test_native_data_locations(monkeypatch, clean_env, platform, relative):
    monkeypatch.setattr(sys, 'platform', platform)
    assert user_data_dir() == clean_env / relative


def test_xdg_absolute_and_override_precedence(monkeypatch, clean_env):
    monkeypatch.setattr(sys, 'platform', 'linux')
    monkeypatch.setenv('XDG_DATA_HOME', str(clean_env / 'xdg'))
    assert user_data_dir() == clean_env / 'xdg/Karrierekrake'
    monkeypatch.setenv('XDG_DATA_HOME', 'relative-is-invalid')
    assert user_data_dir() == clean_env / '.local/share/Karrierekrake'
    monkeypatch.setenv('LOCALAPPDATA', str(clean_env / 'ci'))
    assert user_data_dir() == clean_env / 'ci/Karrierekrake'
    monkeypatch.setenv('KARRIEREKRAKE_DATA_DIR', str(clean_env / 'explicit'))
    assert user_data_dir() == clean_env / 'explicit'
    monkeypatch.setenv('KARRIEREKRAKE_DATA_DIR', 'relative')
    with pytest.raises(ValueError):
        user_data_dir()


def test_mac_data_does_not_import_windows_legacy(monkeypatch, clean_env):
    from desktop import paths
    monkeypatch.setattr(sys, 'platform', 'darwin')
    monkeypatch.setattr(paths, 'migrate_legacy_appdata_if_needed', lambda _: pytest.fail('Windows migration on Mac'))
    assert paths.app_data_dir() == user_data_dir()
    assert paths.app_data_dir().is_dir()


@pytest.mark.parametrize('relative', [
    'chromium-123/chrome-linux/chrome',
    'chromium-123/chrome-linux64/chrome',
    'chromium-123/chrome-mac/Chromium.app/Contents/MacOS/Chromium',
    'chromium-123/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing',
    'chromium_headless_shell-123/chrome-mac-arm64/headless_shell',
    'chromium_headless_shell-123/chrome-linux/headless_shell',
])
def test_native_browser_detection(tmp_path, relative):
    exe = tmp_path / relative
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b'fake browser')
    assert find_chromium_executable(tmp_path) == exe


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX archive permissions and symlinks")
def test_linux_archive_preserves_symlinks_and_executable(tmp_path, monkeypatch):
    from scripts import package_native_release as p
    dist = tmp_path / 'dist'
    app = dist / 'Karrierekrake'
    app.mkdir(parents=True)
    exe = app / 'Karrierekrake'
    exe.write_bytes(b'native executable')
    exe.chmod(0o755)
    (app / 'link').symlink_to('Karrierekrake')
    fake_root = tmp_path / 'repo'
    (fake_root / 'packaging').mkdir(parents=True)
    (fake_root / 'packaging' / p.METADATA).write_text('{}')
    monkeypatch.setattr(p, 'ROOT', fake_root)
    archive = p.package('linux-x86_64', dist, tmp_path / 'out')
    with tarfile.open(archive) as bundle:
        assert bundle.getmember('Karrierekrake/Karrierekrake').mode & 0o111
        assert bundle.getmember('Karrierekrake/link').issym()
