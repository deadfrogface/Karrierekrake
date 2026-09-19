"""PR32 follow-up eligibility + restart-persistent reminders."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from core.case_pipeline import refresh_follow_up_tasks
from core.database import Database
from core.lifecycle import ApplicationCase, CaseStatus
from integrations.followup import (
    FollowUpPolicy,
    evaluate_eligibility,
    suggest_follow_ups,
)
from integrations.reminders import (
    REMINDER_SCHEMA_VERSION,
    ReminderScheduler,
    ReminderStore,
    sync_reminders_from_suggestions,
)


NOW = datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc)


def _case(**kwargs) -> dict:
    base = {
        "id": "c1",
        "company": "Acme Demo",
        "position": "Analyst",
        "status": CaseStatus.APPLIED.value,
        "applied_at": (NOW - timedelta(days=10)).isoformat(),
        "updated_at": (NOW - timedelta(days=1)).isoformat(),
        "created_at": (NOW - timedelta(days=10)).isoformat(),
    }
    base.update(kwargs)
    return base


def test_policy_rejects_inverted_thresholds():
    with pytest.raises(ValueError):
        FollowUpPolicy(follow_up_days=20, ghosted_days=10)


def test_suggest_requires_explicit_thresholds():
    with pytest.raises(TypeError):
        suggest_follow_ups([_case()])


def test_eligibility_below_threshold():
    policy = FollowUpPolicy(follow_up_days=14, ghosted_days=21)
    r = evaluate_eligibility(_case(applied_at=(NOW - timedelta(days=5)).isoformat()), policy, now=NOW)
    assert r.eligible is False
    assert r.reason == "below_threshold"


def test_eligibility_follow_up_then_ghosted_by_config():
    policy = FollowUpPolicy(follow_up_days=7, ghosted_days=20)
    r1 = evaluate_eligibility(_case(applied_at=(NOW - timedelta(days=10)).isoformat()), policy, now=NOW)
    assert r1.eligible and r1.kind == "follow_up"
    r2 = evaluate_eligibility(_case(applied_at=(NOW - timedelta(days=25)).isoformat()), policy, now=NOW)
    assert r2.eligible and r2.kind == "ghosted"


def test_no_hardcoded_14_day_ghosting_rule():
    """Ghosting uses configured ghosted_days, not a fixed 14."""
    policy = FollowUpPolicy(follow_up_days=3, ghosted_days=5)
    r = evaluate_eligibility(_case(applied_at=(NOW - timedelta(days=6)).isoformat()), policy, now=NOW)
    assert r.kind == "ghosted"
    # At 4 days: follow_up, not ghosted — proves 14 is not hardwired.
    r2 = evaluate_eligibility(_case(applied_at=(NOW - timedelta(days=4)).isoformat()), policy, now=NOW)
    assert r2.kind == "follow_up"


def test_feature_disable_returns_empty():
    policy = FollowUpPolicy(follow_up_days=1, ghosted_days=2, enabled=False)
    assert suggest_follow_ups([_case()], policy=policy) == []
    r = evaluate_eligibility(_case(), policy, now=NOW)
    assert r.reason == "feature_disabled"


def test_terminal_status_not_eligible():
    policy = FollowUpPolicy(follow_up_days=1, ghosted_days=2)
    r = evaluate_eligibility(
        _case(status=CaseStatus.REJECTED.value, applied_at=(NOW - timedelta(days=40)).isoformat()),
        policy,
        now=NOW,
    )
    assert r.eligible is False


def test_suggestions_never_auto_send():
    policy = FollowUpPolicy(follow_up_days=7, ghosted_days=20)
    sugs = suggest_follow_ups(
        [_case(applied_at=(NOW - timedelta(days=25)).isoformat())],
        policy=policy,
        now=NOW,
    )
    assert sugs
    assert all(s.auto_send is False for s in sugs)


def test_reminders_persist_across_restart(tmp_path: Path):
    db = Database(tmp_path / "r.db")
    old = (NOW - timedelta(days=30)).isoformat()
    db.upsert_case(
        ApplicationCase(
            id="c-persist",
            company="Persist Demo",
            position="Dev",
            status=CaseStatus.APPLIED.value,
            applied_at=old,
            updated_at=old,
        )
    )
    policy = FollowUpPolicy(
        follow_up_days=14,
        ghosted_days=21,
        reminders_enabled=True,
        schema_version=REMINDER_SCHEMA_VERSION,
    )
    sugs = suggest_follow_ups([c.to_dict() for c in db.list_cases()], policy=policy, now=NOW)
    store = ReminderStore(db)
    created = sync_reminders_from_suggestions(store, sugs, policy=policy)
    assert created >= 1
    # Simulate restart: new store/db handle
    db2 = Database(tmp_path / "r.db")
    store2 = ReminderStore(db2)
    open_rows = store2.list_open()
    assert open_rows
    assert all(r.auto_send is False for r in open_rows)
    assert all(int(r.schema_version) == REMINDER_SCHEMA_VERSION for r in open_rows)
    assert all(r.case_id == "c-persist" for r in open_rows)


def test_reminders_disabled_by_default_policy(tmp_path: Path):
    db = Database(tmp_path / "r2.db")
    policy = FollowUpPolicy(follow_up_days=1, ghosted_days=2, reminders_enabled=False)
    sugs = suggest_follow_ups(
        [_case(id="c2", applied_at=(NOW - timedelta(days=10)).isoformat())],
        policy=policy,
        now=NOW,
    )
    n = sync_reminders_from_suggestions(ReminderStore(db), sugs, policy=policy)
    assert n == 0
    assert ReminderStore(db).list_open() == []


def test_scheduler_does_not_start_when_disabled(tmp_path: Path):
    db = Database(tmp_path / "r3.db")
    policy = FollowUpPolicy(follow_up_days=1, ghosted_days=2, reminders_enabled=False)
    sched = ReminderScheduler(ReminderStore(db), policy=policy)
    assert sched.start() is False
    assert sched.running is False


def test_refresh_follow_up_tasks_requires_explicit_policy(tmp_path: Path):
    db = Database(tmp_path / "r4.db")
    with pytest.raises(TypeError):
        refresh_follow_up_tasks(db)


def test_refresh_uses_policy_and_never_autosend(tmp_path: Path):
    db = Database(tmp_path / "r5.db")
    old = (NOW - timedelta(days=30)).isoformat()
    db.upsert_case(
        ApplicationCase(
            id="c5",
            company="Pipe Demo",
            position="Dev",
            status=CaseStatus.APPLIED.value,
            applied_at=old,
            updated_at=old,
        )
    )
    n = refresh_follow_up_tasks(db, follow_up_days=14, ghosted_days=21)
    assert n >= 1
    tasks = db.list_lifecycle_tasks(status="open")
    assert tasks
    assert all(int(t.get("auto_send") or 0) == 0 for t in tasks)
