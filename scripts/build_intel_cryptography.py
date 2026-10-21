"""Build the unavailable Intel macOS wheel against hash-pinned static OpenSSL."""
from __future__ import annotations
import argparse
import base64
import csv
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import subprocess
import sys
import tarfile
import tempfile
from urllib.request import urlopen
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def fetch_source(entry, destination):
    size, value = 0, hashlib.sha256()
    with urlopen(entry['url'], timeout=90) as response, destination.open('xb') as output:
        while block := response.read(1024 * 1024):
            size += len(block)
            if size > entry['size']:
                raise ValueError('intel_crypto_source_integrity_failed')
            value.update(block)
            output.write(block)
    if size != entry['size'] or value.hexdigest() != entry['sha256']:
        raise ValueError('intel_crypto_source_integrity_failed')


def extract_source(archive, destination, root):
    with tarfile.open(archive, 'r:gz') as source:
        members = source.getmembers()
        if len(members) > 50000 or sum(m.size for m in members) > 1024**3:
            raise ValueError('intel_crypto_source_archive_invalid')
        seen = set()
        for member in members:
            path = PurePosixPath(member.name)
            if (path.is_absolute() or not path.parts or path.parts[0] != root
                    or '..' in path.parts or '\\' in member.name or path.as_posix() in seen
                    or member.size < 0 or not (member.isfile() or member.isdir() or member.issym())):
                raise ValueError('intel_crypto_source_archive_invalid')
            seen.add(path.as_posix())
        source.extractall(destination, filter='data')
    return destination / root


def enrich_wheel(wheel, sources, license_text, compiler, sdk):
    with zipfile.ZipFile(wheel) as archive:
        entries = {item.filename: (item, archive.read(item)) for item in archive.infolist()}
    roots = {name.rsplit('/', 1)[0] for name in entries if name.endswith('.dist-info/WHEEL')}
    if len(roots) != 1 or any(name.endswith(('RECORD.jws', 'RECORD.p7s')) for name in entries):
        raise ValueError('intel_crypto_wheel_metadata_invalid')
    dist, = roots
    openssl = sources['openssl']
    bom = {'bomFormat': 'CycloneDX', 'specVersion': '1.6', 'version': 1, 'components': [{
        'type': 'library', 'name': 'openssl', 'version': openssl['version'],
        'purl': 'pkg:generic/openssl@' + openssl['version'],
        'licenses': [{'expression': 'Apache-2.0'}],
        'hashes': [{'alg': 'SHA-256', 'content': openssl['sha256']}],
        'externalReferences': [{'type': 'distribution', 'url': openssl['url']}]}]}
    provenance = {'sources': sources, 'compiler': compiler, 'sdk': sdk,
                  'static_openssl': True, 'macos_deployment_target': '13.0',
                  'builder_sha256': digest(__file__),
                  'scope': 'OpenSSL source and static link verified; Rust transitives need their own inventory.'}
    additions = {'sboms/sbom.json': json.dumps(bom, indent=2).encode(),
                 'kk-build-provenance.json': json.dumps(provenance, indent=2).encode(),
                 'licenses/openssl-LICENSE.txt': license_text}
    for relative, content in additions.items():
        name = dist + '/' + relative
        info = zipfile.ZipInfo(name)
        info.external_attr = 0o100644 << 16
        info.compress_type = zipfile.ZIP_DEFLATED
        entries[name] = (info, content)
    record = dist + '/RECORD'
    rows = []
    for name, (_, content) in sorted(entries.items()):
        if name != record:
            value = base64.urlsafe_b64encode(hashlib.sha256(content).digest()).decode().rstrip('=')
            rows.append([name, 'sha256=' + value, str(len(content))])
    rows.append([record, '', ''])
    stream = io.StringIO(newline='')
    csv.writer(stream).writerows(rows)
    info = zipfile.ZipInfo(record)
    info.external_attr = 0o100644 << 16
    entries[record] = (info, stream.getvalue().encode())
    temporary = wheel.with_suffix('.tmp')
    with zipfile.ZipFile(temporary, 'w') as archive:
        for info, content in entries.values():
            archive.writestr(info, content)
    os.replace(temporary, wheel)


def verify_install(wheel):
    subprocess.run([sys.executable, '-m', 'pip', 'install', '-c', str(ROOT / 'constraints-runtime.txt'),
                    '--force-reinstall', str(wheel)], check=True)
    subprocess.run([sys.executable, '-c',
        'from core.security.crypto_runtime import verify_crypto_runtime; print(verify_crypto_runtime())'],
        cwd=ROOT, check=True, timeout=60)
    binding = subprocess.check_output([sys.executable, '-c',
        'import cryptography.hazmat.bindings._rust as rust; print(rust.__file__)'], text=True).strip()
    dependencies = subprocess.check_output(['otool', '-L', binding], text=True)
    if re.search(r'lib(?:ssl|crypto)[./_-]', dependencies, re.I):
        raise ValueError('intel_crypto_wheel_has_external_openssl')


def build(wheel_dir):
    if sys.platform != 'darwin' or platform.machine().lower() != 'x86_64':
        raise ValueError('intel_crypto_requires_native_intel_macos')
    sources = json.loads((ROOT / 'packaging/intel_crypto_sources.json').read_text())
    wheel_dir = Path(wheel_dir).resolve()
    wheel_dir.mkdir(parents=True, exist_ok=True)
    wheels = list(wheel_dir.glob('cryptography-50.0.2-*.whl'))
    receipt = wheel_dir / 'provenance.json'
    if wheels:
        if len(wheels) != 1 or not receipt.is_file():
            raise ValueError('intel_crypto_cache_invalid')
        previous = json.loads(receipt.read_text())
        if (previous.get('sources') != sources or previous.get('wheel_sha256') != digest(wheels[0])
                or previous.get('builder_sha256') != digest(__file__)):
            raise ValueError('intel_crypto_cache_invalid')
        verify_install(wheels[0])
        return
    with tempfile.TemporaryDirectory(prefix='kk-intel-crypto-') as temporary:
        work = Path(temporary)
        archives = {}
        for name, entry in sources.items():
            archive = work / (name + '.tar.gz')
            fetch_source(entry, archive)
            archives[name] = archive
        openssl = extract_source(archives['openssl'], work, sources['openssl']['root'])
        extract_source(archives['cryptography'], work, sources['cryptography']['root'])
        prefix = work / 'openssl-static'
        env = dict(os.environ, MACOSX_DEPLOYMENT_TARGET='13.0',
                   CFLAGS='-O2 -fPIC -mmacosx-version-min=13.0')
        subprocess.run([str(openssl / 'Configure'), 'darwin64-x86_64-cc', 'no-shared', 'no-module',
                        'no-tests', '--libdir=lib', '--prefix=' + str(prefix)],
                       cwd=openssl, env=env, check=True)
        subprocess.run(['make', '-j3'], cwd=openssl, env=env, check=True)
        subprocess.run(['make', 'install_sw'], cwd=openssl, env=env, check=True)
        env.update(OPENSSL_DIR=str(prefix), OPENSSL_LIB_DIR=str(prefix / 'lib'),
                   OPENSSL_INCLUDE_DIR=str(prefix / 'include'), OPENSSL_STATIC='1', OPENSSL_NO_VENDOR='1')
        subprocess.run([sys.executable, '-m', 'pip', 'wheel', '--no-deps', '--no-cache-dir',
                        '--wheel-dir', str(wheel_dir), str(archives['cryptography'])], env=env, check=True)
        wheels = list(wheel_dir.glob('cryptography-50.0.2-*-macosx_*_x86_64.whl'))
        if len(wheels) != 1:
            raise ValueError('intel_crypto_wheel_missing')
        compiler = subprocess.check_output(['clang', '--version'], text=True).splitlines()[0]
        sdk = subprocess.check_output(['xcrun', '--show-sdk-version'], text=True).strip()
        enrich_wheel(wheels[0], sources, (openssl / 'LICENSE.txt').read_bytes(), compiler, sdk)
        verify_install(wheels[0])
        receipt.write_text(json.dumps({'sources': sources, 'wheel_sha256': digest(wheels[0]),
                                       'builder_sha256': digest(__file__)}, indent=2)+'\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wheel-dir', type=Path, required=True)
    build(parser.parse_args().wheel_dir)
