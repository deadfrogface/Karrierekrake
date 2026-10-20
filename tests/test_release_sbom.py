"""Inventory the actual resolved inputs, without inventing native licenses."""
import hashlib
import json
from pathlib import Path

from scripts import export_release_sbom as sbom


def inventory(tmp_path, monkeypatch, *, version=True, distributions=()):
    monkeypatch.setattr(sbom.metadata, 'packages_distributions', lambda: {})
    monkeypatch.setattr(sbom.metadata, 'distributions', lambda: list(distributions))
    geo_dir = tmp_path / 'data/geo'
    geo_dir.mkdir(parents=True)
    payload = geo_dir / 'DE.txt'
    payload.write_bytes(b'synthetic public geodata')
    (geo_dir / 'manifest.json').write_text(json.dumps({
        'files': {'DE': {'path': 'DE.txt', 'sha256': hashlib.sha256(payload.read_bytes()).hexdigest()}},
        'version': 'test', 'license': 'test-only-license', 'source_url': 'https://example.org/',
        'attribution': 'synthetic attribution'}))
    crypto = tmp_path / 'libcrypto.3.dylib'
    crypto.write_bytes(b'OpenSSL 3.6.3 1 Oct 2026\x00' if version else b'unknown')
    ssl = tmp_path / 'libssl.3.dylib'
    ssl.write_bytes(b'library')
    font = tmp_path / 'font.ttf'
    font.write_bytes(b'synthetic font')
    out = tmp_path / 'out'
    sbom.export_release_inventory(tmp_path, out, [
        ('libssl.3.dylib', ssl, 'BINARY'), ('libcrypto.3.dylib', crypto, 'BINARY')], [],
        [('assets/font.ttf', font, 'DATA')])
    return out


def test_native_versions_hashes_and_unknown_rights_remain_explicit(tmp_path, monkeypatch):
    out = inventory(tmp_path, monkeypatch)
    raw = (out / 'release-sbom.json').read_text()
    assert str(tmp_path) not in raw
    components = json.loads(raw)['components']
    native = [c for c in components if c['bom-ref'].startswith('native:')]
    assert len(native) == 2
    assert all(c['version'] == '3.6.3' and c['hashes'][0]['content'] for c in native)
    assert all('licenses' not in c for c in native)
    review = json.loads((out / 'license-review.json').read_text())
    assert review['status'] == 'review-required'
    assert 'asset-rights:assets/font.ttf' in review['unresolved']
    assert 'native:libcrypto.3.dylib' in review['unresolved']


def test_unidentified_native_version_is_not_silently_complete(tmp_path, monkeypatch):
    out = inventory(tmp_path, monkeypatch, version=False)
    review = json.loads((out / 'license-review.json').read_text())
    assert 'native-version:libcrypto.3.dylib' in review['unresolved']


def test_corrupt_dataset_refuses_sbom(tmp_path, monkeypatch):
    out = inventory(tmp_path, monkeypatch)
    (tmp_path / 'data/geo/DE.txt').write_bytes(b'corrupt')
    import pytest
    with pytest.raises(ValueError, match='dataset_inventory_hash_mismatch'):
        sbom.export_release_inventory(tmp_path, out, [], [])


def test_binary_only_distribution_is_not_lost(tmp_path, monkeypatch):
    class Distribution:
        metadata = {'Name': 'binary-only', 'License-Expression': 'MIT'}
        version = '1.2.3'
        files = [Path('libcrypto.3.dylib')]
        def locate_file(self, file):
            return tmp_path / file
    out = inventory(tmp_path, monkeypatch, distributions=[Distribution()])
    components = json.loads((out / 'release-sbom.json').read_text())['components']
    owner = next(c for c in components if c['name'] == 'binary-only')
    native = next(c for c in components if c['bom-ref'] == 'native:libcrypto.3.dylib')
    assert owner['version'] == '1.2.3'
    assert native['licenses'] == [{'expression': 'MIT'}]
    review = json.loads((out / 'license-review.json').read_text())
    assert 'native:libcrypto.3.dylib' not in review['unresolved']


def test_os_package_version_remains_separate_from_native_abi(tmp_path, monkeypatch):
    from scripts import native_package_metadata
    owner = {'name': 'libssl3:amd64', 'version': '3.0.2-0ubuntu1.20',
             'bom-ref': 'os-package:libssl3:amd64',
             'purl': 'pkg:deb/ubuntu/libssl3@3.0.2-0ubuntu1.20?arch=amd64&distro=ubuntu-22.04'}
    monkeypatch.setattr(native_package_metadata, 'linux_packages', lambda paths: {
        str((tmp_path / 'libcrypto.3.dylib').resolve()): owner})
    out = inventory(tmp_path, monkeypatch)
    components = json.loads((out / 'release-sbom.json').read_text())['components']
    package = next(c for c in components if c['bom-ref'] == owner['bom-ref'])
    native = next(c for c in components if c['bom-ref'] == 'native:libcrypto.3.dylib')
    assert package['version'] == '3.0.2-0ubuntu1.20'
    assert native['version'] == '3.6.3'
    assert {'name':'kk:os-package', 'value':owner['bom-ref']} in native['properties']


def test_python_runtime_version_is_separate_and_license_review_remains_open(tmp_path, monkeypatch):
    from scripts import native_python_metadata
    runtime = {'type': 'library', 'name': 'CPython', 'version': '3.12.12',
               'bom-ref': 'runtime:cpython',
               'properties': [{'name': 'kk:version-source', 'value': 'build-interpreter'}]}
    monkeypatch.setattr(native_python_metadata, 'python_runtime_owners', lambda paths: {
        str((tmp_path / 'libcrypto.3.dylib').resolve()): runtime})
    out = inventory(tmp_path, monkeypatch)
    components = json.loads((out / 'release-sbom.json').read_text())['components']
    native = next(c for c in components if c['bom-ref'] == 'native:libcrypto.3.dylib')
    assert {'name': 'kk:python-runtime', 'value': 'runtime:cpython'} in native['properties']
    assert next(c for c in components if c['bom-ref'] == 'runtime:cpython')['version'] == '3.12.12'
    assert 'licenses' not in runtime
    review = json.loads((out / 'license-review.json').read_text())
    assert 'runtime-license:CPython' in review['unresolved']


def test_production_inventory_cannot_succeed_without_identifying_its_python_runtime(tmp_path, monkeypatch):
    import pytest
    from scripts import native_python_metadata
    inventory(tmp_path, monkeypatch)
    monkeypatch.setattr(native_python_metadata, 'python_runtime_owners', lambda paths: {})
    with pytest.raises(ValueError, match='python_runtime_unidentified'):
        sbom.export_release_inventory(tmp_path, tmp_path / 'required-output', [], [],
                                      require_python_runtime=True)


def test_windows_and_linux_openssl_record_the_minor_release(tmp_path, monkeypatch):
    """T08.03: the SBOM names the embedded OpenSSL release, not only the shared SONAME."""
    monkeypatch.setattr(sbom.metadata, 'packages_distributions', lambda: {})
    monkeypatch.setattr(sbom.metadata, 'distributions', lambda: [])
    geo_dir = tmp_path / 'data/geo'
    geo_dir.mkdir(parents=True)
    (geo_dir / 'DE.txt').write_bytes(b'synthetic public geodata')
    (geo_dir / 'manifest.json').write_text(json.dumps({
        'files': {'DE': {'path': 'DE.txt', 'sha256': hashlib.sha256(b'synthetic public geodata').hexdigest()}},
        'version': 'test', 'license': 'test-only-license', 'source_url': 'https://example.org/',
        'attribution': 'synthetic attribution'}))
    files = {
        'libcrypto-3-x64.dll': b'..OpenSSL 3.5.9 30 Sep 2026..', 'libssl-3-x64.dll': b'library',
        'libcrypto.so.3': b'..OpenSSL 3.0.2 15 Mar 2022..', 'libssl.so.3': b'library',
    }
    rows = []
    for name, content in files.items():
        (tmp_path / name).write_bytes(content)
        rows.append((name, tmp_path / name, 'BINARY'))
    out = tmp_path / 'out'
    sbom.export_release_inventory(tmp_path, out, rows, [], [])
    versions = {c['name']: c.get('version') for c in json.loads((out / 'release-sbom.json').read_text())['components']
                if c['bom-ref'].startswith('native:')}
    assert versions == {'libcrypto-3-x64.dll': '3.5.9', 'libssl-3-x64.dll': '3.5.9',
                        'libcrypto.so.3': '3.0.2', 'libssl.so.3': '3.0.2'}
    assert sbom._openssl_crypto_name('LIBSSL-3-X64.DLL') == 'libcrypto-3-x64.dll'
    assert sbom._openssl_crypto_name('libz.so.1') == ''


def test_license_review_check_accepts_the_exporter_output_and_rejects_drift(tmp_path, monkeypatch):
    """T08.02.03: license-review.json is checked for content, not only preserved."""
    from scripts.ci_license_review_check import check

    out = inventory(tmp_path, monkeypatch)
    summary = check(out)
    assert summary['ok'], summary['problems']
    assert summary['unresolved_by_kind']['asset-rights'] == 1
    review = json.loads((out / 'license-review.json').read_text())
    review['unresolved'] = [e for e in review['unresolved'] if not e.startswith('native:')]
    (out / 'license-review.json').write_text(json.dumps(review))
    drifted = check(out)
    assert not drifted['ok']
    assert any('native component without license' in p for p in drifted['problems'])


def test_packaged_notices_must_match_the_build_and_cover_distro_packages(tmp_path, monkeypatch):
    """T08.05.01: THIRD_PARTY_NOTICES.txt ships inside the package with every distro copyright text."""
    from scripts.ci_license_review_check import check_package

    out = inventory(tmp_path, monkeypatch)
    sbom = json.loads((out / 'release-sbom.json').read_text())
    sbom['components'].append({'type': 'library', 'name': 'zlib1g', 'bom-ref': 'os-package:zlib1g'})
    (out / 'release-sbom.json').write_text(json.dumps(sbom))
    package = tmp_path / 'pkg' / '_internal'
    package.mkdir(parents=True)
    assert check_package(out, package.parent) == ['THIRD_PARTY_NOTICES.txt missing from the built package']
    built = (out / 'THIRD_PARTY_NOTICES.txt').read_bytes()
    (package / 'THIRD_PARTY_NOTICES.txt').write_bytes(built)
    assert check_package(out, package.parent) == ['no copyright text for distro package zlib1g']
    notices = built + b'\n--- distro package: zlib1g ---\nCopyright zlib authors\n'
    (out / 'THIRD_PARTY_NOTICES.txt').write_bytes(notices)
    (package / 'THIRD_PARTY_NOTICES.txt').write_bytes(notices)
    assert check_package(out, package.parent) == []
