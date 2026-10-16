"""Choose one ABI-compatible OpenSSL pair without loading foreign dylibs.

Python and native wheels can require different OpenSSL 3 minor versions.
PyInstaller deduplicates by basename, so mixing their libssl/libcrypto is unsafe.
"""
from pathlib import Path
import re
import subprocess

NAMES = frozenset({'libssl.3.dylib', 'libcrypto.3.dylib'})


def openssl_release(path):
    """Read the embedded OpenSSL 3 release without executing/loading a library."""
    versions = re.findall(rb'OpenSSL (3)\.(\d+)\.(\d+)', Path(path).read_bytes())
    if not versions:
        raise RuntimeError(f'Cannot identify OpenSSL release: {path}')
    return max(tuple(map(int, v)) for v in versions)


def dylib_version(path):
    output = subprocess.check_output(['otool', '-L', str(path)], text=True)
    # The first dependency line of a dylib is its own LC_ID_DYLIB.
    lines = output.splitlines()
    match = re.search(r'current version (\d+)\.(\d+)\.(\d+)', lines[1] if len(lines) > 1 else '')
    if not match:
        raise RuntimeError(f'Cannot inspect OpenSSL ABI: {path}')
    abi = tuple(map(int, match.groups()))
    # OpenSSL 3 keeps LC_ID_DYLIB at 3.0.0 across minor releases. Read the
    # embedded version string from libcrypto rather than loading it into Python.
    crypto = Path(path).parent / 'libcrypto.3.dylib'
    release = openssl_release(crypto)
    if abi[0] != release[0]:
        raise RuntimeError(f'OpenSSL ABI/release mismatch: {path}')
    return release


def coherent_openssl(binaries, *, extra_dirs=()):
    """Keep required TLS libraries, selecting a complete pair at the newest ABI.

    A missing or too-old pair fails the build instead of producing an app that
    silently depends on Homebrew or the Python installation on the build host.
    """
    entries = [e for e in binaries if Path(e[0]).name in NAMES]
    if not entries:
        raise RuntimeError('macOS build did not collect Python OpenSSL libraries')
    required = max(dylib_version(e[1]) for e in entries)
    directories = {Path(e[1]).parent for e in entries} | {Path(p) for p in extra_dirs}
    choices = []
    for directory in sorted(directories):
        pair = [directory / name for name in sorted(NAMES)]
        if not all(p.is_file() for p in pair):
            continue
        versions = [dylib_version(p) for p in pair]
        if versions[0] == versions[1] and versions[0] >= required:
            choices.append((versions[0], str(directory), pair))
    if not choices:
        raise RuntimeError(f'No coherent OpenSSL pair satisfies ABI {required}')
    _, _, pair = max(choices)
    result = [e for e in binaries if Path(e[0]).name not in NAMES]
    result.extend((p.name, str(p), 'BINARY') for p in pair)
    return result
