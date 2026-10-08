"""One draft becomes public only after every OS package is uploaded."""
import json
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

from core import app_updates
from core.release_identity import RELEASE_TITLE, VERSION, WINDOWS_ASSET, WINDOWS_TARGET
from scripts import package_component_update as component
from scripts import publish_alpha_release as alpha


def build_windows(root, commit, monkeypatch):
    exe, model = root / 'exe', root / 'model'
    exe.write_bytes(b'windows program')
    model.write_bytes(b'local model')
    monkeypatch.setattr(component, 'CV_MODEL_SHA256', app_updates.digest(model))
    folder = root / 'windows-source'
    manifest = component.build(exe, model, folder, sequence=42, commit=commit)
    (folder / 'acceptance.json').write_text(json.dumps({'ok': True}))
    return folder, manifest


def test_windows_package_has_no_other_os_or_model(tmp_path, monkeypatch):
    folder, manifest = build_windows(tmp_path, 'a' * 40, monkeypatch)
    assert manifest['target'] == WINDOWS_TARGET and manifest['version'] == VERSION
    with zipfile.ZipFile(folder / WINDOWS_ASSET) as archive:
        assert set(archive.namelist()) == {'Karrierekrake.exe', app_updates.CURRENT, 'INSTALL.txt'}


@pytest.mark.parametrize('fail_target', [None, 'macos-arm64', 'linux-x86_64'])
def test_common_release_only_published_after_all_platforms(tmp_path, monkeypatch, fail_target):
    commit = 'a' * 40
    windows, _manifest = build_windows(tmp_path, commit, monkeypatch)
    calls = []
    monkeypatch.setattr(alpha, 'current_main', lambda: commit)
    def gh(*args, check=True):
        calls.append(args)
        if args[:2] == ('run', 'download'):
            name = args[args.index('--name') + 1]
            dest = Path(args[args.index('--dir') + 1])
            if name == 'Karrierekrake-windows-x86_64':
                shutil.copytree(windows, dest)
            else:
                target = name.removeprefix('Karrierekrake-')
                dest.mkdir()
                (dest / alpha.ASSETS[target]).write_bytes(b'one native platform')
                (dest / 'native-current.json').write_text(json.dumps({
                    'target': target, 'commit': commit, 'sequence': 40, 'version': VERSION}))
                (dest / 'acceptance.json').write_text(json.dumps({'ok': target != fail_target}))
        if args[:2] == ('release', 'view'):
            return subprocess.CompletedProcess(args, 1, '', '')
        return subprocess.CompletedProcess(args, 0, '', '')
    monkeypatch.setattr(alpha, 'gh', gh)
    if fail_target:
        with pytest.raises(ValueError):
            alpha.publish('40', '41', commit)
        assert not any('--draft=false' in call for call in calls)
    else:
        assert alpha.publish('40', '41', commit)
        assert any('--title' in call and RELEASE_TITLE in call for call in calls)
        assert '--draft=false' in calls[-1]
        uploaded = [call for call in calls if call[:2] == ('release', 'upload')]
        assert len(uploaded) == 4
        assert WINDOWS_ASSET in ' '.join(uploaded[0])
        assert not any(name in ' '.join(uploaded[0]) for name in alpha.ASSETS.values())
        for filename in alpha.ASSETS.values():
            assert any(filename in ' '.join(call) for call in uploaded[1:])


def test_superseded_commit_does_not_download_or_publish(monkeypatch):
    monkeypatch.setattr(alpha, 'current_main', lambda: 'b' * 40)
    monkeypatch.setattr(alpha, 'gh', lambda *a, **k: pytest.fail('should not access artifacts'))
    assert not alpha.publish('40', '41', 'a' * 40)
