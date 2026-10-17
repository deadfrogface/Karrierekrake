"""Do not depend on an old tarfile data filter for hard-link/symlink safety."""
import tarfile

import pytest
from core.native_update_install import _validate_archive_members


def member(name, kind=tarfile.REGTYPE, target='', size=0):
    entry = tarfile.TarInfo(name)
    entry.type, entry.linkname, entry.size = kind, target, size
    return entry


def test_real_bundle_layout_keeps_internal_symlinks_and_direct_regular_hard_links():
    entries = [member('Karrierekrake/bin/app'),
               member('Karrierekrake/app', tarfile.SYMTYPE, 'bin/app'),
               member('Karrierekrake/copy', tarfile.LNKTYPE, 'Karrierekrake/bin/app')]
    _validate_archive_members(entries)


def test_hard_link_cannot_rebase_a_symlink_target_like_cpython_gh_157190():
    entries = [member('Karrierekrake/deep/inner/link', tarfile.SYMTYPE, '../../outside'),
               member('Karrierekrake/rebased', tarfile.LNKTYPE, 'Karrierekrake/deep/inner/link')]
    with pytest.raises(ValueError, match='archive_invalid'):
        _validate_archive_members(entries)


@pytest.mark.parametrize('entries', [
    [member('Karrierekrake/link', tarfile.LNKTYPE, '../outside')],
    [member('Karrierekrake/link', tarfile.LNKTYPE, '/outside')],
    [member('Karrierekrake/link', tarfile.LNKTYPE, 'Karrierekrake/missing')],
    [member('Karrierekrake/link', tarfile.LNKTYPE, 'Karrierekrake/other'),
     member('Karrierekrake/other', tarfile.LNKTYPE, 'Karrierekrake/link')],
    [member('Karrierekrake/file'), member('Karrierekrake/./file', tarfile.SYMTYPE, 'other')],
    [member('Karrierekrake/../outside')],
    [member('Karrierekrake/negative', size=-1)],
    [member('Karrierekrake/oversized', size=20 * 1024**3 + 1)],
])
def test_ambiguous_escaping_or_unbounded_members_are_rejected(entries):
    with pytest.raises(ValueError, match='archive_invalid'):
        _validate_archive_members(entries)


def test_malicious_release_is_rejected_before_extraction_and_preserves_outside_file(tmp_path, monkeypatch):
    import hashlib
    import io
    import stat
    from core import native_update_install as updater
    victim = tmp_path / 'outside-private.txt'
    victim.write_text('synthetic outside marker')
    victim.chmod(0o640)
    before = victim.stat()
    root = tmp_path / 'Karrierekrake'
    root.mkdir()
    (root / 'Karrierekrake').write_bytes(b'old installed application')
    data = io.BytesIO()
    with tarfile.open(fileobj=data, mode='w:gz') as archive:
        archive.addfile(member('Karrierekrake/deep/inner/link', tarfile.SYMTYPE, '../../outside-private.txt'))
        archive.addfile(member('Karrierekrake/rebased', tarfile.LNKTYPE, 'Karrierekrake/deep/inner/link'))
    payload = data.getvalue()
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def iter_content(self, size): yield payload
    monkeypatch.setattr(updater, 'install_location', lambda: root)
    monkeypatch.setattr(updater, 'current', lambda: {'sequence': 1, 'commit': 'a' * 40})
    monkeypatch.setattr(updater, 'runtime_target', lambda: 'linux-x86_64')
    monkeypatch.setattr(updater, '_get', lambda *a, **k: Response())
    def forbidden_extract(*args, **kwargs):
        pytest.fail('unsafe archive reached tarfile extraction')
    monkeypatch.setattr(tarfile.TarFile, 'extractall', forbidden_extract)
    tag = 'update-2-' + 'b' * 12
    manifest = {'protocol': 1, 'target': 'linux-x86_64', 'sequence': 2, 'commit': 'b' * 40,
                'tag': tag, 'size': len(payload), 'sha256': hashlib.sha256(payload).hexdigest(),
                'url': f'https://github.com/{updater.REPOSITORY}/releases/download/{tag}/Karrierekrake-Alpha-1.0-Linux-x86_64.tar.gz'}
    with pytest.raises(ValueError, match='archive_invalid'):
        updater.stage_update(manifest)
    after = victim.stat()
    assert victim.read_text() == 'synthetic outside marker'
    assert stat.S_IMODE(before.st_mode) == stat.S_IMODE(after.st_mode)
    assert before.st_mtime_ns == after.st_mtime_ns
    assert (root / 'Karrierekrake').read_bytes() == b'old installed application'
    assert not list(tmp_path.glob('.kk-native-update-*'))


def test_actual_expanded_footprint_is_checked_before_writing_payload(tmp_path, monkeypatch):
    import hashlib
    import io
    from types import SimpleNamespace
    from core import native_update_install as updater
    root = tmp_path / 'Karrierekrake'
    root.mkdir()
    (root / 'Karrierekrake').write_bytes(b'old installed application')
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode='w:gz') as archive:
        entry = member('Karrierekrake/large-data.bin', size=1024 * 1024)
        archive.addfile(entry, io.BytesIO(b'0' * entry.size))
    payload = stream.getvalue()
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def iter_content(self, size): yield payload
    monkeypatch.setattr(updater, 'install_location', lambda: root)
    monkeypatch.setattr(updater, 'current', lambda: {'sequence': 1, 'commit': 'a' * 40})
    monkeypatch.setattr(updater, 'runtime_target', lambda: 'linux-x86_64')
    monkeypatch.setattr(updater, '_get', lambda *a, **k: Response())
    space = iter([10**9, 100_100_000])
    monkeypatch.setattr(updater.shutil, 'disk_usage', lambda _: SimpleNamespace(free=next(space)))
    monkeypatch.setattr(tarfile.TarFile, 'extractall', lambda *a, **k: pytest.fail('disk check came too late'))
    tag = 'update-2-' + 'b' * 12
    manifest = {'protocol': 1, 'target': 'linux-x86_64', 'sequence': 2, 'commit': 'b' * 40,
                'tag': tag, 'size': len(payload), 'sha256': hashlib.sha256(payload).hexdigest(),
                'url': f'https://github.com/{updater.REPOSITORY}/releases/download/{tag}/Karrierekrake-Alpha-1.0-Linux-x86_64.tar.gz'}
    with pytest.raises(OSError, match='insufficient_update_space'):
        updater.stage_update(manifest)
    assert (root / 'Karrierekrake').read_bytes() == b'old installed application'
    assert not list(tmp_path.glob('.kk-native-update-*'))
