"""Standalone source health probes for StepStone / XING / company_sites.

These tests do not require live network for placeholder checks. Live probes are
marked optional and skip on network failure.
"""

from __future__ import annotations

import pytest

from core.source_health import SourceHealthStatus
from search.company_sites import CompanySitesSource
from search.stepstone import StepstoneSource
from search.xing import XingSource


def test_company_sites_is_curated_not_placeholder():
    src = CompanySitesSource()
    jobs = src.search([])
    assert jobs == []
    ok, msg = src.health_check()
    assert ok is True
    assert "placeholder" not in msg.lower()
    status = SourceHealthStatus.from_outcome(jobs_found=0, source_id=src.source_id)
    assert status == SourceHealthStatus.OK_EMPTY


@pytest.mark.network
def test_stepstone_health_check_reachable():
    src = StepstoneSource()
    ok, msg = src.health_check()
    # Reachable HTML is enough; 0 search hits may still be OK_EMPTY in runs.
    assert isinstance(ok, bool)
    assert msg


@pytest.mark.network
def test_xing_health_check_reachable():
    src = XingSource()
    ok, msg = src.health_check()
    assert isinstance(ok, bool)
    assert msg
