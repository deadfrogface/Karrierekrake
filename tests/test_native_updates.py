import json
import sys

import pytest

from core import native_updates as n


def release(target='macos-arm64', sequence=2):
    tag = 'update-23-' + 'b' * 12
    base = f'https://github.com/{n.REPOSITORY}/releases/download/{tag}/'
    manifest = {'protocol': 1, 'target': target, 'tag': tag, 'sequence': sequence,
                'commit': 'b' * 40, 'sha256': 'c' * 64, 'size': 100, 'url': base + n.ASSETS[target]}
    url = base + f'native-manifest-{target}.json'
    info = {'tag_name': tag, 'assets': [{'browser_download_url': url}, {'browser_download_url': manifest['url']}]}
    return info, manifest, url


def test_new_native_release_is_platform_specific(monkeypatch):
    monkeypatch.setattr(n, "runtime_target", lambda: "macos-arm64")
    info, manifest, url = release()
    monkeypatch.setattr(n, '_json', lambda requested: manifest if requested == url else [info])
    installed = {'target': 'macos-arm64', 'commit': 'a' * 40, 'sequence': 1}
    assert n.check_for_update(installed) == manifest
    assert n.check_for_update(dict(installed, target='linux-x86_64')) is None
    assert n.check_for_update(dict(installed, sequence=3)) is None
    assert n.check_for_update(dict(installed, commit='b' * 40)) is None
    info['prerelease'] = True
    assert n.check_for_update(installed) is None


@pytest.mark.parametrize('mutation', [
    {'url': 'https://evil.example/update.dmg'}, {'target': 'linux-x86_64'},
    {'sequence': '2'}, {'size': -1}, {'sha256': 'invalid'}, {'protocol': 9},
])
def test_untrusted_native_manifest_rejected(monkeypatch, mutation):
    monkeypatch.setattr(n, "runtime_target", lambda: "macos-arm64")
    info, manifest, url = release()
    manifest.update(mutation)
    monkeypatch.setattr(n, '_json', lambda requested: manifest if requested == url else [info])
    with pytest.raises(ValueError):
        n.check_for_update({'target': 'macos-arm64', 'commit': 'a' * 40, 'sequence': 1})


def test_packaged_native_identity_and_source_no_network(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(sys, '_MEIPASS', str(tmp_path), raising=False)
    monkeypatch.setattr(n, 'runtime_target', lambda: 'linux-x86_64')
    value = {'target': 'linux-x86_64', 'commit': 'a' * 40, 'sequence': 1}
    (tmp_path / n.METADATA).write_text(json.dumps(value))
    assert n.current() == value
    monkeypatch.setattr(sys, 'frozen', False)
    monkeypatch.setattr(n, '_json', lambda _: pytest.fail('source checkout contacted network'))
    assert n.current() == {}
    assert n.check_for_update() is None


def test_native_panel_uses_native_checks_and_never_windows_installer(qtbot, tmp_path, monkeypatch):
    from desktop.widgets import update_panel as ui
    monkeypatch.setattr(n, 'runtime_target', lambda: 'linux-x86_64')
    value = {'target': 'linux-x86_64', 'commit': 'a' * 40, 'sequence': 1}
    monkeypatch.setattr(sys, 'platform', 'linux')
    monkeypatch.setattr(n, 'current', lambda: value)
    monkeypatch.setattr(ui.updates, 'install_root', lambda: tmp_path)
    monkeypatch.setattr(ui.updates, 'check_for_update', lambda: pytest.fail('Windows update check'))
    _info, manifest, _url = release(target='linux-x86_64')
    monkeypatch.setattr(n, 'check_for_update', lambda installed, **kwargs: manifest)
    monkeypatch.setattr(ui.native_models, 'available', lambda: True)
    opened = []
    monkeypatch.setattr(ui.QDesktopServices, 'openUrl', lambda url: opened.append(url.toString()) or True)
    panel = ui.UpdatePanel()
    qtbot.addWidget(panel)
    panel.check(quiet=True)
    qtbot.waitUntil(lambda: not panel.busy)
    assert panel.manifest == manifest
    panel.retranslate()
    panel.install()
    assert opened == [manifest['url']]


@pytest.mark.parametrize('platform,machine,target', [
    ('win32', 'AMD64', None), ('linux', 'x86_64', 'linux-x86_64'),
    ('darwin', 'arm64', 'macos-arm64'), ('darwin', 'x86_64', 'macos-x86_64'),
    ('linux', 'aarch64', None),
])
def test_runtime_platform_and_architecture(monkeypatch, platform, machine, target):
    monkeypatch.setattr(sys, 'platform', platform)
    monkeypatch.setattr(n.platform, 'machine', lambda: machine)
    assert n.runtime_target() == target


def test_wrong_platform_is_rejected_before_any_network(monkeypatch):
    monkeypatch.setattr(n, 'runtime_target', lambda: 'linux-x86_64')
    monkeypatch.setattr(n, '_json', lambda _: pytest.fail('wrong platform triggered a download'))
    assert n.check_for_update({'target': 'macos-arm64', 'commit': 'a' * 40, 'sequence': 1}) is None



def test_future_version_filename_stays_on_same_platform(monkeypatch):
    monkeypatch.setattr(n, 'runtime_target', lambda: 'macos-arm64')
    info, manifest, url = release()
    manifest['url'] = manifest['url'].replace('Alpha-0.1-', 'Alpha-0.2-')
    info['assets'][1]['browser_download_url'] = manifest['url']
    monkeypatch.setattr(n, '_json', lambda requested: manifest if requested == url else [info])
    assert n.check_for_update({'target': 'macos-arm64', 'commit': 'a' * 40, 'sequence': 1}) == manifest


def test_first_setup_can_find_current_release_without_app_update(monkeypatch):
    monkeypatch.setattr(n, 'runtime_target', lambda: 'macos-arm64')
    info, manifest, url = release()
    monkeypatch.setattr(n, '_json', lambda requested: manifest if requested == url else [info])
    installed = {'target': 'macos-arm64', 'commit': 'b' * 40, 'sequence': 2}
    assert n.check_for_update(installed) is None
    assert n.check_for_update(installed, include_current=True) == manifest


def test_native_first_setup_downloads_model_without_windows_installer(qtbot, tmp_path, monkeypatch):
    from desktop.widgets import update_panel as ui
    value = {'target': 'linux-x86_64', 'commit': 'a' * 40, 'sequence': 1}
    monkeypatch.setattr(sys, 'platform', 'linux')
    monkeypatch.setattr(n, 'current', lambda: value)
    monkeypatch.setattr(ui.updates, 'install_root', lambda: tmp_path)
    monkeypatch.setattr(ui.updates, 'launch_installer', lambda *a: pytest.fail('Windows installer'))
    monkeypatch.setattr(ui.QDesktopServices, 'openUrl', lambda *a: pytest.fail('app download during model setup'))
    ready = []
    monkeypatch.setattr(ui.native_models, 'available', lambda: bool(ready))
    _info, manifest, _url = release(target='linux-x86_64')
    def check(installed, *, include_current):
        assert include_current
        return manifest
    monkeypatch.setattr(n, 'check_for_update', check)
    def download(received, **kwargs):
        assert received == manifest
        ready.append(True)
        return tmp_path / 'model.gguf'
    monkeypatch.setattr(ui.native_models, 'download', download)
    panel = ui.UpdatePanel()
    qtbot.addWidget(panel)
    panel.install()  # Find the model in this platform's current release.
    qtbot.waitUntil(lambda: not panel.busy)
    panel.install()
    qtbot.waitUntil(lambda: not panel.busy)
    assert ready and panel.manifest is None
    assert panel.install_button.isHidden()
