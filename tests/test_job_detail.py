"""Full ad text for XING/StepStone results (the list pages only carry a teaser)."""
import json

from core.models import Job
from search import job_detail


class _Response:
    def __init__(self, body: bytes, url: str):
        self.content, self.url = body, url

    def raise_for_status(self):
        pass


def _page(description: str) -> bytes:
    data = {"@context": "https://schema.org", "@type": "JobPosting", "title": "Sachbearbeiter", "description": description}
    return f'<html><script type="application/ld+json">{json.dumps(data)}</script></html>'.encode("utf-8")


def _job(source="xing", url="https://www.xing.com/jobs/x-1", description=""):
    return Job(id="1", title="Sachbearbeiter", source=source, url=url, description=description)


def test_full_text_is_read_from_the_job_posting_data(monkeypatch):
    text = "Ihre Aufgaben: Rechnungen prüfen und buchen. " * 4
    monkeypatch.setattr(job_detail.requests, "get", lambda url, **kw: _Response(_page("<p>" + text + "</p>"), url))
    assert job_detail.fetch_full_description(_job()).startswith("Ihre Aufgaben")


def test_only_the_two_portals_and_only_over_https_are_fetched(monkeypatch):
    calls = []
    monkeypatch.setattr(job_detail.requests, "get", lambda url, **kw: calls.append(url))
    assert job_detail.fetch_full_description(_job("linkedin", "https://www.linkedin.com/jobs/view/1")) == ""
    assert job_detail.fetch_full_description(_job(url="http://www.xing.com/jobs/x-1")) == ""
    assert job_detail.fetch_full_description(_job(url="https://evil.example.org/jobs/x-1")) == ""
    assert calls == []


def test_redirect_to_another_host_is_ignored(monkeypatch):
    monkeypatch.setattr(job_detail.requests, "get",
                        lambda url, **kw: _Response(_page("x" * 200), "https://evil.example.org/"))
    assert job_detail.fetch_full_description(_job()) == ""


def test_failed_fetch_returns_nothing_and_short_ads_need_text():
    assert job_detail.needs_full_text(_job()) and not job_detail.needs_full_text(_job(description="x" * 600))
    assert not job_detail.needs_full_text(_job("indeed", "https://de.indeed.com/viewjob?jk=1"))


def test_calendar_link_errors_are_written_for_the_person():
    import os, tempfile
    from pathlib import Path
    from integrations.calendar import local_ics

    target = Path(tempfile.gettempdir()) / "kk-cal-test.ics"
    for url, fragment in (("http://example.org/a.ics", "https://"), ("https://127.0.0.1/a.ics", "Netzwerk")):
        try:
            local_ics.refresh_private_ics(url, target)
        except local_ics.CalendarLinkError as exc:
            assert fragment in str(exc) and "http" not in str(exc).replace("https://", "")
        else:
            raise AssertionError(url)
    from desktop.oauth_messages import message_for_account_error
    assert message_for_account_error(local_ics.CalendarLinkError("Der Link ist ungültig.")) == "Der Link ist ungültig."
