"""Bounded public-web discovery; only verified JobPosting pages become jobs."""
from __future__ import annotations

import ipaddress
import json
import re
import socket
import time
import urllib.parse
import urllib.robotparser
from collections import deque
from datetime import datetime, timezone

import httpx
from bs4 import BeautifulSoup

from search.base import SearchQuery
from search.jsonld import iter_job_postings, job_from_job_posting

AGENT = 'Karrierekrake'
MAX_BYTES = 2_000_000
MAX_PAGES = 20
SEARCH_URL = 'https://html.duckduckgo.com/html/'
CAREER = re.compile(r'karriere|career|stellen|jobs?|vacanc|bewerb|position|opening', re.I)


def public_url(url: str) -> str:
    parts = urllib.parse.urlsplit(url)
    if (parts.scheme not in {'http', 'https'} or not parts.hostname
            or parts.username or parts.password or parts.port not in {None, 80, 443}):
        raise ValueError('invalid_public_url')
    addresses = socket.getaddrinfo(parts.hostname, parts.port or (443 if parts.scheme == 'https' else 80),
                                   type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise ValueError('non_public_url')
    return urllib.parse.urlunsplit(parts._replace(fragment=''))


class PublicPages:
    def __init__(self):
        self.client = httpx.Client(timeout=8, headers={'User-Agent': 'Karrierekrake/1.0 (public job search)'})
        self.robots = {}
        self.cache = {}
        self.deadline = time.monotonic() + 75
        from search.web_search_guard import WebSearchGuard
        self.search_guard = WebSearchGuard()

    def close(self):
        self.client.close()

    def _read(self, url, *, check_robots=True):
        for _ in range(6):
            remaining = self.deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('web_search_budget_exhausted')
            url = public_url(url)
            if check_robots and not self.allowed(url):
                raise RuntimeError('robots_disallowed')
            with self.client.stream('GET', url, timeout=min(6, remaining)) as response:
                if response.is_redirect:
                    url = urllib.parse.urljoin(url, response.headers['location'])
                    continue
                response.raise_for_status()
                data = bytearray()
                for block in response.iter_bytes():
                    if time.monotonic() >= self.deadline:
                        raise TimeoutError('web_search_budget_exhausted')
                    data.extend(block)
                    if len(data) > MAX_BYTES:
                        raise ValueError('page_too_large')
                return bytes(data).decode('utf-8', errors='replace'), url
        raise RuntimeError('too_many_redirects')

    def allowed(self, url):
        parts = urllib.parse.urlsplit(url)
        origin = f'{parts.scheme}://{parts.netloc}'
        if origin not in self.robots:
            parser = urllib.robotparser.RobotFileParser()
            try:
                text, _ = self._read(origin + '/robots.txt', check_robots=False)
                parser.parse(text.splitlines())
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code not in {404, 410}:
                    raise
                parser.parse([])
            self.robots[origin] = parser
        return self.robots[origin].can_fetch(AGENT, url)

    def get(self, url):
        if url not in self.cache:
            self.cache[url] = self._read(url)
        return self.cache[url]


def _discover_html(query: SearchQuery, pages: PublicPages) -> list[str]:
    terms = ' '.join(x for x in (query.keyword, query.location, '(Karriere OR Stellenangebote OR Jobs)') if x)
    url = SEARCH_URL + '?' + urllib.parse.urlencode({'q': terms, 'kl': 'de-de'})
    html, _ = pages.get(url)
    soup = BeautifulSoup(html, 'html.parser')
    if soup.select_one('#challenge-form, #anomaly-modal, .anomaly-modal'):
        raise RuntimeError('web_search_captcha')
    urls = []
    for link in soup.select('a.result__a'):
        target = urllib.parse.urljoin(SEARCH_URL, link.get('href', ''))
        wrapped = urllib.parse.parse_qs(urllib.parse.urlsplit(target).query).get('uddg')
        if wrapped:
            target = wrapped[0]
        if target.startswith(('https://', 'http://')) and target not in urls:
            urls.append(target)
    if not urls and not soup.select_one('.no-results'):
        raise RuntimeError('web_search_unrecognized_response')
    return urls[:10]


def discover(query: SearchQuery, pages: PublicPages) -> list[str]:
    try:
        key = json.dumps([query.keyword, query.location, "de-de"], ensure_ascii=False)
        return pages.search_guard.run("duckduckgo", key, lambda: _discover_html(query, pages))
    except Exception:
        # A separate public search provider; never solve/bypass a CAPTCHA.
        from ddgs import DDGS

        remaining = pages.deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("web_search_budget_exhausted")
        terms = " ".join(x for x in (query.keyword, query.location, "Karriere Stellenangebote") if x)
        def fetch_brave():
            rows = DDGS(timeout=max(1, min(6, int(remaining)))).text(
                terms, region="de-de", max_results=10, backend="brave")
            urls = list(dict.fromkeys(str(row.get("href") or "") for row in rows
                                     if str(row.get("href") or "").startswith(("https://", "http://"))))
            if not urls:
                raise RuntimeError("web_search_no_verified_response")
            return urls
        return pages.search_guard.run("brave", key, fetch_brave)


def expired(item):
    value = str(item.get('validThrough') or '').strip()
    if not value:
        return False
    try:
        date = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if len(value) == 10:
            return date.date() < datetime.now(timezone.utc).date()
        return date.replace(tzinfo=date.tzinfo or timezone.utc) < datetime.now(timezone.utc)
    except ValueError:
        return False


def parse_jobs(html, url):
    soup = BeautifulSoup(html, 'html.parser')
    jobs = []
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            payload = json.loads(script.string or script.get_text())
        except (ValueError, TypeError):
            continue
        for item in iter_job_postings(payload):
            if expired(item):
                continue
            item = dict(item)
            target = item.get('url') or item.get('mainEntityOfPage') or url
            if isinstance(target, dict):
                target = target.get('@id') or url
            item['url'] = urllib.parse.urljoin(url, str(target))
            if urllib.parse.urlsplit(item['url']).scheme not in {'http', 'https'}:
                continue
            job = job_from_job_posting(item, source='company_sites')
            if job and job.company and job.description:
                jobs.append(job)
    # Some employers publish schema.org microdata instead of JSON-LD.
    for node in soup.select('[itemscope][itemtype*="JobPosting"]'):
        def prop(name):
            child = node.select_one(f'[itemprop="{name}"]')
            return ((child.get('content') or child.get('href') or child.get_text(' ', strip=True))
                    if child else '')

        item = {'title': prop('title'), 'description': prop('description'),
                'url': urllib.parse.urljoin(url, prop('url') or url),
                'validThrough': prop('validThrough'),
                'hiringOrganization': {'name': prop('name')},
                'jobLocation': {'address': {'addressLocality': prop('addressLocality'),
                                            'addressCountry': prop('addressCountry')}}}
        if item['title'] and item['hiringOrganization']['name'] and not expired(item):
            job = job_from_job_posting(item, source='company_sites')
            if job and job.description:
                jobs.append(job)
    return jobs, soup


def search_web(query: SearchQuery, pages: PublicPages):
    from search.company_sites import _keyword_match
    from search.public_ats import read_board

    # Explicit URLs support bookmarked employer career pages through the adapter.
    seeds = query.extra.get('career_urls') or []
    if isinstance(seeds, str):
        seeds = [seeds]
    errors = []
    try:
        seeds = list(seeds) + discover(query, pages)
    except Exception as exc:
        code = str(exc) if str(exc).startswith('web_search_provider_') else type(exc).__name__
        errors.append('web_discovery:' + code)
    pending = deque((url, 0) for url in dict.fromkeys(seeds))
    visited = set()
    jobs = {}
    deadline = min(pages.deadline, time.monotonic() + 20)
    while pending and len(visited) < MAX_PAGES and time.monotonic() < deadline:
        url, depth = pending.popleft()
        if url in visited:
            continue
        visited.add(url)
        try:
            batch = read_board(url, pages)
            soup = None
            if batch is None:
                html, final = pages.get(url)
                batch, soup = parse_jobs(html, final)
            for job in batch:
                if any(_keyword_match(job.title, keyword)
                       for keyword in query.extra.get("match_keywords", [query.keyword])):
                    jobs.setdefault(job.url, job)
            if len(jobs) >= query.max_results:
                break
            if soup is not None and depth < 2:
                for anchor in soup.select('a[href]'):
                    href = urllib.parse.urljoin(final, anchor['href']).split('#')[0]
                    label = anchor.get_text(' ', strip=True)
                    if (href.startswith(('https://', 'http://')) and href not in visited
                            and (CAREER.search(href + ' ' + label)
                                 or (query.keyword and _keyword_match(label, query.keyword)))):
                        if len(pending) < MAX_PAGES * 2:
                            pending.appendleft((href, depth + 1))
        except Exception as exc:
            errors.append('career_page:' + type(exc).__name__)
    if pending and (time.monotonic() >= deadline or len(visited) >= MAX_PAGES):
        errors.append('web_search_budget_exhausted')
    return list(jobs.values())[:max(1, query.max_results)], errors
