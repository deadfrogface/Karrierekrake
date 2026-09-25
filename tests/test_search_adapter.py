"""SearchAdapter interface and health_check smoke tests."""

from search.base import JobSource, SearchAdapter
from search.bundesagentur import BundesagenturSource
from search.company_sites import CompanySitesSource
from search.indeed import IndeedSource
from search.linkedin import LinkedInSearchSource
from search.stepstone import StepstoneSource
from search.xing import XingSource


def test_search_adapter_alias():
    assert SearchAdapter is JobSource


def test_default_health_check_ok():
    from search.base import JobSource, SearchQuery
    from core.models import Job

    class _Dummy(JobSource):
        source_id = "dummy"

        def search(self, queries: list[SearchQuery]) -> list[Job]:
            return []

    ok, msg = _Dummy().health_check()
    assert ok is True
    assert msg == "ok"


def test_company_sites_health_check_curated():
    ok, msg = CompanySitesSource().health_check()
    assert ok is True
    assert "placeholder" not in msg.lower()
    assert "greenhouse" in msg.lower() or "lever" in msg.lower() or "kuratierte" in msg.lower()


def test_indeed_normalize_maps_row():
    src = IndeedSource()
    job = src.normalize(
        {
            "title": "Sachbearbeiter",
            "company": "Beispiel GmbH",
            "location": "Berlin, Deutschland",
            "job_url": "https://example.com/job/1",
            "description": "Büro",
            "id": "abc",
        }
    )
    assert job is not None
    assert job.title == "Sachbearbeiter"
    assert job.city == "Berlin"
    assert job.source == "indeed"


def test_linkedin_inherits_indeed_normalize_and_health():
    src = LinkedInSearchSource()
    assert src.source_id == "linkedin"
    ok, msg = src.health_check()
    assert isinstance(ok, bool)
    assert isinstance(msg, str)
    job = src.normalize(
        {
            "title": "Office Manager",
            "company": "Acme",
            "location": "Hamburg",
            "job_url": "https://example.com/li/1",
            "description": "Team",
            "id": "li1",
        }
    )
    assert job is not None
    assert job.source == "linkedin"


def test_stepstone_normalize_job_posting():
    src = StepstoneSource()
    ok, msg = src.health_check()
    assert isinstance(ok, bool) and isinstance(msg, str)
    job = src.normalize(
        {
            "@type": "JobPosting",
            "title": "Kaufmännische Assistenz",
            "url": "https://www.stepstone.de/job/1",
            "hiringOrganization": {"name": "Beispiel AG"},
            "jobLocation": {"address": {"addressLocality": "Köln"}},
            "description": "<p>Vollzeit</p>",
        }
    )
    assert job is not None
    assert job.source == "stepstone"
    assert job.company == "Beispiel AG"
    assert job.city == "Köln"


def test_xing_normalize_job_posting():
    src = XingSource()
    ok, msg = src.health_check()
    assert isinstance(ok, bool) and isinstance(msg, str)
    job = src.normalize(
        {
            "@type": "JobPosting",
            "title": "Office Support",
            "url": "https://www.xing.com/jobs/1",
            "hiringOrganization": {"name": "Xing Firma"},
            "jobLocation": {"address": {"addressLocality": "München"}},
            "description": "Homeoffice möglich",
        }
    )
    assert job is not None
    assert job.source == "xing"
    assert "Office" in job.title


def test_bundesagentur_health_check_returns_tuple():
    ok, msg = BundesagenturSource().health_check()
    assert isinstance(ok, bool)
    assert isinstance(msg, str)
