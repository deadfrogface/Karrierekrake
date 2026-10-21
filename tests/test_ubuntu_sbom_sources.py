import copy

import pytest
from scripts import enrich_ubuntu_sbom_sources as sources


def component():
    return {'name': 'libexample:amd64', 'version': '1.2-3build1', 'bom-ref': 'os-package:libexample:amd64',
            'purl': 'pkg:deb/ubuntu/libexample@1.2-3build1?arch=amd64&distro=ubuntu-22.04'}


def publication():
    return {'binary_package_name': 'libexample', 'binary_package_version': '1.2-3build1',
            'distro_arch_series_link': sources.API + 'ubuntu/jammy/amd64',
            'build_link': sources.API + 'ubuntu/+source/example/1.2-3/+build/123'}


def test_different_source_version_is_taken_from_actual_build_and_original_is_preserved():
    original = {'components': [component()]}
    before = copy.deepcopy(original)
    def fetch(url):
        if '/+build/' in url:
            return {'source_package_name': 'example', 'source_package_version': '1.2-3'}
        return {'entries': [publication(), publication()]}
    enriched, failures = sources.enrich(original, fetch=fetch, workers=1)
    assert original == before
    assert not failures
    properties = enriched['components'][0]['properties']
    assert {'name': 'kk:source-package', 'value': 'example'} in properties
    assert {'name': 'kk:source-version', 'value': '1.2-3'} in properties
    assert sum(p['name'] == 'kk:source-build' for p in properties) == 1


@pytest.mark.parametrize('changed', ['version', 'architecture', 'empty', 'ambiguous', 'pagination'])
def test_missing_or_conflicting_provenance_never_guesses_source_version(changed):
    row = publication()
    if changed == 'version': row['binary_package_version'] = 'wrong'
    if changed == 'architecture': row['distro_arch_series_link'] = sources.API + 'ubuntu/jammy/arm64'
    def fetch(url):
        if '/+build/' in url:
            return {'source_package_name': 'example', 'source_package_version': 'different' if url.endswith('124') else '1.2-3'}
        page = {'entries': [] if changed == 'empty' else [row]}
        if changed == 'ambiguous': page['entries'].append({**row, 'build_link': row['build_link'][:-3] + '124'})
        if changed == 'pagination': page['next_collection_link'] = url
        return page
    enriched, failures = sources.enrich({'components': [component()]}, fetch=fetch, workers=1)
    assert failures
    assert 'properties' not in enriched['components'][0]


def test_metadata_requests_cannot_follow_untrusted_origins():
    with pytest.raises(ValueError, match='unexpected_provenance_origin'):
        sources.get_json('https://example.invalid/1.0/build/123')


def test_publication_pages_are_all_checked():
    calls = []
    def fetch(url):
        calls.append(url)
        if '/+build/' in url:
            return {'source_package_name': 'example', 'source_package_version': '1.2-3'}
        if url.endswith('second'):
            return {'entries': [publication()]}
        return {'entries': [], 'next_collection_link': sources.API + 'second'}
    assert sources.source_identity(component(), fetch=fetch)[:2] == ('example', '1.2-3')
    assert len(calls) == 3
