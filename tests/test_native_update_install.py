import io
import json
import tarfile
import hashlib
from pathlib import Path
import pytest
from core import native_update_install as module


def test_checksum_failure_never_replaces_app(tmp_path, monkeypatch):
    root = tmp_path / 'Karrierekrake'
    root.mkdir()
    (root / 'Karrierekrake').write_bytes(b'old version')
    monkeypatch.setattr(module, 'install_location', lambda: root)
    monkeypatch.setattr(module, 'current', lambda: {'sequence': 1, 'commit': 'a' * 40})
    monkeypatch.setattr(module, 'runtime_target', lambda: 'linux-x86_64')
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def iter_content(self, size): yield b'bad'
    monkeypatch.setattr(module, '_get', lambda *a, **kw: Response())
    manifest = {'protocol': 1, 'target': 'linux-x86_64', 'sequence': 2, 'commit': 'b' * 40,
                'tag': 'update-2-' + 'b' * 12, 'size': 3, 'sha256': '0' * 64}
    manifest['url'] = f"https://github.com/{module.REPOSITORY}/releases/download/{manifest['tag']}/Karrierekrake-Alpha-1.0-Linux-x86_64.tar.gz"
    with pytest.raises(ValueError, match='integrity'):
        module.stage_update(manifest)
    assert (root / 'Karrierekrake').read_bytes() == b'old version'
    assert not list(tmp_path.glob('.kk-native-update-*'))
