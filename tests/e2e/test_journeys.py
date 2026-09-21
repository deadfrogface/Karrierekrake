"""Full user journey E2E tests (offline / fake providers)."""

from __future__ import annotations

import pytest

from tests.e2e.scenarios.journeys import (
    journey_ambiguous_mail,
    journey_happy_path,
    journey_interview_reschedule,
    journey_offline,
    journey_rejection_path,
)


def test_journey_01_happy_path(e2e_env):
    result = journey_happy_path(e2e_env)
    assert result["calendar_events"] == 1
    assert result["reply_sent"] is False
    e2e_env.gates.assert_all_zero()


def test_journey_02_rejection_path(e2e_env):
    result = journey_rejection_path(e2e_env)
    assert result["case_id"]
    assert result["other_case_id"]
    e2e_env.gates.assert_all_zero()


def test_journey_03_interview_reschedule_no_duplicate_calendar(e2e_env):
    result = journey_interview_reschedule(e2e_env)
    assert result["calendar_events"] <= 2
    e2e_env.gates.assert_all_zero()


def test_journey_04_ambiguous_mail_requires_review(e2e_env):
    result = journey_ambiguous_mail(e2e_env)
    assert result["status"]
    e2e_env.gates.assert_all_zero()


def test_journey_05_offline_user(e2e_env):
    result = journey_offline(e2e_env)
    assert result["offline_ok"] is True
    e2e_env.gates.assert_all_zero()


@pytest.mark.parametrize("persona_id", [f"PERSONA_{i}" for i in range(1, 9)])
def test_journey_persona_profile_persists_across_restart(e2e_env, persona_id):
    from tests.e2e.fixtures.personas import get_persona
    from tests.e2e.harness import apply_persona

    persona = get_persona(persona_id)
    apply_persona(e2e_env, persona)
    expected_email = persona["profile"]["email"]
    e2e_env.reload()
    assert e2e_env.cfg.application.email == expected_email
    # Second restart
    e2e_env.reload()
    assert e2e_env.cfg.application.first_name == persona["profile"]["first_name"]
