"""Build the pinned CPU backend, respecting macOS flags despite upstream FORCE.

llama-cpp-python 0.3.35's Apple block forces AVX/FMA off and Metal on after
reading CMAKE_ARGS. Change only those cache defaults in the verified sdist.
No model/runtime code is changed. Windows continues using its pinned wheel.
"""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
from urllib.request import urlopen

VERSION = '0.3.35'
SOURCE_URL = ('https://files.pythonhosted.org/packages/1a/71/'
              '5ecdad726b87527b361d9d95313c6591f27bb3fad79c9ab524ad4250b4c9/'
              'llama_cpp_python-0.3.35.tar.gz')
SOURCE_SHA256 = '1139dbb54509074b70893fab8554e3b079aa9f4d312058ce4018ef0019e3de12'
ROOT = Path(__file__).resolve().parents[1]


def patch_apple_defaults(text: str) -> str:
    for flag, value, help_text in (
        ('GGML_AVX', 'OFF', 'enable AVX'),
        ('GGML_AVX2', 'OFF', 'enable AVX2'),
        ('GGML_FMA', 'OFF', 'enable FMA'),
        ('GGML_F16C', 'OFF', 'enable F16C'),
        ('GGML_METAL', 'ON', 'enable Metal'),
    ):
        original = f'set({flag} "{value}" CACHE BOOL "ggml: {help_text}" FORCE)'
        if text.count(original) != 1:
            raise ValueError(f'native_llama_source_patch_mismatch: {flag}')
        text = text.replace(original, original.replace(' FORCE)', ')'))
    return text


def build(wheel_dir: Path) -> None:
    constraints = (ROOT / 'constraints-runtime.txt').read_text(encoding='utf-8')
    if f'llama-cpp-python=={VERSION}' not in constraints.splitlines():
        raise ValueError('native_llama_version_pin_mismatch')
    wheel_dir.mkdir(parents=True, exist_ok=True)
    wheels = list(wheel_dir.glob(f'llama_cpp_python-{VERSION}-*.whl'))
    if len(wheels) > 1:
        raise ValueError('native_llama_multiple_cached_wheels')
    if not wheels:
        with tempfile.TemporaryDirectory(prefix='kk-llama-build-') as temporary:
            work = Path(temporary)
            archive = work / 'source.tar.gz'
            sha = hashlib.sha256()
            with urlopen(SOURCE_URL, timeout=60) as response, archive.open('wb') as output:
                for block in iter(lambda: response.read(1024 * 1024), b''):
                    sha.update(block)
                    output.write(block)
            if sha.hexdigest() != SOURCE_SHA256:
                raise ValueError('native_llama_source_hash_mismatch')
            with tarfile.open(archive) as source_tar:
                source_tar.extractall(work, filter='data')
            source = work / f'llama_cpp_python-{VERSION}'
            cmake = source / 'CMakeLists.txt'
            cmake.write_text(patch_apple_defaults(cmake.read_text(encoding='utf-8')),
                             encoding='utf-8')
            subprocess.run([sys.executable, '-m', 'pip', 'wheel', '--no-deps',
                            '--no-cache-dir', '--wheel-dir', str(wheel_dir.resolve()),
                            str(source)], env=os.environ.copy(), check=True)
        wheels = list(wheel_dir.glob(f'llama_cpp_python-{VERSION}-*.whl'))
    if len(wheels) != 1:
        raise ValueError('native_llama_wheel_missing')
    subprocess.run([sys.executable, '-m', 'pip', 'install', '--no-deps',
                    '--force-reinstall', str(wheels[0].resolve())], check=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--wheel-dir', type=Path, required=True)
    build(parser.parse_args().wheel_dir)
