"""Windows EXE human E2E — skipped unless black-box env is ready."""

from __future__ import annotations

import pytest

from tests.blackbox.chaos import (
    double_click_search,
    kill_and_note,
    resize_window,
    spam_refresh,
    start_cancel_search_loop,
    switch_pages_during_work,
)
from tests.blackbox.flows.human_journey import run_human_journey
from tests.blackbox.harness import assess_environment, launch_exe


def _ready() -> bool:
    return assess_environment().can_run


@pytest.mark.blackbox_windows
@pytest.mark.skipif(not _ready(), reason="Windows EXE black-box env not configured")
def test_human_journey_against_packaged_exe():
    result = run_human_journey()
    assert result["status"] == "PASS", result
    assert "profile" in result["steps_completed"]
    assert "google_road_distance_job_search" in result["steps_completed"]
    assert "delete_reset" in result["steps_completed"]


@pytest.mark.blackbox_windows
@pytest.mark.skipif(not _ready(), reason="Windows EXE black-box env not configured")
def test_chaos_user_against_packaged_exe():
    session = launch_exe(fresh_profile=True)
    assert session.app is not None
    try:
        double_click_search(session)
        start_cancel_search_loop(session, rounds=2)
        switch_pages_during_work(session)
        spam_refresh(session, times=3)
        resize_window(session)
        kill_and_note(session)
    finally:
        session.close(kill=True)
