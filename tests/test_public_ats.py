import json
from search.public_ats import board_endpoint, read_board
from search.company_web import search_web
from search.base import SearchQuery


class Pages:
    deadline = float('inf')
    def __init__(self, payload):
        self.payload = payload
        self.calls = []
    def get(self, url):
        self.calls.append(url)
        return json.dumps(self.payload), url


def test_greenhouse_feed_is_used_without_loading_challenged_html(monkeypatch):
    url = 'https://job-boards.greenhouse.io/acme/jobs/1'
    page = Pages({'jobs': [{'title': 'Verkäufer', 'absolute_url': url,
                           'content': '&lt;p&gt;Kunden beraten&lt;/p&gt;',
                           'location': {'name': 'Berlin'}}]})
    monkeypatch.setattr('search.company_web.discover', lambda *a: [url])
    jobs, errors = search_web(SearchQuery('Verkäufer'), page)
    assert not errors and len(jobs) == 1
    assert len(page.calls) == 1 and page.calls[0].startswith('https://boards-api.greenhouse.io/')
    assert jobs[0].description == 'Kunden beraten'
    assert jobs[0].url == url


def test_lever_eu_endpoint_and_application_link():
    url = 'https://jobs.eu.lever.co/acme/1'
    page = Pages([{'text': 'Buchhalter', 'hostedUrl': url, 'applyUrl': url + '/apply',
                   'description': '<p>Buchhaltung</p>', 'categories': {'location': 'Berlin'}}])
    jobs = read_board(url, page)
    assert page.calls[0] == 'https://api.eu.lever.co/v0/postings/acme?mode=json'
    assert jobs[0].application_url == url + '/apply'
    assert jobs[0].title == 'Buchhalter'


def test_ashby_reads_published_jobs_and_retains_verified_location():
    url = 'https://jobs.ashbyhq.com/acme/job'
    row = {'title': 'Support', 'jobUrl': url, 'descriptionPlain': 'Kundenservice',
           'isRemote': True, 'isListed': True,
           'address': {'postalAddress': {'addressLocality': 'Köln', 'addressCountry': 'DE'}}}
    page = Pages({'jobs': [row, {**row, 'isListed': False}]})
    jobs = read_board(url, page)
    assert len(jobs) == 1 and jobs[0].city == 'Köln'
    assert jobs[0].remote_type == 'remote'
    assert page.calls[0].startswith('https://api.ashbyhq.com/posting-api/job-board/acme')


def test_spoofed_host_does_not_get_a_trusted_feed_mapping():
    assert board_endpoint('https://jobs.lever.co.attacker.example/acme') is None
    assert board_endpoint('https://jobs.lever.co/acme%2Fbad') is None
    assert board_endpoint('https://boards.greenhouse.io/embed/job_board?for=acme')[1] == 'acme'
