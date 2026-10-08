import hashlib
import json
import sys
import subprocess
import pytest
from core import app_updates as u


def sha(data):
    return hashlib.sha256(data).hexdigest()


def manifest(app=b'new app', model=b'model', sequence=2):
    tag = f'update-{sequence}-abcdef123456'
    return {'protocol': 1, 'sequence': sequence, 'tag': tag, 'components': {
        name: {'path': u.TARGETS[name], 'size': len(data), 'sha256': sha(data), 'parts': [
            {'size': len(data), 'sha256': sha(data), 'url': f'https://github.com/{u.REPOSITORY}/releases/download/{tag}/{name}-001.bin'}]}
        for name, data in [('app', app), ('model', model)]}}


def installed(root):
    old = manifest(b'old app', sequence=1)
    for name, data in [('app', b'old app'), ('model', b'model')]:
        p = root / u.TARGETS[name]
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    (root / u.CURRENT).write_text(json.dumps(old))
    return old


class Response:
    def __init__(self, data): self.data = data
    def __enter__(self): return self
    def __exit__(self, *a): pass
    def iter_content(self, size): yield self.data


@pytest.mark.parametrize('mutation', [
    lambda m: m.update(protocol=3),
    lambda m: m['components']['app'].update(path='../user.yaml'),
    lambda m: m['components']['app']['parts'][0].update(url='http://evil.org/app.bin'),
    lambda m: m['components']['app'].update(sha256='bad'),
    lambda m: m['components']['app']['parts'][0].update(size=2_000_000_001),
    lambda m: m['components'].update(extra={}),
])
def test_untrusted_manifest_rejected(mutation):
    m = manifest()
    mutation(m)
    with pytest.raises(ValueError): u.validate_manifest(m, m['tag'])


def test_ui_update_downloads_app_only_and_keeps_model_and_profile(tmp_path, monkeypatch):
    installed(tmp_path)
    (tmp_path / 'profile.yaml').write_text('user data')
    calls = []
    def get(url, **kwargs):
        calls.append(url)
        return Response(b'new app')
    monkeypatch.setattr(u, '_get', get)
    stage = u.stage_update(manifest(), tmp_path)
    assert len(calls) == 1 and calls[0].endswith('/app-001.bin')
    assert (stage / 'Karrierekrake.exe').read_bytes() == b'new app'
    assert not (stage / u.MODEL_PATH).exists()
    assert (tmp_path / u.MODEL_PATH).read_bytes() == b'model'
    assert (tmp_path / 'Karrierekrake.exe').read_bytes() == b'old app'
    assert (tmp_path / 'profile.yaml').read_text() == 'user data'


@pytest.mark.parametrize('data', [b'corrupt', b'new app EXTRA'])
def test_corrupt_download_never_changes_install(tmp_path, monkeypatch, data):
    installed(tmp_path)
    monkeypatch.setattr(u, '_get', lambda *a, **kw: Response(data))
    with pytest.raises(ValueError): u.stage_update(manifest(), tmp_path)
    assert (tmp_path / 'Karrierekrake.exe').read_bytes() == b'old app'
    assert not list(tmp_path.glob('.kk-update-*'))


def test_first_install_downloads_missing_model_only(tmp_path, monkeypatch):
    m = installed(tmp_path)
    (tmp_path / u.MODEL_PATH).unlink()
    calls = []
    def get(url, **kw):
        calls.append(url)
        return Response(b'model')
    monkeypatch.setattr(u, '_get', get)
    stage = u.stage_update(m, tmp_path)
    assert len(calls) == 1 and '/model-001.bin' in calls[0]
    assert (stage / u.MODEL_PATH).read_bytes() == b'model'


def test_latest_release_is_monotonic_and_uses_fixed_repo(tmp_path, monkeypatch):
    installed(tmp_path)
    m = manifest()
    url = f'https://github.com/{u.REPOSITORY}/releases/download/{m["tag"]}/update-manifest.json'
    release = {'tag_name': m['tag'], 'assets': [{'browser_download_url': url}]}
    monkeypatch.setattr(u, '_json', lambda source: release if source == u.API else m)
    assert u.check_for_update(tmp_path) == m
    (tmp_path / u.CURRENT).write_text(json.dumps(m))
    assert u.check_for_update(tmp_path) is None
    release['prerelease'] = True
    assert u.check_for_update(tmp_path) is None


def test_retained_model_is_verified_before_install(tmp_path, monkeypatch):
    installed(tmp_path)
    (tmp_path / u.MODEL_PATH).write_bytes(b'altered')
    monkeypatch.setattr(u, '_get', lambda *a, **kw: Response(b'new app'))
    with pytest.raises(ValueError, match='installed_component_modified'):
        u.stage_update(manifest(), tmp_path)
    assert (tmp_path / 'Karrierekrake.exe').read_bytes() == b'old app'


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows installer helper')
@pytest.mark.parametrize('fail', [False, True])
def test_powershell_transaction_and_rollback(tmp_path, fail):
    installed(tmp_path)
    stage = tmp_path / 'stage'
    stage.mkdir()
    (stage / 'Karrierekrake.exe').write_bytes(b'new app')
    (stage / u.CURRENT).write_text(json.dumps(manifest()))
    # Failure occurs after app copy; manifest source missing exercises rollback.
    if fail: (stage / u.CURRENT).unlink()
    plan = {'root': str(tmp_path), 'files': ['Karrierekrake.exe', u.CURRENT], 'hashes': {'Karrierekrake.exe': sha(b'new app')}}
    (stage / 'plan.json').write_text(json.dumps(plan))
    helper = u.HELPER.replace("  Start-Process -FilePath (Join-Path $root 'Karrierekrake.exe') -WorkingDirectory $root", "  'restarted' | Set-Content -LiteralPath (Join-Path $root 'restarted.txt')")
    script = tmp_path / 'helper.ps1'
    script.write_text(helper, encoding='utf-8-sig')
    subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', str(script), '-Stage', str(stage), '-ParentId', '2147483647'], check=True, timeout=30)
    assert (tmp_path / 'Karrierekrake.exe').read_bytes() == (b'old app' if fail else b'new app')
    assert (tmp_path / 'restarted.txt').exists()
    assert (tmp_path / 'update-error.txt').exists() == fail


def test_multiple_parts_stream_into_one_verified_component(tmp_path, monkeypatch):
    installed(tmp_path)
    m = manifest()
    item = m['components']['app']
    data = [b'new ', b'app']
    item['parts'] = [dict(size=len(part), sha256=sha(part), url=f'https://github.com/{u.REPOSITORY}/releases/download/{m["tag"]}/app-{index:03d}.bin') for index, part in enumerate(data, 1)]
    responses = iter(data)
    monkeypatch.setattr(u, '_get', lambda *a, **kw: Response(next(responses)))
    progress = []
    stage = u.stage_update(m, tmp_path, progress=lambda done, total: progress.append((done, total)))
    assert (stage / 'Karrierekrake.exe').read_bytes() == b'new app'
    assert progress[-1] == (7, 7)


def test_download_cancel_cleans_staging(tmp_path, monkeypatch):
    installed(tmp_path)
    monkeypatch.setattr(u, '_get', lambda *a, **kw: Response(b'new app'))
    with pytest.raises(RuntimeError, match='update_cancelled'):
        u.stage_update(manifest(), tmp_path, cancelled=lambda: True)
    assert not list(tmp_path.glob('.kk-update-*'))
    assert (tmp_path / 'Karrierekrake.exe').read_bytes() == b'old app'


@pytest.mark.parametrize('target', ['linux-x86_64', 'macos-arm64', 'macos-x86_64'])
def test_windows_updater_refuses_foreign_platform_manifest(target):
    value = manifest()
    value['target'] = target
    with pytest.raises(ValueError, match='wrong_update_platform'):
        u.validate_manifest(value, value['tag'])
