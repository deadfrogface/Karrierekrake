"""Install a hash-pinned isolated CPython 3.12 build for Windows/macOS CI.

setup-python still bootstraps this script; it does not supply security-only
CPython patch binaries for these platforms. No package resolver chooses the
interpreter. All archives, sizes and SHA-256 values are committed explicitly.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import subprocess
import sys
import tarfile
import tempfile
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]


def validate_members(members):
    if len(members) > 20000 or sum(m.size for m in members) > 512 * 1024**2:
        raise ValueError('ci_python_archive_invalid')
    seen = set()
    for m in members:
        path = PurePosixPath(m.name)
        if (path.is_absolute() or not path.parts or path.parts[0] != 'python'
                or '..' in path.parts or '\\' in m.name or path.as_posix() in seen
                or m.size < 0 or not (m.isfile() or m.isdir() or m.issym())):
            raise ValueError('ci_python_archive_invalid')
        seen.add(path.as_posix())


def runtime_target(system=None, machine=None):
    system, machine = system or sys.platform, (machine or platform.machine()).lower()
    targets = {('win32', 'amd64'): 'x86_64-pc-windows-msvc',
               ('win32', 'x86_64'): 'x86_64-pc-windows-msvc',
               ('darwin', 'arm64'): 'aarch64-apple-darwin',
               ('darwin', 'aarch64'): 'aarch64-apple-darwin',
               ('darwin', 'x86_64'): 'x86_64-apple-darwin'}
    if (system, machine) not in targets:
        raise ValueError('ci_python_target_unsupported')
    return targets[(system, machine)]


def prepare():
    config = json.loads((ROOT / 'packaging/ci_python_runtimes.json').read_text())
    entry = config['runtimes'][runtime_target()]
    prefix = 'https://github.com/astral-sh/python-build-standalone/releases/download/' + config['release'] + '/'
    if not entry['url'].startswith(prefix) or len(entry['sha256']) != 64:
        raise ValueError('ci_python_source_invalid')
    destination = Path(os.environ['RUNNER_TEMP']) / 'kk-patched-python'
    destination.mkdir(exist_ok=False)
    with tempfile.TemporaryDirectory(prefix='kk-python-download-') as temporary:
        archive = Path(temporary) / 'runtime.tar.gz'
        digest, size = hashlib.sha256(), 0
        with urlopen(entry['url'], timeout=90) as response, archive.open('xb') as output:
            while block := response.read(1024 * 1024):
                size += len(block)
                if size > entry['size']:
                    raise ValueError('ci_python_integrity_failed')
                digest.update(block)
                output.write(block)
        if size != entry['size'] or digest.hexdigest() != entry['sha256']:
            raise ValueError('ci_python_integrity_failed')
        with tarfile.open(archive, 'r:gz') as source:
            validate_members(source.getmembers())
            source.extractall(destination, filter='data')
    for relative, expected_hash in entry.get('files', {}).items():
        source = destination / 'python' / relative
        with source.open('rb') as stream:
            if hashlib.file_digest(stream, 'sha256').hexdigest() != expected_hash:
                raise ValueError('ci_python_critical_file_mismatch')
    python = destination / ('python/python.exe' if sys.platform == 'win32' else 'python/bin/python3.12')
    if sys.platform == 'win32':
        # A Windows venv python.exe redirects through another process. Keep
        # direct source-worker PID / Job Object semantics, while all packages
        # still live inside this fresh RUNNER_TEMP installation.
        environment, executable = destination / 'python', python
    else:
        environment = destination / 'venv'
        subprocess.run([str(python), '-m', 'venv', str(environment)], check=True, timeout=120)
        executable = environment / 'bin/python'
    # Verify the actual interpreter and its ssl module, not archive filenames.
    probe = subprocess.check_output([str(executable), '-c',
        'import json,sys,ssl; from core.security.tls_version import openssl_release; '
        'print(json.dumps({"python":list(sys.version_info[:3]),'
        '"openssl":list(openssl_release(ssl.OPENSSL_VERSION_INFO)),'
        '"openssl_api_info":list(ssl.OPENSSL_VERSION_INFO),"openssl_text":ssl.OPENSSL_VERSION}))'],
        text=True, timeout=30, cwd=ROOT)
    actual = json.loads(probe)
    print('ci_python_runtime_probe=' + json.dumps(actual, sort_keys=True), flush=True)
    if (actual.get('python') != [3, 12, 15] or actual.get('openssl') != [3, 5, 9]
            or not actual.get('openssl_text', '').startswith('OpenSSL 3.5.9 ')):
        raise ValueError('ci_python_runtime_mismatch')
    receipt = {'version': config['version'], 'release': config['release'], **entry}
    (destination / 'python/kk-runtime-provenance.json').write_text(json.dumps(receipt) + '\n')
    with open(os.environ['GITHUB_PATH'], 'a', encoding='utf-8') as path:
        path.write(str(executable.parent) + '\n')
    with open(os.environ['GITHUB_ENV'], 'a', encoding='utf-8') as env:
        for name in ('pythonLocation', 'Python_ROOT_DIR', 'Python2_ROOT_DIR', 'Python3_ROOT_DIR'):
            env.write(name + '=' + str(environment) + '\n')
        if sys.platform != 'win32':
            env.write('VIRTUAL_ENV=' + str(environment) + '\n')
        env.write('PKG_CONFIG_PATH=' + str(destination / 'python/lib/pkgconfig') + '\n')
    print('ci_python=3.12.15 openssl=3.5.9 sha256=' + entry['sha256'], flush=True)


if __name__ == '__main__':
    prepare()
