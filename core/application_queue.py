"""Jobs eligible for an application run.

Only portal scrapers whose listing fetch is covered by a test may enter the
queue or auto-apply: ``search/indeed.py``, ``search/stepstone.py``,
``search/xing.py``, ``search/bundesagentur.py``. LinkedIn
(``search/linkedin.py``): Abruf über JobSpy, ungetestet. ``company_sites``
is a v1 placeholder. ``demo``, ``fixture``, empty, and any other source stay
out.
"""

from __future__ import annotations

from typing import Iterable

from core.models import Job

# Keep in sync with the portal JobSource.source_id attributes. A test pins this
# set to those class attributes so a rename cannot drift silently.
APPLICATION_SOURCE_ALLOWLIST = frozenset(
    {
        "bundesagentur",
        "indeed",
        "stepstone",
        "xing",
    }
)

DEMO_SOURCE = "demo"


def job_source_key(job: Job) -> str:
    return str(getattr(job, "source", "") or "").strip().casefold()


def is_application_source(job: Job) -> bool:
    """True when this row may enter the application queue or auto-apply."""
    return job_source_key(job) in APPLICATION_SOURCE_ALLOWLIST


def is_demo_job(job: Job) -> bool:
    """Visual-QA rows. Cover letters stay blocked; the queue blocks them too."""
    return job_source_key(job) == DEMO_SOURCE


def filter_application_queue(jobs: Iterable[Job]) -> list[Job]:
    """Keep allowlisted portal jobs. Order of the remaining jobs is preserved."""
    return [job for job in jobs if is_application_source(job)]
