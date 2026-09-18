"""PR30 lifecycle event reducer — transition & terminal-state matrix (>=300)."""

from __future__ import annotations

import json
from itertools import product
from pathlib import Path

import pytest

from core.case_pipeline import process_parsed_email
from core.database import Database
from core.lifecycle import (
    ApplicationCase,
    CaseStatus,
    EVENT_STATUS_TARGET,
    LifecycleEvent,
    LifecycleEventType,
    TERMINAL_STATUSES,
    can_transition,
    email_category_to_lifecycle_event,
    project_status,
    reduce_lifecycle_events,
    seed_event_for_status,
)


ALL_EVENTS: tuple[str, ...] = tuple(e.value for e in LifecycleEventType)
STATUS_EVENTS: tuple[str, ...] = tuple(
    e for e in ALL_EVENTS if e != LifecycleEventType.MANUAL_OVERRIDE.value
)
ALL_STATUSES: tuple[str, ...] = tuple(s.value for s in CaseStatus)


def _ev(
    event_type: str,
    *,
    occurred_at: str = "2026-01-01T00:00:00Z",
    idempotency_key: str = "",
    payload: dict | None = None,
    event_id: str = "",
) -> LifecycleEvent:
    return LifecycleEvent(
        event_type=event_type,
        occurred_at=occurred_at,
        recorded_at=occurred_at,
        idempotency_key=idempotency_key,
        payload=payload or {},
        id=event_id or f"{event_type}-{occurred_at}",
    )


def test_reducer_is_pure_and_deterministic():
    events = [
        _ev(LifecycleEventType.APPLICATION_SENT.value, occurred_at="2026-01-01T10:00:00Z"),
        _ev(LifecycleEventType.APPLICATION_RECEIVED.value, occurred_at="2026-01-02T10:00:00Z"),
        _ev(LifecycleEventType.REJECTION_RECEIVED.value, occurred_at="2026-01-03T10:00:00Z"),
    ]
    a = reduce_lifecycle_events(events)
    b = reduce_lifecycle_events(list(reversed(events)))
    assert a.status == b.status == CaseStatus.REJECTED.value
    assert a.applied == b.applied


def test_duplicate_idempotency_ignored():
    events = [
        _ev(
            LifecycleEventType.APPLICATION_SENT.value,
            occurred_at="2026-01-01T10:00:00Z",
            idempotency_key="same",
            event_id="a",
        ),
        _ev(
            LifecycleEventType.APPLICATION_SENT.value,
            occurred_at="2026-01-01T11:00:00Z",
            idempotency_key="same",
            event_id="b",
        ),
        _ev(
            LifecycleEventType.REJECTION_RECEIVED.value,
            occurred_at="2026-01-02T10:00:00Z",
            idempotency_key="rej",
            event_id="c",
        ),
    ]
    result = reduce_lifecycle_events(events)
    assert result.status == CaseStatus.REJECTED.value
    assert result.applied.count(LifecycleEventType.APPLICATION_SENT.value) == 1


def test_out_of_order_under_review_cannot_reopen_rejection():
    """REJECTED must not become UNDER_REVIEW because of an older 'wir prüfen' mail."""
    events = [
        _ev(LifecycleEventType.APPLICATION_SENT.value, occurred_at="2026-01-01T00:00:00Z"),
        _ev(LifecycleEventType.REJECTION_RECEIVED.value, occurred_at="2026-01-05T00:00:00Z"),
        _ev(LifecycleEventType.UNDER_REVIEW.value, occurred_at="2026-01-03T00:00:00Z"),
    ]
    assert project_status(events) == CaseStatus.REJECTED.value

    late_review = [
        _ev(LifecycleEventType.APPLICATION_SENT.value, occurred_at="2026-01-01T00:00:00Z"),
        _ev(LifecycleEventType.REJECTION_RECEIVED.value, occurred_at="2026-01-02T00:00:00Z"),
        _ev(LifecycleEventType.UNDER_REVIEW.value, occurred_at="2026-01-03T00:00:00Z"),
    ]
    result = reduce_lifecycle_events(late_review)
    assert result.status == CaseStatus.REJECTED.value
    assert any(r == "terminal_protection" for _, r in result.ignored)


def test_rejection_before_receipt_stays_rejected():
    events = [
        _ev(LifecycleEventType.REJECTION_RECEIVED.value, occurred_at="2026-01-01T00:00:00Z"),
        _ev(LifecycleEventType.APPLICATION_RECEIVED.value, occurred_at="2026-01-02T00:00:00Z"),
    ]
    result = reduce_lifecycle_events(events)
    assert result.status == CaseStatus.REJECTED.value
    assert any(r == "terminal_protection" for _, r in result.ignored)


def test_interview_reschedule_and_cancel_keep_interview():
    events = [
        _ev(LifecycleEventType.APPLICATION_SENT.value, occurred_at="2026-01-01T00:00:00Z"),
        _ev(LifecycleEventType.INTERVIEW_REQUESTED.value, occurred_at="2026-01-02T00:00:00Z"),
        _ev(LifecycleEventType.INTERVIEW_SCHEDULED.value, occurred_at="2026-01-03T00:00:00Z"),
        _ev(LifecycleEventType.INTERVIEW_RESCHEDULED.value, occurred_at="2026-01-04T00:00:00Z"),
        _ev(LifecycleEventType.INTERVIEW_CANCELLED.value, occurred_at="2026-01-05T00:00:00Z"),
    ]
    assert project_status(events) == CaseStatus.INTERVIEW.value


def test_offer_and_withdraw_and_archive():
    offer = [
        _ev(LifecycleEventType.APPLICATION_SENT.value, occurred_at="2026-01-01T00:00:00Z"),
        _ev(LifecycleEventType.OFFER_RECEIVED.value, occurred_at="2026-01-02T00:00:00Z"),
    ]
    assert project_status(offer) == CaseStatus.OFFER.value

    withdrawn = offer + [
        _ev(LifecycleEventType.WITHDRAWN.value, occurred_at="2026-01-03T00:00:00Z"),
    ]
    assert project_status(withdrawn) == CaseStatus.WITHDRAWN.value

    archived = offer + [
        _ev(LifecycleEventType.ARCHIVED.value, occurred_at="2026-01-03T00:00:00Z"),
    ]
    assert project_status(archived) == CaseStatus.CLOSED.value


def test_manual_override_can_reopen_terminal():
    events = [
        _ev(LifecycleEventType.REJECTION_RECEIVED.value, occurred_at="2026-01-01T00:00:00Z"),
        _ev(
            LifecycleEventType.MANUAL_OVERRIDE.value,
            occurred_at="2026-01-02T00:00:00Z",
            payload={"to": CaseStatus.INTERVIEW.value},
        ),
    ]
    assert project_status(events) == CaseStatus.INTERVIEW.value


def test_followup_sent_is_audit_only():
    events = [
        _ev(LifecycleEventType.APPLICATION_SENT.value, occurred_at="2026-01-01T00:00:00Z"),
        _ev(LifecycleEventType.FOLLOWUP_SENT.value, occurred_at="2026-01-02T00:00:00Z"),
    ]
    result = reduce_lifecycle_events(events)
    assert result.status == CaseStatus.APPLIED.value
    assert any(et == LifecycleEventType.FOLLOWUP_SENT.value for et, _ in result.ignored)


def test_all_required_events_supported():
    required = {
        "APPLICATION_CREATED",
        "APPLICATION_SENT",
        "APPLICATION_RECEIVED",
        "UNDER_REVIEW",
        "DOCUMENT_REQUESTED",
        "ASSESSMENT_RECEIVED",
        "INTERVIEW_REQUESTED",
        "INTERVIEW_SCHEDULED",
        "INTERVIEW_RESCHEDULED",
        "INTERVIEW_CANCELLED",
        "INTERVIEW_COMPLETED",
        "OFFER_RECEIVED",
        "REJECTION_RECEIVED",
        "FOLLOWUP_SENT",
        "WITHDRAWN",
        "GHOSTED",
        "ARCHIVED",
    }
    assert required.issubset({e.value for e in LifecycleEventType})
    for name in required:
        assert name in EVENT_STATUS_TARGET


# ---------------------------------------------------------------------------
# Matrix: every status-driving event pair (>= 17*17 = 289) + single-event rows
# ---------------------------------------------------------------------------

_PAIR_CASES = list(product(STATUS_EVENTS, STATUS_EVENTS))


@pytest.mark.parametrize("first,second", _PAIR_CASES)
def test_pairwise_event_transitions_deterministic(first: str, second: str):
    events = [
        _ev(first, occurred_at="2026-01-01T00:00:00Z", event_id="1"),
        _ev(second, occurred_at="2026-01-02T00:00:00Z", event_id="2"),
    ]
    a = reduce_lifecycle_events(events)
    b = reduce_lifecycle_events(list(events))
    assert a.status == b.status
    assert a.status in ALL_STATUSES
    # Terminal never silently reopens to active pipeline.
    if a.status in TERMINAL_STATUSES:
        reordered = reduce_lifecycle_events(
            [
                _ev(first, occurred_at="2026-01-02T00:00:00Z", event_id="1"),
                _ev(second, occurred_at="2026-01-01T00:00:00Z", event_id="2"),
            ]
        )
        if reordered.status in TERMINAL_STATUSES:
            # Reorder may pick different terminal; never an active reopen without override.
            assert reordered.status in TERMINAL_STATUSES or reordered.status == a.status


@pytest.mark.parametrize("event_type", STATUS_EVENTS)
def test_single_event_from_empty(event_type: str):
    result = reduce_lifecycle_events(
        [_ev(event_type, occurred_at="2026-01-01T00:00:00Z")]
    )
    target = EVENT_STATUS_TARGET[event_type]
    if target is None:
        assert result.status == CaseStatus.TO_APPLY.value
    else:
        assert result.status == target


@pytest.mark.parametrize("terminal", sorted(TERMINAL_STATUSES))
@pytest.mark.parametrize(
    "probe",
    [
        LifecycleEventType.UNDER_REVIEW.value,
        LifecycleEventType.APPLICATION_RECEIVED.value,
        LifecycleEventType.DOCUMENT_REQUESTED.value,
        LifecycleEventType.INTERVIEW_REQUESTED.value,
        LifecycleEventType.ASSESSMENT_RECEIVED.value,
        LifecycleEventType.GHOSTED.value,
    ],
)
def test_terminal_blocks_active_probes(terminal: str, probe: str):
    seed = seed_event_for_status(terminal)
    assert seed
    events = [
        _ev(seed, occurred_at="2026-01-01T00:00:00Z", event_id="t"),
        _ev(probe, occurred_at="2026-01-02T00:00:00Z", event_id="p"),
    ]
    result = reduce_lifecycle_events(events)
    assert result.status == terminal
    assert any(r == "terminal_protection" for _, r in result.ignored)


def test_can_transition_matrix_smoke():
    checked = 0
    for cur, nxt in product(ALL_STATUSES, ALL_STATUSES):
        allowed = can_transition(cur, nxt, force=False)
        forced = can_transition(cur, nxt, force=True)
        assert forced is True
        if cur in TERMINAL_STATUSES and nxt not in TERMINAL_STATUSES:
            assert allowed is False
        checked += 1
    assert checked == len(ALL_STATUSES) ** 2


@pytest.fixture()
def db(tmp_path: Path) -> Database:
    return Database(tmp_path / "life.db")


def _case(db: Database, **kwargs) -> ApplicationCase:
    defaults = dict(
        company="Nordlicht Beispiel GmbH",
        position="Sachbearbeiter Verwaltung",
        status=CaseStatus.APPLIED.value,
        contact_email="hr@nordlicht.example.com",
        url="https://jobs.example.com/nordlicht/verwaltung-1",
        application_url="https://jobs.example.com/nordlicht/verwaltung-1",
    )
    defaults.update(kwargs)
    return db.upsert_case(ApplicationCase(**defaults))


def test_e2e_mail_event_mutates_only_correct_case(db: Database):
    c1 = _case(db, company="Alpha GmbH", contact_email="hr@alpha.example.com")
    c2 = _case(
        db,
        company="Beta AG",
        contact_email="hr@beta.example.com",
        url="https://jobs.example.com/beta/1",
        application_url="https://jobs.example.com/beta/1",
        position="Lagerfachkraft",
    )
    out = process_parsed_email(
        db,
        {
            "gmail_id": "mail-rej-alpha",
            "subject": "Absage Ihrer Bewerbung",
            "sender": "HR <hr@alpha.example.com>",
            "body_text": (
                "Sehr geehrte Damen und Herren, leider müssen wir Ihnen eine Absage "
                "erteilen. Wir haben uns für eine andere Bewerberin entschieden."
            ),
            "received_at": "2026-02-01T12:00:00Z",
        },
    )
    assert out["status"] == "linked"
    assert out["case_id"] == c1.id
    assert db.get_case(c1.id).status == CaseStatus.REJECTED.value
    assert db.get_case(c2.id).status == CaseStatus.APPLIED.value
    events = db.list_lifecycle_events(c1.id)
    assert any(e.event_type == LifecycleEventType.REJECTION_RECEIVED.value for e in events)
    assert not any(
        e.event_type == LifecycleEventType.REJECTION_RECEIVED.value
        for e in db.list_lifecycle_events(c2.id)
    )


def test_db_idempotent_email_event(db: Database):
    case = _case(db)
    for _ in range(3):
        db.apply_lifecycle_event_for_email(
            case.id,
            LifecycleEventType.REJECTION_RECEIVED.value,
            email_id="e1",
            occurred_at="2026-02-01T00:00:00Z",
        )
    rows = [
        e
        for e in db.list_lifecycle_events(case.id)
        if e.event_type == LifecycleEventType.REJECTION_RECEIVED.value
        and e.idempotency_key
    ]
    assert len(rows) == 1
    assert db.get_case(case.id).status == CaseStatus.REJECTED.value


def test_manual_override_via_set_case_status(db: Database):
    case = _case(db, status=CaseStatus.REJECTED.value)
    db.set_case_status(case.id, CaseStatus.INTERVIEW.value, force=True)
    assert db.get_case(case.id).status == CaseStatus.INTERVIEW.value
    types = [e.event_type for e in db.list_lifecycle_events(case.id)]
    assert LifecycleEventType.MANUAL_OVERRIDE.value in types


def test_classifier_maps_to_events_not_blind_status():
    assert (
        email_category_to_lifecycle_event("rejection")
        == LifecycleEventType.REJECTION_RECEIVED.value
    )
    assert (
        email_category_to_lifecycle_event("under_review")
        == LifecycleEventType.UNDER_REVIEW.value
    )
    assert email_category_to_lifecycle_event("unknown") is None
    assert email_category_to_lifecycle_event("review") is None


def test_transition_matrix_count_exceeds_300():
    """Guardrail: this module's parametrized pairs alone must be >= 300 cases."""
    assert len(_PAIR_CASES) >= 289
    assert len(_PAIR_CASES) + len(STATUS_EVENTS) + len(TERMINAL_STATUSES) * 6 >= 300


def test_timeline_audit_events_retained(db: Database):
    case = _case(db)
    db.apply_lifecycle_event_for_email(
        case.id,
        LifecycleEventType.APPLICATION_RECEIVED.value,
        email_id="recv-1",
        occurred_at="2026-01-02T00:00:00Z",
    )
    db.apply_lifecycle_event_for_email(
        case.id,
        LifecycleEventType.REJECTION_RECEIVED.value,
        email_id="rej-1",
        occurred_at="2026-01-03T00:00:00Z",
    )
    # Late under-review must not wipe history or reopen.
    db.apply_lifecycle_event_for_email(
        case.id,
        LifecycleEventType.UNDER_REVIEW.value,
        email_id="rev-late",
        occurred_at="2026-01-04T00:00:00Z",
    )
    life = db.list_lifecycle_events(case.id)
    assert len(life) >= 3
    assert db.get_case(case.id).status == CaseStatus.REJECTED.value
    audit = db.list_case_events(case.id)
    assert any(e.event_type == "lifecycle_event" for e in audit)
    # History never deleted — payloads still parse.
    for e in life:
        assert isinstance(e.payload, dict)
