"""The release SBOM names the distribution whose files are actually collected (Teamlead 19.10.2026).

Two installed distributions can own the same top-level module: urllib3-future
(via caldav -> niquests) replaces the files of ``urllib3``. PyInstaller then
collects urllib3-future's code; the SBOM must list ``urllib3-future 2.25.901``
and not ``urllib3 2.8.0``, whose files are not in the package.
"""
import base64
import hashlib
import json
from importlib import metadata

from scripts import export_release_sbom as sbom


def _record_hash(data: bytes) -> str:
    return 'sha256=' + base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b'=').decode()


def _dist(site, name, version, files):
    info = site / f"{name.replace('-', '_')}-{version}.dist-info"
    info.mkdir(parents=True)
    (info / 'METADATA').write_text(f'Metadata-Version: 2.4\nName: {name}\nVersion: {version}\n'
                                   'License-Expression: MIT\n', encoding='utf-8')
    rows = [f'{path},{_record_hash(data)},{len(data)}' for path, data in files.items()]
    (info / 'RECORD').write_text('\n'.join(rows) + '\n', encoding='utf-8')
    return metadata.PathDistribution(info)


def _inventory(tmp_path, monkeypatch, dists, owners, pure):
    monkeypatch.setattr(sbom.metadata, 'packages_distributions', lambda: owners)
    monkeypatch.setattr(sbom.metadata, 'distributions', lambda: list(dists))
    geo_dir = tmp_path / 'data/geo'
    geo_dir.mkdir(parents=True)
    payload = geo_dir / 'DE.txt'
    payload.write_bytes(b'synthetic public geodata')
    (geo_dir / 'manifest.json').write_text(json.dumps({
        'files': {'DE': {'path': 'DE.txt', 'sha256': hashlib.sha256(payload.read_bytes()).hexdigest()}},
        'version': 'test', 'license': 'test-only-license', 'source_url': 'https://example.org/',
        'attribution': 'synthetic attribution'}))
    out = tmp_path / 'out'
    sbom.export_release_inventory(tmp_path, out, [], pure)
    components = json.loads((out / 'release-sbom.json').read_text())['components']
    review = json.loads((out / 'license-review.json').read_text())
    libraries = {(c['name'], c['version']) for c in components if c['type'] == 'library'}
    return libraries, review


def _site_with_overwritten_urllib3(tmp_path, shipped=b'# urllib3-future\n'):
    site = tmp_path / 'site'
    (site / 'urllib3').mkdir(parents=True)
    (site / 'urllib3' / '__init__.py').write_bytes(shipped)
    (site / 'urllib3' / '_version.py').write_bytes(b'__version__ = "2.25.901"\n')
    classic = _dist(site, 'urllib3', '2.8.0', {
        'urllib3/__init__.py': b'# urllib3 classic\n', 'urllib3/_version.py': b'__version__ = "2.8.0"\n'})
    future = _dist(site, 'urllib3-future', '2.25.901', {
        'urllib3/__init__.py': b'# urllib3-future\n', 'urllib3/_version.py': b'__version__ = "2.25.901"\n'})
    pure = [('urllib3', site / 'urllib3' / '__init__.py', 'PYMODULE'),
            ('urllib3._version', site / 'urllib3' / '_version.py', 'PYMODULE')]
    return [classic, future], {'urllib3': ['urllib3', 'urllib3-future']}, pure


def test_sbom_lists_the_distribution_whose_files_are_collected(tmp_path, monkeypatch):
    dists, owners, pure = _site_with_overwritten_urllib3(tmp_path)
    libraries, review = _inventory(tmp_path, monkeypatch, dists, owners, pure)
    assert ('urllib3-future', '2.25.901') in libraries
    assert ('urllib3', '2.8.0') not in libraries
    assert not [u for u in review['unresolved'] if u.startswith('module-owner')]


def test_shared_module_matching_no_record_stays_listed_and_unresolved(tmp_path, monkeypatch):
    dists, owners, pure = _site_with_overwritten_urllib3(tmp_path, shipped=b'# patched locally\n')
    libraries, review = _inventory(tmp_path, monkeypatch, dists, owners, pure)
    assert {('urllib3', '2.8.0'), ('urllib3-future', '2.25.901')} <= libraries
    assert 'module-owner-ambiguous:urllib3' in review['unresolved']


def test_single_owner_module_is_unchanged(tmp_path, monkeypatch):
    site = tmp_path / 'site'
    (site / 'jobspy').mkdir(parents=True)
    (site / 'jobspy' / '__init__.py').write_bytes(b'# local edit, hash differs\n')
    jobspy = _dist(site, 'python-jobspy', '1.3.0', {'jobspy/__init__.py': b'# jobspy\n'})
    libraries, review = _inventory(tmp_path, monkeypatch, [jobspy], {'jobspy': ['python-jobspy']},
                                   [('jobspy', site / 'jobspy' / '__init__.py', 'PYMODULE')])
    assert ('python-jobspy', '1.3.0') in libraries
    assert not [u for u in review['unresolved'] if u.startswith('module-owner')]
