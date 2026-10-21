"""Fingerprint native build inputs without invalidating on unrelated CI edits."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shlex
import shutil
import subprocess
import sys
import sysconfig

ROOT = Path(__file__).resolve().parents[1]
BUILD_ENV = ('CC', 'CXX', 'CFLAGS', 'CXXFLAGS', 'CPPFLAGS', 'LDFLAGS',
             'ARCHFLAGS', 'CMAKE_ARGS', 'CMAKE_GENERATOR', 'CMAKE_BUILD_TYPE',
             'MACOSX_DEPLOYMENT_TARGET', 'CMAKE_OSX_DEPLOYMENT_TARGET', 'SDKROOT')


def compiler_identity(variable, default):
    command = shlex.split(os.environ.get(variable, '')) or [shutil.which(default) or default]
    result = subprocess.run([*command, '--version'], capture_output=True, text=True,
                            timeout=20, check=True)
    return {'command': command, 'version': result.stdout.strip()}


def build_key(target, identity, *, root=ROOT, environment=None):
    environment = os.environ if environment is None else environment
    inputs = {path: hashlib.sha256((root / path).read_bytes()).hexdigest()
              for path in ('scripts/build_native_llama.py',
                           'scripts/native_build_cache_key.py', 'constraints-runtime.txt')}
    payload = {'target': target, 'identity': identity, 'files': inputs,
               'environment': {key: environment.get(key, '') for key in BUILD_ENV}}
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    return 'native-llama-' + target + '-' + digest


def host_identity(target):
    machine = platform.machine().lower()
    actual = ('macos-' if sys.platform == 'darwin' else 'linux-') + (
        'arm64' if machine in {'aarch64', 'arm64'} else machine)
    if actual != target:
        raise ValueError('native_cache_target_host_mismatch')
    identity = {'python': platform.python_version(), 'soabi': sysconfig.get_config_var('SOABI'),
                'machine': machine, 'libc': platform.libc_ver(), 'macos': platform.mac_ver()[0],
                'cc': compiler_identity('CC', 'cc'), 'cxx': compiler_identity('CXX', 'c++')}
    if sys.platform == 'darwin':
        identity['sdk'] = subprocess.run(['xcrun', '--show-sdk-version'], capture_output=True,
                                         text=True, timeout=20, check=True).stdout.strip()
    return identity


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', required=True,
                        choices=['linux-x86_64', 'macos-arm64', 'macos-x86_64'])
    args = parser.parse_args()
    key = build_key(args.target, host_identity(args.target))
    print(key)
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as output:
            output.write('key=' + key + '\n')


if __name__ == '__main__':
    main()
