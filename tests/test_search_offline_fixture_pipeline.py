"""Offline fixture pipeline: JobSpy 1.3.0 parser -> search adapter -> job_schema -> dedupe.

PR144 Data Engine (T06.05.07.05.04.02/.03, T07.06). Network is blocked at the
socket, DNS and libcurl level; only the HTTP layer of ``requests.Session`` is
replaced by synthetic fixtures. No real job search, no request to any portal.
"""
from __future__ import annotations

import json
import socket
import sys
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlparse

import pytest

FIXTURES = Path(__file__).parent / "fixtures" / "search_offline"


class NetworkAttempt(AssertionError):
    pass


def _install_network_guard(monkeypatch) -> list[str]:
    """Fail on any socket connect, DNS lookup or libcurl transfer; record attempts."""
    attempts: list[str] = []

    def deny(kind):
        def _deny(*args, **kwargs):
            attempts.append(f"{kind}:{args[1:2] or args[:1]}")
            raise NetworkAttempt(f"network blocked in offline test: {kind}")
        return _deny

    monkeypatch.setattr(socket.socket, "connect", deny("socket.connect"))
    monkeypatch.setattr(socket.socket, "connect_ex", deny("socket.connect_ex"))
    monkeypatch.setattr(socket, "create_connection", deny("socket.create_connection"))
    monkeypatch.setattr(socket, "getaddrinfo", deny("socket.getaddrinfo"))
    from curl_cffi import Curl
    monkeypatch.setattr(Curl, "perform", deny("curl_cffi.Curl.perform"))
    return attempts


@pytest.fixture
def no_network(monkeypatch):
    attempts = _install_network_guard(monkeypatch)
    yield attempts
    assert attempts == [], f"unexpected network attempts: {attempts}"


@pytest.fixture
def portal_fixtures(monkeypatch):
    """Serve synthetic Indeed GraphQL / LinkedIn guest HTML at the requests layer."""
    import requests

    indeed = json.loads((FIXTURES / "indeed_graphql_synthetic.json").read_text("utf-8"))
    linkedin = (FIXTURES / "linkedin_guest_search_synthetic.html").read_text("utf-8")
    served: list[tuple[str, str]] = []

    def fake_request(self, method, url, **kwargs):
        served.append((method.upper(), url))
        parsed = urlparse(url)
        if (method.upper(), parsed.netloc, parsed.path) == ("POST", "apis.indeed.com", "/graphql"):
            payload = json.loads(json.dumps(indeed))
            return SimpleNamespace(status_code=200, json=lambda: payload, text=json.dumps(payload))
        if parsed.netloc.endswith("linkedin.com") and parsed.path.endswith(
            "/jobs-guest/jobs/api/seeMoreJobPostings/search"
        ):
            start = int((kwargs.get("params") or {}).get("start") or 0)
            body = linkedin if start == 0 else "<!DOCTYPE html>\n\n<!---->"
            return SimpleNamespace(status_code=200, text=body, url=url)
        raise AssertionError(f"unexpected outbound request in offline test: {method} {url}")

    monkeypatch.setattr(requests.Session, "request", fake_request)
    # The retired Go transport must not be needed on any code path.
    monkeypatch.setitem(sys.modules, "tls_client", None)
    return served


def _query(location="Berlin", max_results=5):
    from search.base import SearchQuery
    return SearchQuery("Softwareentwickler", location, max_results=max_results,
                       published_within_days=3)


def test_indeed_fixture_through_adapter_and_job_schema(no_network, portal_fixtures):
    from search.indeed import IndeedSource
    jobs = IndeedSource().search([_query()])
    assert [j.title for j in jobs] == ["Softwareentwickler (m/w/d)", "Data Engineer"]
    first = jobs[0]
    assert first.source == "indeed"
    assert first.company == "Synthetischer Testbetrieb GmbH"
    assert first.country_code == "DE"
    assert first.city == "Berlin"
    assert "Python, SQL" in first.description
    assert "<p>" not in first.description
    assert first.url.startswith("https://de.indeed.com/viewjob?jk=synthkk0001")
    assert len({j.id for j in jobs}) == 2
    assert {urlparse(u).netloc for _, u in portal_fixtures} == {"apis.indeed.com"}
    assert sys.modules.get("tls_client") is None


def test_linkedin_fixture_through_adapter_without_tls_client(no_network, portal_fixtures):
    from search.linkedin import LinkedInSearchSource
    jobs = LinkedInSearchSource().search([_query()])
    assert [j.title for j in jobs] == ["Softwareentwickler", "QA Engineer"]
    assert jobs[0].source == "linkedin"
    assert jobs[0].url.endswith("/jobs/view/900000001")
    assert jobs[0].country_code == "DE"
    # linkedin_fetch_description=False: only the guest search page, no detail pages.
    assert all("/jobs/view/" not in u for _, u in portal_fixtures)
    assert all(urlparse(u).netloc.endswith("linkedin.com") for _, u in portal_fixtures)


def test_cross_source_dedupe_collapses_portal_twins(no_network, portal_fixtures):
    from core.deduplicator import deduplicate
    from search.indeed import IndeedSource
    from search.linkedin import LinkedInSearchSource
    jobs = IndeedSource().search([_query()]) + LinkedInSearchSource().search([_query()])
    assert len(jobs) == 4
    result = deduplicate(jobs)
    primaries = [j for j in result if not j.duplicate_of]
    dups = [j for j in result if j.duplicate_of]
    assert len(result) == 4  # duplicates are retained but marked
    assert len(primaries) == 3
    assert len(dups) == 1
    twin = dups[0]
    winner = next(j for j in primaries if j.id == twin.duplicate_of)
    assert {twin.source, winner.source} == {"indeed", "linkedin"}
    assert twin.source in winner.alt_sources


def test_network_guard_really_blocks():
    """Self-test of the guard so a silently ineffective block cannot pass."""
    mp = pytest.MonkeyPatch()
    try:
        attempts = _install_network_guard(mp)
        with pytest.raises(NetworkAttempt):
            socket.create_connection(("192.0.2.1", 9))
        with pytest.raises(NetworkAttempt):
            socket.getaddrinfo("example.invalid", 443)
        from curl_cffi import Curl
        with pytest.raises(NetworkAttempt):
            Curl().perform()
        assert len(attempts) == 3
    finally:
        mp.undo()
