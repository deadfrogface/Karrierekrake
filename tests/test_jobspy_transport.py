"""Exercise the real pinned JobSpy parser through our adapter, with offline HTTP."""
from contextlib import closing
import json
import sys
from types import SimpleNamespace

import pytest
from search.base import SearchQuery
from search.indeed import IndeedSource


@pytest.mark.parametrize('location', ['Berlin', 'remote'])
def test_real_jobspy_search_and_health_work_without_retired_go_transport(monkeypatch, location):
    import requests
    from jobspy.indeed.constant import remote_key
    monkeypatch.setitem(sys.modules, 'tls_client', None)
    calls = []
    fixture = {'data': {'jobSearch': {'results': [{'job': {
        'key': 'synthetic123', 'title': 'Softwareentwickler',
        'description': {'html': '<p>Python und SQL</p>'},
        'employer': {'name': 'Synthetischer Testbetrieb'}, 'sourceEmployerName': '',
        'location': {'city': 'Berlin', 'admin1Code': 'BE', 'countryCode': 'DE'},
        'recruit': {'viewJobUrl': 'https://example.invalid/synthetic-job'},
        'attributes': [{'key': remote_key}] if location == 'remote' else [],
        'compensation': {'baseSalary': None, 'estimated': None, 'currencyCode': 'EUR'},
        'dateOnIndeed': 1792195200000,
    }}], 'pageInfo': {'nextCursor': None}}}}

    def post(session, url, **kwargs):
        assert url == 'https://apis.indeed.com/graphql'
        assert kwargs['headers']['indeed-co'] == 'DE'
        assert kwargs['headers']['indeed-locale'] == 'de-DE'
        query = kwargs['json']['query']
        assert 'Softwareentwickler' in query
        assert '72h' in query
        assert ('Germany' if location == 'remote' else 'Berlin') in query
        calls.append(query)
        return SimpleNamespace(status_code=200, json=lambda: json.loads(json.dumps(fixture)))

    monkeypatch.setattr(requests.Session, 'post', post)
    source = IndeedSource()
    assert source.health_check() == (True, 'ok')
    jobs = source.search([SearchQuery('Softwareentwickler', location, max_results=1,
                                       published_within_days=3)])
    assert len(calls) == len(jobs) == 1
    assert jobs[0].title == 'Softwareentwickler'
    assert jobs[0].company == 'Synthetischer Testbetrieb'
    assert jobs[0].country_code == 'DE'
    assert 'Python und SQL' in jobs[0].description
    assert 'tls_client' not in sys.modules or sys.modules['tls_client'] is None


def test_current_curl_transport_can_load_and_close_without_external_network():
    from curl_cffi import Curl
    with closing(Curl()) as handle:
        version = handle.version().decode()
        assert version.startswith('libcurl/')
        assert 'BoringSSL' in version


def test_search_runtime_attests_actual_native_transport():
    from core.security.jobspy_runtime import verify_jobspy_runtime
    result = verify_jobspy_runtime()
    assert result['jobspy'] == '1.3.0'
    assert result['native'].startswith('libcurl/8.21.0-IMPERSONATE ')


def test_frozen_search_runtime_rejects_legacy_module(monkeypatch):
    from importlib import util
    from core.security.jobspy_runtime import verify_jobspy_runtime
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    original = util.find_spec
    monkeypatch.setattr(util, 'find_spec', lambda name: object() if name == 'tls_client' else original(name))
    with pytest.raises(RuntimeError, match='legacy_go_transport_present'):
        verify_jobspy_runtime()
