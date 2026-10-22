"""Own Indeed / LinkedIn clients through the search adapter, with offline HTTP (no JobSpy, no curl_cffi)."""
import json
import sys
from types import SimpleNamespace

import pytest

from search.base import SearchQuery
from search.indeed import IndeedSource
from search.indeed_api import REMOTE_KEY


@pytest.mark.parametrize('location', ['Berlin', 'remote'])
def test_indeed_search_and_health_work_without_jobspy_or_go_transport(monkeypatch, location):
    import requests
    monkeypatch.setitem(sys.modules, 'tls_client', None)
    calls = []
    fixture = {'data': {'jobSearch': {'results': [{'job': {
        'key': 'synthetic123', 'title': 'Softwareentwickler',
        'description': {'html': '<p>Python und SQL</p>'},
        'employer': {'name': 'Synthetischer Testbetrieb'}, 'sourceEmployerName': '',
        'location': {'city': 'Berlin', 'admin1Code': 'BE', 'countryCode': 'DE'},
        'recruit': {'viewJobUrl': 'https://example.invalid/synthetic-job'},
        'attributes': [{'key': REMOTE_KEY}] if location == 'remote' else [],
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
    assert (jobs[0].remote_type == 'remote') is (location == 'remote')
    assert 'tls_client' not in sys.modules or sys.modules['tls_client'] is None


def test_blocked_indeed_response_becomes_a_guarded_error(monkeypatch):
    import requests
    monkeypatch.setattr(requests.Session, 'post', lambda session, url, **kw: SimpleNamespace(status_code=429))
    with pytest.raises(RuntimeError, match='indeed blocked'):
        IndeedSource().search([SearchQuery('x', 'Berlin')])


def test_search_modules_do_not_depend_on_jobspy_or_curl_cffi():
    import importlib
    for name in ('search.indeed', 'search.indeed_api', 'search.linkedin', 'search.linkedin_api'):
        importlib.import_module(name)
    # They must run without those packages: nothing of ours imports them.
    for n in ('indeed', 'indeed_api', 'linkedin', 'linkedin_api'):
        text = open(f'search/{n}.py', encoding='utf-8').read()
        assert 'import jobspy' not in text and 'from jobspy' not in text and 'curl_cffi' not in text


@pytest.mark.parametrize('relative', ['tls_client', 'tls_client/__init__.py', 'tls-client-64.dll'])
def test_legacy_transport_root_and_flat_library_paths_are_forbidden(relative):
    from scripts.generate_content_manifest import _load_policy
    policy = _load_policy()
    assert policy.path_has_forbidden_marker(relative)
    assert not policy.filter_collect_all_datas([('/site-packages/'+relative, relative)])


def test_xing_place_with_more_work_places_keeps_only_the_first():
    from search.job_schema import normalize_portal_job
    from core.models import Job

    job = normalize_portal_job(Job(id="1", title="Sachbearbeiter", source="xing", city="Düsseldorf + 2 weitere"))
    assert job.city == "Düsseldorf"
