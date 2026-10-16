from pathlib import Path

import pytest

from scripts import macos_openssl as ssl


def pair(tmp_path, name):
    directory = tmp_path / name
    directory.mkdir()
    for lib in ssl.NAMES:
        (directory / lib).touch()
    return directory


def test_mixed_collection_uses_complete_newer_pair(tmp_path, monkeypatch):
    python = pair(tmp_path, 'python')
    brew = pair(tmp_path, 'brew')
    monkeypatch.setattr(ssl, 'dylib_version', lambda p: (3, 6, 0) if Path(p).parent == brew else (3, 0, 0))
    unrelated = ('other.so', '/other.so', 'EXTENSION')
    entries = [('libssl.3.dylib', str(python / 'libssl.3.dylib'), 'BINARY'),
               ('libcrypto.3.dylib', str(brew / 'libcrypto.3.dylib'), 'BINARY'), unrelated]
    result = ssl.coherent_openssl(entries)
    assert unrelated in result
    assert {e[0] for e in result if e != unrelated} == ssl.NAMES
    assert all(Path(e[1]).parent == brew for e in result if e != unrelated)


def test_missing_pair_fails_closed(tmp_path, monkeypatch):
    library = tmp_path / 'libssl.3.dylib'
    library.touch()
    monkeypatch.setattr(ssl, 'dylib_version', lambda p: (3, 6, 0))
    with pytest.raises(RuntimeError, match='No coherent'):
        ssl.coherent_openssl([(library.name, str(library), 'BINARY')])


def test_mismatched_pair_rejected(tmp_path, monkeypatch):
    directory = pair(tmp_path, 'broken')
    monkeypatch.setattr(ssl, 'dylib_version', lambda p: (3, 6, 0) if Path(p).name.startswith('libssl') else (3, 0, 0))
    with pytest.raises(RuntimeError, match='No coherent'):
        ssl.coherent_openssl([(p.name, str(p), 'BINARY') for p in directory.iterdir()])


def test_inspection_never_loads_library(monkeypatch, tmp_path):
    library = tmp_path / "libssl.3.dylib"
    (tmp_path / "libcrypto.3.dylib").write_bytes(b"OpenSSL 3.6.3 1 Oct 2026\x00")
    def inspect(args, **kwargs):
        assert args == ['otool', '-L', str(library)]
        return '/lib/libssl.3.dylib:\n\t@rpath/libssl.3.dylib (compatibility version 3.0.0, current version 3.0.0)\n'
    monkeypatch.setattr(ssl.subprocess, 'check_output', inspect)
    assert ssl.dylib_version(library) == (3, 6, 3)
