"""Prevent PyInstaller dependency search from substituting older Windows DLLs."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def coherent_windows_runtime(binaries, prefix, *, expected=None):
    if expected is None:
        config = json.loads((ROOT / 'packaging/ci_python_runtimes.json').read_text())
        expected = config['runtimes']['x86_64-pc-windows-msvc']['files']
    sources = {}
    for relative, digest in expected.items():
        source = Path(prefix) / relative
        try:
            with source.open('rb') as stream:
                actual = hashlib.file_digest(stream, 'sha256').hexdigest()
        except OSError as exc:
            raise ValueError('windows_runtime_source_missing') from exc
        if actual != digest:
            raise ValueError('windows_runtime_source_hash_mismatch')
        sources[source.name.casefold()] = source
    required, collected, result = set(sources), set(), []
    for row in binaries:
        name = str(row[0]).replace('\\', '/').rsplit('/', 1)[-1].casefold()
        if name in sources:
            # Preserve every destination (including Qt plugin paths), while
            # requiring every copy of the same runtime DLL to share provenance.
            result.append((row[0], str(sources[name]), row[2]))
            collected.add(name)
        else:
            result.append(row)
    if collected != required:
        raise ValueError('windows_runtime_collection_incomplete')
    return result
