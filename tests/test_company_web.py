import json
import socket
import time
from types import SimpleNamespace

import pytest

from search.base import SearchQuery, PartialResultsError
from search import company_web as web
from search import company_sites as company


def posting(title='Verkäufer', **extra):
    return {'@type': 'JobPosting', 'title': title,
            'description': '<p>Verkauf und Kundenberatung</p>',
            'hiringOrganization': {'name': 'Firma XY'},
            'jobLocation': {'address': {'addressLocality': 'Köln', 'addressCountry': 'DE'}},
            **extra}


def html(item):
    return '<script type="application/ld+json">' + json.dumps(item) + '</script>'


class Pages:
    deadline = float('inf')
    def __init__(self, mapping):
        self.mapping = mapping
        self.calls = []
    def get(self, url):
        self.calls.append(url)
        return self.mapping[url], url
    def close(self):
        pass


def test_discover_career_overview_follow_detail_and_deduplicate(monkeypatch):
    root = 'https://firma.example/karriere'
    detail = 'https://firma.example/jobs/verkauf'
    pages = Pages({root: '<a href="/jobs/verkauf">Verkäufer</a><a href="/jobs/verkauf">Bewerben</a>',
                   detail: html({'@graph': [posting()]})})
    monkeypatch.setattr(web, 'discover', lambda *args: [root])
    jobs, errors = web.search_web(SearchQuery('Verkäufer', 'Köln'), pages)
    assert not errors
    assert len(jobs) == 1
    assert jobs[0].url == detail and jobs[0].company == 'Firma XY'
    assert jobs[0].city == 'Köln' and jobs[0].description
    assert pages.calls.count(detail) == 1


def test_overview_and_expired_jobs_are_not_hits():
    assert web.parse_jobs('<h1>Karriere</h1>', 'https://firma.example')[0] == []
    assert web.parse_jobs(html(posting(validThrough='2000-01-01')), 'https://firma.example')[0] == []


def test_itemlist_relative_url_and_keyword_filter(monkeypatch):
    url = 'https://firma.example/karriere/'
    pages = Pages({url: html({'@type': 'ItemList', 'itemListElement': [
        {'item': posting(url='verkauf')}, {'item': posting('Buchhalter', url='buchhaltung')}]})})
    monkeypatch.setattr(web, 'discover', lambda *args: [url])
    jobs, errors = web.search_web(SearchQuery('Verkäufer'), pages)
    assert not errors and len(jobs) == 1
    assert jobs[0].url == url + 'verkauf'


def test_discovery_unwraps_search_results_without_inventing_jobs():
    class SearchPage:
        def get(self, url):
            assert 'K%C3%B6ln' in url and 'Verk%C3%A4ufer' in url
            return '<a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Ffirma.example%2Fkarriere">XY</a>', url
    assert web._discover_html(SearchQuery('Verkäufer', 'Köln'), SearchPage()) == ['https://firma.example/karriere']


@pytest.mark.parametrize('body', ['<div class="anomaly-modal"></div>', '<html>Blocked</html>'])
def test_search_block_is_an_error_not_no_jobs(body):
    pages = SimpleNamespace(get=lambda url: (body, url))
    with pytest.raises(RuntimeError):
        web._discover_html(SearchQuery('Verkäufer'), pages)


def test_all_queries_used_and_board_fetched_once(monkeypatch):
    monkeypatch.setattr(web, 'PublicPages', lambda: Pages({}))
    seen = []
    monkeypatch.setattr(web, 'search_web', lambda q, p: (seen.append(q.keyword) or [], []))
    monkeypatch.setattr(company, 'CURATED_BOARDS', (('greenhouse', 'xy', 'Firma XY'),))
    calls = []
    jobs = [web.parse_jobs(html(posting(t)), 'https://firma.example/' + str(i))[0][0]
            for i, t in enumerate(['Verkäufer', 'Buchhalter'])]
    monkeypatch.setattr(company, '_fetch_greenhouse', lambda *a: (calls.append(a) or jobs))
    result = company.CompanySitesSource().search([SearchQuery('Verkäufer'), SearchQuery('Buchhalter')])
    assert seen == ['Verkäufer', 'Buchhalter']
    assert len(calls) == 1 and len(result) == 2


def test_web_failure_retains_real_board_results(monkeypatch):
    monkeypatch.setattr(web, 'PublicPages', lambda: Pages({}))
    monkeypatch.setattr(web, 'search_web', lambda q, p: ([], ['web_search_captcha']))
    monkeypatch.setattr(company, 'CURATED_BOARDS', (('greenhouse', 'xy', 'Firma XY'),))
    jobs = web.parse_jobs(html(posting()), 'https://firma.example/job')[0]
    monkeypatch.setattr(company, '_fetch_greenhouse', lambda *a: jobs)
    with pytest.raises(PartialResultsError) as exc:
        company.CompanySitesSource().search([SearchQuery('Verkäufer')])
    assert exc.value.jobs == jobs


@pytest.mark.parametrize('address', ['127.0.0.1', '10.0.0.1', '169.254.169.254', '::1'])
def test_private_addresses_rejected(monkeypatch, address):
    monkeypatch.setattr(socket, 'getaddrinfo', lambda *a, **k: [(0, 0, 0, '', (address, 443))])
    with pytest.raises(ValueError, match='non_public'):
        web.public_url('https://firma.example/job')


def test_deadline_returns_partial_jobs(monkeypatch):
    pages = Pages({})
    pages.deadline = time.monotonic() - 1
    monkeypatch.setattr(web, 'discover', lambda *a: ['https://firma.example/karriere'])
    jobs, errors = web.search_web(SearchQuery('Verkäufer'), pages)
    assert not jobs and errors == ['web_search_budget_exhausted'] and not pages.calls


def test_transport_follows_public_redirect_and_respects_robots(monkeypatch):
    import httpx
    records = []
    def respond(req):
        records.append(str(req.url))
        if req.url.path == '/robots.txt':
            return httpx.Response(200, text='User-agent: *\nDisallow: /private\n')
        if req.url.path == '/career':
            return httpx.Response(302, headers={'location': '/jobs/verkauf'})
        if req.url.path == '/jobs/verkauf':
            return httpx.Response(200, text=html(posting()),
                                  headers={'content-type': 'text/html; charset=utf-8'})
        return httpx.Response(404)
    monkeypatch.setattr(web, 'public_url', lambda url: url)
    pages = web.PublicPages()
    pages.client.close()
    pages.client = httpx.Client(transport=httpx.MockTransport(respond))
    try:
        body, final = pages.get('https://firma.example/career')
        assert final == 'https://firma.example/jobs/verkauf'
        assert web.parse_jobs(body, final)[0][0].title == 'Verkäufer'
        with pytest.raises(RuntimeError, match='robots_disallowed'):
            pages.get('https://firma.example/private')
        assert records.count('https://firma.example/robots.txt') == 1
        assert 'https://firma.example/private' not in records
    finally:
        pages.close()


def test_search_provider_fallback_after_challenge(monkeypatch):
    import sys
    from types import ModuleType
    class Search:
        def __init__(self, **kw):
            assert kw['timeout'] > 0
        def text(self, *args, **kwargs):
            assert kwargs['backend'] == 'brave'
            return [{'href': 'https://firma.example/karriere'}]
    fake = ModuleType('ddgs')
    fake.DDGS = Search
    monkeypatch.setitem(sys.modules, 'ddgs', fake)
    class Challenge:
        deadline = time.monotonic() + 10
        def get(self, url):
            return '<div class="anomaly-modal"></div>', url
    assert web.discover(SearchQuery('Verkäufer', 'Köln'), Challenge()) == [
        'https://firma.example/karriere']


def test_employer_microdata_job_is_extracted():
    markup = ("<article itemscope itemtype='https://schema.org/JobPosting'>"
              "<h1 itemprop='title'>Verkäufer</h1>"
              "<div itemprop='description'>Kunden beraten und Waren verkaufen.</div>"
              "<span itemprop='name'>Firma XY</span>"
              "<span itemprop='addressLocality'>Köln</span>"
              "</article>")
    jobs, _ = web.parse_jobs(markup, 'https://firma.example/karriere/verkauf')
    assert len(jobs) == 1
    assert jobs[0].title == 'Verkäufer' and jobs[0].company == 'Firma XY'
