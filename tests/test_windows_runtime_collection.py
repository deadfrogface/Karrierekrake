import hashlib
from pathlib import Path
import pytest
from scripts.windows_runtime_collection import coherent_windows_runtime


def inputs(tmp_path):
    prefix = tmp_path / 'verified-runtime'
    expected, rows = {}, []
    for relative in ['python312.dll', 'DLLs/_ssl.pyd', 'DLLs/libcrypto-3-x64.dll', 'DLLs/libssl-3-x64.dll']:
        source = prefix / relative
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(('verified ' + relative).encode())
        expected[relative] = hashlib.sha256(source.read_bytes()).hexdigest()
        old = tmp_path / 'host-toolcache' / source.name
        old.parent.mkdir(exist_ok=True)
        old.write_bytes(b'old unrelated build')
        rows.append((source.name, str(old), 'BINARY'))
    return prefix, expected, rows


def test_host_dlls_cannot_replace_verified_interpreter_tls_pair(tmp_path):
    prefix, expected, rows = inputs(tmp_path)
    unrelated = ('vendor.dll', '/other/vendor.dll', 'BINARY')
    rows.extend([unrelated, ('Qt/plugins/libcrypto-3-x64.dll', '/old/crypto.dll', 'BINARY')])
    result = coherent_windows_runtime(rows, prefix, expected=expected)
    assert unrelated in result
    for destination, source, kind in result:
        if destination != 'vendor.dll':
            assert Path(source).is_relative_to(prefix)
            name = Path(source).relative_to(prefix).as_posix()
            assert hashlib.sha256(Path(source).read_bytes()).hexdigest() == expected[name]
    assert result[-1][0] == 'Qt/plugins/libcrypto-3-x64.dll'


def test_modified_runtime_source_cannot_supply_a_plausible_version_string(tmp_path):
    prefix, expected, rows = inputs(tmp_path)
    (prefix / 'DLLs/libcrypto-3-x64.dll').write_bytes(b'OpenSSL 3.5.9 but wrong binary')
    with pytest.raises(ValueError, match='source_hash_mismatch'):
        coherent_windows_runtime(rows, prefix, expected=expected)


def test_missing_runtime_component_does_not_silently_produce_partial_protection(tmp_path):
    prefix, expected, rows = inputs(tmp_path)
    with pytest.raises(ValueError, match='collection_incomplete'):
        coherent_windows_runtime(rows[:-1], prefix, expected=expected)
