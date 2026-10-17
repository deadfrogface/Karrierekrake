import hashlib
import json

import pytest
from scripts.embedded_sbom import collected_components


def fixture(tmp_path, document):
    path = tmp_path / 'source.json'
    path.write_text(json.dumps(document))
    return [('cryptography-50.0.2.dist-info/sboms/sbom.json', path, 'DATA')]


def test_embedded_library_identity_is_not_the_python_distribution_version(tmp_path):
    rows = fixture(tmp_path, {'bomFormat': 'CycloneDX', 'components': [{
        'type': 'library', 'name': 'openssl', 'version': '4.0.3',
        'purl': 'pkg:generic/openssl@4.0.3',
        'bom-ref': '/private/build/absolute/path',
        'licenses': [{'expression': 'Apache-2.0'}]}]})
    components, unresolved = collected_components(rows)
    assert not unresolved
    c, = components
    assert c['name'] == 'openssl' and c['version'] == '4.0.3'
    assert c['purl'] == 'pkg:generic/openssl@4.0.3'
    assert c['properties'][1]['value'] == hashlib.sha256(rows[0][1].read_bytes()).hexdigest()
    assert '/private/build' not in json.dumps(components)


def test_local_workspace_is_not_invented_as_a_registry_dependency(tmp_path):
    rows = fixture(tmp_path, {'bomFormat': 'CycloneDX', 'components': [{
        'type': 'library', 'name': 'private-component', 'version': '1.0',
        'purl': 'pkg:cargo/private-component@1.0?download_url=file:///build'}]})
    components, unresolved = collected_components(rows)
    assert 'purl' not in components[0]
    assert any(v.startswith('embedded-identity:') for v in unresolved)
    assert any(v.startswith('embedded-license:') for v in unresolved)


@pytest.mark.parametrize('document', [None, {}, {'bomFormat': 'CycloneDX', 'components': {}},
    {'bomFormat': 'CycloneDX', 'components': [None]},
    {'bomFormat': 'CycloneDX', 'components': [{'type': 'library', 'name': 'x', 'version': ''}]}])
def test_invalid_embedded_inventory_fails_closed(tmp_path, document):
    with pytest.raises(ValueError, match='embedded_sbom_invalid'):
        collected_components(fixture(tmp_path, document))


def test_duplicate_inventory_is_rejected(tmp_path):
    rows = fixture(tmp_path, {'bomFormat': 'CycloneDX', 'components': []})
    with pytest.raises(ValueError, match='duplicate_input'):
        collected_components(rows + rows)
