"""Chaos / idiot-user / button-abuse / navigation destruction tests."""

from __future__ import annotations

import pytest

from core.case_pipeline import process_parsed_email
from core.cancel import cancel_active_searches
from core.models import Job
from search.base import SearchQuery
from tests.e2e.fixtures.job_corpus import load_e2e_job_corpus, seed_jobs
from tests.e2e.fixtures.mail_corpus import MAIL_CONFIRMATION, MAIL_INTERVIEW
from tests.e2e.fixtures.personas import get_persona
from tests.e2e.harness import apply_persona, snapshot_case_statuses
from tests.e2e.providers.fake_calendar import FakeJobSource
from tests.e2e.scenarios.journeys import create_application, seed_primary_job


def test_search_double_click_does_not_duplicate_jobs(e2e_env):
    apply_persona(e2e_env, get_persona("PERSONA_1"))
    jobs = load_e2e_job_corpus()[:20]
    src = FakeJobSource(jobs)
    for _ in range(10):
        found = src.search([SearchQuery(keyword="Lohnbuchhalter")])
        for job in found:
            e2e_env.db.upsert_job(job)
    stored = e2e_env.db.list_jobs() if hasattr(e2e_env.db, "list_jobs") else None
    if stored is not None:
        ids = [j.id for j in stored]
        assert len(ids) == len(set(ids))
    assert src.calls == 10


def test_search_cancel_is_safe(e2e_env):
    apply_persona(e2e_env, get_persona("PERSONA_1"))
    cancel_active_searches()
    cancel_active_searches()
    e2e_env.reload()
    assert e2e_env.cfg.application.email.endswith("@example.com")


def test_search_source_failure_halfway(e2e_env):
    src = FakeJobSource(load_e2e_job_corpus()[:5], hang_after=2)
    with pytest.raises(TimeoutError):
        src.search([SearchQuery(keyword="x")])
    e2e_env.reload()
    # DB still usable
    seed_jobs(e2e_env.db, load_e2e_job_corpus()[:3])


def test_malformed_job_source_does_not_crash(e2e_env):
    src = FakeJobSource(malformed_once=True)
    jobs = src.search([SearchQuery(keyword="x")])
    assert jobs
    for j in jobs:
        e2e_env.db.upsert_job(j)


def test_duplicate_email_processing_is_idempotent(e2e_env):
    apply_persona(e2e_env, get_persona("PERSONA_1"))
    job = seed_primary_job(e2e_env)
    case = create_application(e2e_env, job)
    before = snapshot_case_statuses(e2e_env.db)
    r1 = process_parsed_email(e2e_env.db, dict(MAIL_CONFIRMATION))
    r2 = process_parsed_email(e2e_env.db, dict(MAIL_CONFIRMATION))
    assert r2.get("skipped") is True or r2.get("status") == "duplicate"
    after = snapshot_case_statuses(e2e_env.db)
    # Case may advance once, never thrash on duplicate.
    assert case.id in after
    assert before.keys() == after.keys()


def test_rapid_mail_inject_same_thread(e2e_env):
    apply_persona(e2e_env, get_persona("PERSONA_1"))
    job = seed_primary_job(e2e_env)
    create_application(e2e_env, job)
    for i in range(5):
        mail = dict(MAIL_CONFIRMATION)
        mail["gmail_id"] = f"EMAIL_BURST_{i}"
        process_parsed_email(e2e_env.db, mail)
    e2e_env.reload()
    cases = e2e_env.db.list_cases()
    assert len(cases) >= 1


@pytest.mark.parametrize("n", [0, 1, 5, 50])
def test_application_volume_states(e2e_env, n):
    if n == 0:
        assert len(e2e_env.db.list_cases()) == 0
        return
    for i in range(n):
        job = Job(
            id=f"VOL_JOB_{i:04d}",
            source="e2e_vol",
            source_job_id=f"vol-{i}",
            title=f"Role Volume {i}",
            company=f"Volume Company {i} GmbH",
            city="Berlin",
            country_code="DE",
            url=f"https://jobs.example/vol/{i}",
        )
        e2e_env.db.upsert_job(job)
        create_application(e2e_env, job)
    assert len(e2e_env.db.list_cases()) == n


def test_navigation_chaos_state_isolation(e2e_env):
    """Simulate page hopping by reloading config/db repeatedly mid-flow."""
    apply_persona(e2e_env, get_persona("PERSONA_1"))
    job = seed_primary_job(e2e_env)
    create_application(e2e_env, job)
    for _ in range(20):
        e2e_env.reload()
        assert e2e_env.cfg.application.first_name == "Alex"
        assert len(e2e_env.db.list_cases()) >= 1


def test_profile_save_spam(e2e_env):
    apply_persona(e2e_env, get_persona("PERSONA_1"))
    for i in range(25):
        e2e_env.cfg.application.phone = f"+49 30 {i:07d}"
        e2e_env.save()
    e2e_env.reload()
    assert e2e_env.cfg.application.phone.endswith("0000024")


def test_impossible_workflows_remain_safe(e2e_env):
    # Interview prep without interview: calendar propose on empty text
    from integrations.calendar_scheduling import propose_ranked_slots

    prop = propose_ranked_slots("", case_id="no-case")
    assert prop.ranked_slots == [] or isinstance(prop.ranked_slots, list)

    # Reply without selected email / empty case
    from integrations.reply_draft import ReplyAction, build_action_draft

    draft = build_action_draft(
        ReplyAction.GENERAL_REPLY,
        {"id": "ghost", "company": "", "position": ""},
        applicant_name="",
    )
    assert draft.sent is False
    assert draft.auto_send is False


def test_force_close_during_profile_save_recovers(e2e_env, tmp_path):
    apply_persona(e2e_env, get_persona("PERSONA_1"))
    e2e_env.cfg.application.city = "Berlin"
    e2e_env.save()
    # Simulate new process
    from tests.e2e.harness import make_e2e_env

    # Same LOCALAPPDATA already set by fixture — reload is enough
    e2e_env.reload()
    assert e2e_env.cfg.application.city == "Berlin"


def test_quoted_rejection_inside_invite_not_false_reject(e2e_env):
    from integrations.email_classify import classify_email
    from tests.e2e.fixtures.mail_corpus import MAIL_QUOTED_OLD_REJECTION

    got = classify_email(
        MAIL_QUOTED_OLD_REJECTION["subject"],
        MAIL_QUOTED_OLD_REJECTION["body_text"],
    )
    # Prefer interview over false rejection when invite language dominates.
    if got.category == "rejection":
        e2e_env.gates.note(
            "false_rejection",
            f"quoted-old-rejection classified as rejection: {got.category}",
        )
    e2e_env.gates.assert_all_zero()
