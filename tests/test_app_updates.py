import hashlib
import io
import json
import sys
import subprocess
import zipfile
import pytest
from core import app_updates as u


def sha(data):
    return hashlib.sha256(data).hexdigest()


def app_zip(marker=b'new'):
    """A program folder as the 'app' component ships it: Karrierekrake.exe plus _internal/."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        archive.writestr('Karrierekrake.exe', b'exe ' + marker)
        archive.writestr('_internal/data.bin', b'lib ' + marker)
    return buffer.getvalue()


NEW_APP = app_zip(b'new')


def manifest(app=NEW_APP, model=b'model', sequence=2):
    tag = f'update-{sequence}-abcdef123456'
    return {'protocol': 1, 'sequence': sequence, 'tag': tag, 'components': {
        name: {'path': u.TARGETS[name], 'size': len(data), 'sha256': sha(data), 'parts': [
            {'size': len(data), 'sha256': sha(data), 'url': f'https://github.com/{u.REPOSITORY}/releases/download/{tag}/{name}-001.bin'}]}
        for name, data in [('app', app), ('model', model)]}}


def installed(root):
    old = manifest(app_zip(b'old'), sequence=1)
    for relative, data in [('Karrierekrake.exe', b'exe old'), ('_internal/data.bin', b'lib old'), (u.MODEL_PATH, b'model')]:
        p = root / relative
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
        return Response(NEW_APP)
    monkeypatch.setattr(u, '_get', get)
    stage = u.stage_update(manifest(), tmp_path)
    assert len(calls) == 1 and calls[0].endswith('/app-001.bin')
    assert (stage / u.APP_ARCHIVE).read_bytes() == NEW_APP
    assert not (stage / u.MODEL_PATH).exists()
    assert (tmp_path / u.MODEL_PATH).read_bytes() == b'model'
    assert (tmp_path / 'Karrierekrake.exe').read_bytes() == b'exe old'
    assert (tmp_path / 'profile.yaml').read_text() == 'user data'


@pytest.mark.parametrize('data', [b'corrupt', b'new app EXTRA'])
def test_corrupt_download_never_changes_install(tmp_path, monkeypatch, data):
    installed(tmp_path)
    monkeypatch.setattr(u, '_get', lambda *a, **kw: Response(data))
    with pytest.raises(ValueError): u.stage_update(manifest(), tmp_path)
    assert (tmp_path / 'Karrierekrake.exe').read_bytes() == b'exe old'
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
    monkeypatch.setattr(u, '_get', lambda *a, **kw: Response(NEW_APP))
    with pytest.raises(ValueError, match='installed_component_modified'):
        u.stage_update(manifest(), tmp_path)
    assert (tmp_path / 'Karrierekrake.exe').read_bytes() == b'exe old'


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows installer helper')
@pytest.mark.parametrize('fail', [False, True])
def test_powershell_transaction_and_rollback(tmp_path, fail):
    installed(tmp_path)
    stage = tmp_path / 'stage'
    stage.mkdir()
    (stage / u.APP_ARCHIVE).write_bytes(NEW_APP)
    (stage / u.CURRENT).write_text(json.dumps(manifest()))
    # Failure occurs after the app swap; manifest source missing exercises rollback.
    if fail: (stage / u.CURRENT).unlink()
    plan = {'root': str(tmp_path), 'files': [u.APP_ARCHIVE, u.CURRENT], 'hashes': {u.APP_ARCHIVE: sha(NEW_APP)},
            'archives': [u.APP_ARCHIVE]}
    (stage / 'plan.json').write_text(json.dumps(plan))
    helper = u.HELPER.replace("  Start-Process -FilePath (Join-Path $root 'Karrierekrake.exe') -WorkingDirectory $root", "  'restarted' | Set-Content -LiteralPath (Join-Path $root 'restarted.txt')")
    script = tmp_path / 'helper.ps1'
    script.write_text(helper, encoding='utf-8-sig')
    subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', str(script), '-Stage', str(stage), '-ParentId', '2147483647'], check=True, timeout=30)
    assert (tmp_path / 'Karrierekrake.exe').read_bytes() == (b'exe old' if fail else b'exe new')
    assert (tmp_path / '_internal' / 'data.bin').read_bytes() == (b'lib old' if fail else b'lib new')
    assert (tmp_path / 'restarted.txt').exists()
    assert (tmp_path / 'update-error.txt').exists() == fail


def test_multiple_parts_stream_into_one_verified_component(tmp_path, monkeypatch):
    installed(tmp_path)
    m = manifest()
    item = m['components']['app']
    data = [NEW_APP[:40], NEW_APP[40:]]
    item['parts'] = [dict(size=len(part), sha256=sha(part), url=f'https://github.com/{u.REPOSITORY}/releases/download/{m["tag"]}/app-{index:03d}.bin') for index, part in enumerate(data, 1)]
    responses = iter(data)
    monkeypatch.setattr(u, '_get', lambda *a, **kw: Response(next(responses)))
    progress = []
    stage = u.stage_update(m, tmp_path, progress=lambda done, total: progress.append((done, total)))
    assert (stage / u.APP_ARCHIVE).read_bytes() == NEW_APP
    assert progress[-1] == (len(NEW_APP), len(NEW_APP))


def test_download_cancel_cleans_staging(tmp_path, monkeypatch):
    installed(tmp_path)
    monkeypatch.setattr(u, '_get', lambda *a, **kw: Response(NEW_APP))
    with pytest.raises(RuntimeError, match='update_cancelled'):
        u.stage_update(manifest(), tmp_path, cancelled=lambda: True)
    assert not list(tmp_path.glob('.kk-update-*'))
    assert (tmp_path / 'Karrierekrake.exe').read_bytes() == b'exe old'


@pytest.mark.parametrize('target', ['linux-x86_64', 'macos-arm64', 'macos-x86_64'])
def test_windows_updater_refuses_foreign_platform_manifest(target):
    value = manifest()
    value['target'] = target
    with pytest.raises(ValueError, match='wrong_update_platform'):
        u.validate_manifest(value, value['tag'])


def test_initial_model_setup_after_finding_newer_app_uses_installed_release(tmp_path, monkeypatch):
    current = installed(tmp_path)
    (tmp_path / u.MODEL_PATH).unlink()
    newer = manifest(NEW_APP, sequence=2)
    calls = []
    def get(url, **kwargs):
        calls.append(url)
        return Response(b'model')
    monkeypatch.setattr(u, '_get', get)
    stage = u.stage_update(newer, tmp_path, only_components={'model'})
    assert calls == [current['components']['model']['parts'][0]['url']]
    assert (stage / u.MODEL_PATH).read_bytes() == b'model'
    assert json.loads((stage / u.CURRENT).read_text()) == current
    assert not (stage / u.APP_ARCHIVE).exists()
    assert (tmp_path / u.TARGETS['app']).read_bytes() == b'exe old'
    assert not (tmp_path / u.MODEL_PATH).exists()


def test_installer_restart_does_not_reuse_deleted_onefile_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, 'platform', 'win32')
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setenv('SystemRoot', str(tmp_path))
    monkeypatch.setenv('_PYI_APPLICATION_HOME_DIR', 'old-deleted-extraction')
    monkeypatch.delenv('PYINSTALLER_RESET_ENVIRONMENT', raising=False)
    monkeypatch.setattr(subprocess, 'CREATE_NO_WINDOW', 0x08000000, raising=False)
    launches = []
    monkeypatch.setattr(subprocess, 'Popen', lambda argv, **kw: launches.append((argv, kw)))
    u.launch_installer(tmp_path)
    assert launches[0][1]['env']['PYINSTALLER_RESET_ENVIRONMENT'] == '1'
    # Do not change the running application's environment or its workers.
    assert u.os.environ.get('PYINSTALLER_RESET_ENVIRONMENT') != '1'
    assert "$env:PYINSTALLER_RESET_ENVIRONMENT = '1'" in (tmp_path / 'install.ps1').read_text(encoding='utf-8-sig')


def test_update_never_downgrades_existing_install(tmp_path, monkeypatch):
    installed(tmp_path)
    newer = manifest(NEW_APP, sequence=3)
    (tmp_path / u.CURRENT).write_text(json.dumps(newer))
    monkeypatch.setattr(u, '_get', lambda *a, **kw: pytest.fail('downgrade downloaded bytes'))
    with pytest.raises(ValueError, match='update_downgrade_refused'):
        u.stage_update(manifest(sequence=2), tmp_path)


def test_cross_version_partial_update_cannot_mislabel_existing_application(tmp_path, monkeypatch):
    installed(tmp_path)
    monkeypatch.setattr(u, '_get', lambda *a, **kw: pytest.fail('partial update downloaded bytes'))
    with pytest.raises(ValueError, match='partial_cross_version_update'):
        u.stage_update(manifest(sequence=2), tmp_path, only_components={'app'})
    assert u.read_current(tmp_path)['sequence'] == 1
    assert (tmp_path / u.TARGETS['app']).read_bytes() == b'exe old'


def test_check_refuses_corrupt_installed_release_identity(tmp_path, monkeypatch):
    installed(tmp_path)
    (tmp_path / u.CURRENT).write_text('{"sequence": 999}')
    monkeypatch.setattr(u, '_json', lambda *a: pytest.fail('invalid install contacted network'))
    with pytest.raises(ValueError, match='unsupported_update_protocol'):
        u.check_for_update(tmp_path)


def test_app_archive_must_hold_exactly_the_program_folder(tmp_path):
    def write(*members):
        path = tmp_path / 'a.zip'
        with zipfile.ZipFile(path, 'w') as archive:
            for name, data in members:
                archive.writestr(name, data)
        return path
    u.verify_app_archive(write(('Karrierekrake.exe', b'x'), ('_internal/a.dll', b'y')))
    for members in [
        (('Karrierekrake.exe', b'x'),),                                           # no _internal
        (('_internal/a.dll', b'y'),),                                             # no exe
        (('Karrierekrake.exe', b'x'), ('_internal/a.dll', b'y'), ('profile.yaml', b'z')),  # foreign top-level entry
        (('Karrierekrake.exe', b'x'), ('_internal/../escape.txt', b'y')),         # path traversal
        (('Karrierekrake.exe', b'x'), ('/abs/a.dll', b'y')),
        (('Karrierekrake.exe', b'x'), ('C:/evil.dll', b'y')),
    ]:
        with pytest.raises(ValueError):
            u.verify_app_archive(write(*members))


def test_unpacked_size_limit_is_enforced(tmp_path, monkeypatch):
    monkeypatch.setattr(u, 'MAX_UNPACKED', 10)
    path = tmp_path / 'a.zip'
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('Karrierekrake.exe', b'x' * 8)
        archive.writestr('_internal/a.dll', b'y' * 8)
    with pytest.raises(ValueError, match='invalid_app_archive'):
        u.verify_app_archive(path)


def test_staging_refuses_a_malicious_app_archive_before_anything_is_installed(tmp_path, monkeypatch):
    installed(tmp_path)
    evil = io.BytesIO()
    with zipfile.ZipFile(evil, 'w') as archive:
        archive.writestr('Karrierekrake.exe', b'x')
        archive.writestr('_internal/../../outside.txt', b'y')
    bad = evil.getvalue()
    monkeypatch.setattr(u, '_get', lambda *a, **kw: Response(bad))
    with pytest.raises(ValueError, match='unsafe_app_archive_member'):
        u.stage_update(manifest(app=bad), tmp_path)
    assert (tmp_path / 'Karrierekrake.exe').read_bytes() == b'exe old'
    assert not list(tmp_path.glob('.kk-update-*'))


def test_unchanged_app_is_not_downloaded_again_and_stays_intact(tmp_path, monkeypatch):
    m = installed(tmp_path)
    calls = []
    monkeypatch.setattr(u, '_get', lambda url, **kw: calls.append(url) or Response(b'model'))
    (tmp_path / u.MODEL_PATH).unlink()
    u.stage_update(m, tmp_path, only_components={'model'})
    assert all('/model-001.bin' in c for c in calls)
    (tmp_path / '_internal' / 'data.bin').unlink()
    (tmp_path / '_internal').rmdir()
    with pytest.raises(ValueError, match='installed_component_modified'):
        u.stage_update(m, tmp_path, only_components={'model'})
