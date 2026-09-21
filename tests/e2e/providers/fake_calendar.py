"""Fake calendar + job-source providers for product E2E."""

from __future__ import annotations

from typing import Any

from core.models import Job
from integrations.calendar_freebusy import MockFreeBusyProvider
from integrations.calendar_write import InMemoryCalendarTransport
from search.base import JobSource, SearchQuery


class FakeJobSource(JobSource):
    """Deterministic job source — never hits the network."""

    source_id = "fake_e2e"

    def __init__(
        self,
        jobs: list[Job] | None = None,
        *,
        fail: bool = False,
        hang_after: int | None = None,
        malformed_once: bool = False,
    ):
        self._jobs = list(jobs or [])
        self.fail = fail
        self.hang_after = hang_after
        self.malformed_once = malformed_once
        self.calls = 0

    def search(self, queries: list[SearchQuery]) -> list[Job]:
        self.calls += 1
        if self.fail:
            raise ConnectionError("fake offline job source")
        out: list[Job] = []
        if self.malformed_once and self.calls == 1:
            out.append(
                Job(
                    id="malformed-1",
                    source=self.source_id,
                    source_job_id="malformed-1",
                    title="",
                    company="",
                    city="",
                    url="https://jobs.example/malformed",
                )
            )
        for i, job in enumerate(self._jobs):
            if self.hang_after is not None and i >= self.hang_after:
                raise TimeoutError("fake hung source")
            out.append(job)
        _ = queries  # query shapes used by real adapters; fake returns full corpus
        return out


def make_calendar_stack() -> tuple[MockFreeBusyProvider, InMemoryCalendarTransport]:
    return MockFreeBusyProvider(), InMemoryCalendarTransport()
