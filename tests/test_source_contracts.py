"""Offline source contracts: placeholders and garbage HTTP must not crash."""

from __future__ import annotations

from core.source_health import SourceHealthStatus
from search.base import SearchQuery
from search.company_sites import CompanySitesSource
from search.stepstone import StepstoneSource
from search.xing import XingSource


def test_company_sites_empty_query_is_ok_empty_not_placeholder():
    src = CompanySitesSource()
    assert src.search([]) == []
    status = SourceHealthStatus.from_outcome(jobs_found=0, source_id="company_sites")
    assert status == SourceHealthStatus.OK_EMPTY
    assert status != SourceHealthStatus.PLACEHOLDER
    # Explicit placeholder flag still works for legacy callers.
    assert (
        SourceHealthStatus.from_outcome(
            jobs_found=0, source_id="company_sites", placeholder=True
        )
        == SourceHealthStatus.PLACEHOLDER
    )


def test_company_sites_health_is_curated_not_placeholder():
    ok, msg = CompanySitesSource().health_check()
    assert ok is True
    assert "placeholder" not in msg.lower()
    assert "greenhouse" in msg.lower() or "kuratierte" in msg.lower() or "boards" in msg.lower()


def test_stepstone_garbage_http_does_not_crash(monkeypatch):
    class _Resp:
        text = "<<<not-html-or-json>>>"
        status_code = 200

        def raise_for_status(self):
            return None

    class _Client:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, *a, **k):
            return _Resp()

    monkeypatch.setattr("search.stepstone.httpx.Client", _Client)
    src = StepstoneSource()
    jobs = src.search([SearchQuery(keyword="Sachbearbeiter", location="Berlin")])
    assert isinstance(jobs, list)


def test_xing_garbage_http_does_not_crash(monkeypatch):
    class _Resp:
        text = "{not valid json{{{{"
        status_code = 200

        def raise_for_status(self):
            return None

    class _Client:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, *a, **k):
            return _Resp()

    monkeypatch.setattr("search.xing.httpx.Client", _Client)
    src = XingSource()
    jobs = src.search([SearchQuery(keyword="Sachbearbeiter", location="Berlin")])
    assert isinstance(jobs, list)


def test_source_health_status_distinctions():
    assert SourceHealthStatus.from_outcome(jobs_found=3) == SourceHealthStatus.OK_WITH_RESULTS
    assert SourceHealthStatus.from_outcome(jobs_found=0, source_id="indeed") == SourceHealthStatus.OK_EMPTY
    assert (
        SourceHealthStatus.from_outcome(jobs_found=0, source_id="company_sites")
        == SourceHealthStatus.OK_EMPTY
    )
    assert (
        SourceHealthStatus.from_outcome(jobs_found=0, error="Timeout after 120s")
        == SourceHealthStatus.TIMEOUT
    )
    assert (
        SourceHealthStatus.from_outcome(jobs_found=0, error="HTTP 403 blocked")
        == SourceHealthStatus.BLOCKED
        or SourceHealthStatus.from_outcome(jobs_found=0, error="HTTP 403 blocked")
        == SourceHealthStatus.AUTH_REQUIRED
    )
    assert SourceHealthStatus.OK_EMPTY != SourceHealthStatus.PLACEHOLDER
    assert SourceHealthStatus.TIMEOUT != SourceHealthStatus.ERROR


def test_stepstone_html_card_fallback(monkeypatch):
    html = """
    <html><body>
      <article data-testid="job-item">
        <h2><a href="/stellenangebote--Assistenz-123.html">Kaufmännische Assistenz</a></h2>
        <span data-at="job-item-company-name">Beispiel AG</span>
        <span data-at="job-item-location">Köln</span>
      </article>
    </body></html>
    """

    class _Resp:
        text = html
        status_code = 200

        def raise_for_status(self):
            return None

    class _Client:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, *a, **k):
            return _Resp()

    monkeypatch.setattr("search.stepstone.httpx.Client", _Client)
    jobs = StepstoneSource().search([SearchQuery(keyword="Assistenz", location="Köln")])
    assert len(jobs) >= 1
    assert "Assistenz" in jobs[0].title
    assert jobs[0].company == "Beispiel AG"


def test_xing_itemlist_jsonld(monkeypatch):
    html = """
    <html><body>
      <script type="application/ld+json">
      {"@type":"ItemList","itemListElement":[
        {"item":{"@type":"JobPosting","title":"Office Support Spezialist",
         "url":"https://www.xing.com/jobs/berlin-office-1",
         "hiringOrganization":{"name":"Xing Firma"},
         "jobLocation":{"address":{"addressLocality":"Berlin"}}}}
      ]}
      </script>
    </body></html>
    """

    class _Resp:
        text = html
        status_code = 200

        def raise_for_status(self):
            return None

    class _Client:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, *a, **k):
            return _Resp()

    monkeypatch.setattr("search.xing.httpx.Client", _Client)
    jobs = XingSource().search([SearchQuery(keyword="Office", location="Berlin")])
    assert len(jobs) == 1
    assert jobs[0].title.startswith("Office Support")
    assert jobs[0].company == "Xing Firma"
    assert jobs[0].city == "Berlin"
