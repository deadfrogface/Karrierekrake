import pytest
from scripts.audit_native_packages import audit, package_query, query_all


def bom():
    return {'components': [
        {'bom-ref': 'os-package:libssl3:amd64', 'purl': 'pkg:deb/ubuntu/libssl3@3.0.2-0ubuntu1.20?distro=ubuntu-22.04',
         'properties': [{'name': 'kk:source-package', 'value': 'openssl'},
                        {'name': 'kk:source-version', 'value': '3.0.2-0ubuntu1.20'}]},
        {'bom-ref': 'native:libcrypto.so.3',
         'properties': [{'name': 'kk:os-package', 'value': 'os-package:libssl3:amd64'}]}]}


def test_exact_source_version_not_binary_name_or_soname_is_queried():
    calls = []
    def query(payload):
        calls.append(payload)
        return {}
    report = audit(bom(), query=query)
    assert calls == [{'package': {'name': 'openssl', 'ecosystem': 'Ubuntu:22.04:LTS'},
                      'version': '3.0.2-0ubuntu1.20'}]
    assert not report['unverified']
    assert not report['finding_ids']


def test_pagination_and_findings_are_retained():
    calls = []
    def query(payload):
        calls.append(payload)
        if 'page_token' not in payload:
            return {'vulns': [{'id': 'SYNTHETIC-1'}], 'next_page_token': 'next'}
        return {'vulns': [{'id': 'SYNTHETIC-2'}]}
    report = audit(bom(), query=query)
    assert report['status'] == 'OFFEN'
    assert report['finding_ids'] == ['SYNTHETIC-1', 'SYNTHETIC-2']
    assert calls[1]['page_token'] == 'next'


@pytest.mark.parametrize('response', [None, [], {'error': 'unavailable'}, {'vulns': None},
                                     {'vulns': [{}]}, {'next_page_token': 42}])
def test_malformed_response_never_counts_as_verified(response):
    report = audit(bom(), query=lambda _: response)
    assert report['status'] == 'OFFEN'
    assert not report['queries']
    assert report['unverified']


def test_repeat_page_token_is_failure():
    with pytest.raises(ValueError, match='pagination'):
        query_all({}, lambda _: {'next_page_token': 'same'})


def test_unmapped_native_files_remain_unverified():
    inventory = bom()
    inventory['components'].append({'bom-ref': 'native:unknown.dll'})
    report = audit(inventory, query=lambda _: {})
    assert {'component': 'native:unknown.dll', 'reason': 'no_verified_source_package'} in report['unverified']


def test_source_identity_is_required_without_guessing():
    component = bom()['components'][0]
    component['properties'] = []
    with pytest.raises(ValueError, match='missing_source'):
        package_query(component)


def test_empty_inventory_cannot_pass_without_queries():
    report = audit({'components': []}, query=lambda _: pytest.fail('query'))
    assert report['status'] == 'OFFEN'
    assert len(report['unverified']) == 2
