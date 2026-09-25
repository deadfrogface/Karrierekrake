"""Jobs eligible for an application run.

Rows with ``source == demo`` are visual-QA fixtures. They must not enter the
application queue and must not be auto-applied, even if a caller inserted
them into a user database.
"""

from __future__ import annotations

from typing import Iterable

from core.models import Job

DEMO_SOURCE = "demo"


def is_demo_job(job: Job) -> bool:
    return str(getattr(job, "source", "") or "").strip().casefold() == DEMO_SOURCE


def filter_application_queue(jobs: Iterable[Job]) -> list[Job]:
    """Drop demo fixtures. Order of the remaining jobs is preserved."""
    return [job for job in jobs if not is_demo_job(job)]
