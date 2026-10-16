"""Inventory the actual resolved inputs, without inventing native licenses."""
import hashlib
import json
from pathlib import Path

from scripts import export_release_sbom as sbom


def inventory(tmp_path, monkeypatch, *, version=True):
    monkeypatch.setattr(sbom.metadata, 'packages_distributions', lambda: {})
    monkeypatch.setattr(sbom.metadata, 'distributions', lambda: [])
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
