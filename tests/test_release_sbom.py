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
