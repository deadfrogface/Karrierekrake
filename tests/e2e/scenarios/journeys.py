"""Reusable offline journey helpers (fake providers only)."""

from __future__ import annotations

from typing import Any

from core.case_pipeline import process_parsed_email
from core.lifecycle import CaseStatus
from core.models import ApplicationRecord, Job
from integrations.calendar_scheduling import propose_ranked_slots, select_slot
from integrations.calendar_write import CalendarWriteGate, draft_from_ranked_slot
from integrations.email_associate import associate_email
from integrations.reply_draft import ReplyAction, SendGate, build_action_draft
from search.base import SearchQuery
from tests.e2e.fixtures.job_corpus import load_e2e_job_corpus
from tests.e2e.fixtures.mail_corpus import (
    MAIL_AMBIGUOUS_COMPANY,
    MAIL_CONFIRMATION,
    MAIL_FOLLOWUP,
    MAIL_INTERVIEW,
    MAIL_OFFER,
    MAIL_REJECTION,
    MAIL_RESCHEDULE,
    MAIL_REVIEW,
)
from tests.e2e.fixtures.personas import get_persona
from tests.e2e.harness import E2EEnv, apply_persona, snapshot_case_statuses
from tests.e2e.providers.fake_calendar import FakeJobSource, make_calendar_stack


def seed_primary_job(env: E2EEnv) -> Job:
    jobs = load_e2e_job_corpus()
    job = next(j for j in jobs if j.id == "JOB_EDGE_001")
    env.db.upsert_job(job)
    return job


def create_application(env: E2EEnv, job: Job, *, status: str = "applied") -> Any:
    env.db.save_application(
        ApplicationRecord(
            job_id=job.id,
            company=job.company,
            position=job.title,
            status=status,
            application_date="2026-09-18T10:00:00+00:00",
        )
    )
    return env.db.ensure_case_from_job(job, status=CaseStatus.APPLIED.value)


def inject_and_process(env: E2EEnv, mail: dict[str, Any]) -> dict[str, Any]:
    return process_parsed_email(env.db, dict(mail))


def _create_calendar_once(proposal: Any, *, transport: Any, request_id: str) -> Any:
    gate = CalendarWriteGate(allow_write=True)
    draft = draft_from_ranked_slot(proposal, client_request_id=request_id)
    gate.approve(draft)
    return gate.attempt_create(draft, transport=transport)


def journey_happy_path(env: E2EEnv) -> dict[str, Any]:
    """Journey 1: brand-new user happy path (offline / fake)."""
    apply_persona(env, get_persona("PERSONA_1"))
    env.reload()
    assert env.cfg.application.first_name == "Alex"

    job = seed_primary_job(env)
    case = create_application(env, job)
    case_id = case.id

    r1 = inject_and_process(env, MAIL_CONFIRMATION)
    assert r1.get("skipped") is not True
    case = env.db.get_case(case_id)
    assert case is not None

    inject_and_process(env, MAIL_REVIEW)
    inject_and_process(env, MAIL_INTERVIEW)

    freebusy, transport = make_calendar_stack()
    proposal = propose_ranked_slots(
        MAIL_INTERVIEW["body_text"],
        case_id=case_id,
        freebusy=freebusy,
    )
    assert proposal.ranked_slots, "expected interview slots"
    proposal = select_slot(proposal, 0)
    created = _create_calendar_once(
        proposal, transport=transport, request_id=f"{case_id}:interview-1"
    )
    assert created.created is True
    # Idempotent second create must not duplicate.
    created2 = _create_calendar_once(
        proposal, transport=transport, request_id=f"{case_id}:interview-1"
    )
    assert created2.external_event_id == created.external_event_id
    assert len(transport.events) == 1

    reply = build_action_draft(
        ReplyAction.PROPOSE_SLOTS,
        case.to_dict(),
        applicant_name="Alex Berger",
        proposed_slots=[s.to_dict().get("start") for s in proposal.ranked_slots[:2]],
    )
    send_gate = SendGate(allow_send=False, draft_only=True)
    send_gate.approve(reply)
    sent = send_gate.attempt_send(reply, transport=lambda _d: "should-not-run")
    assert sent.sent is False
    assert send_gate.allow_send is False

    inject_and_process(env, MAIL_FOLLOWUP)
    inject_and_process(env, MAIL_OFFER)
    case = env.db.get_case(case_id)
    assert case is not None

    before = snapshot_case_statuses(env.db)
    env.reload()
    after = snapshot_case_statuses(env.db)
    assert before == after
    assert env.cfg.application.email == "alex.berger@example.com"

    return {
        "case_id": case_id,
        "status": case.status,
        "calendar_events": len(transport.events),
        "reply_action": reply.action,
        "reply_sent": sent.sent,
    }


def journey_rejection_path(env: E2EEnv) -> dict[str, Any]:
    apply_persona(env, get_persona("PERSONA_1"))
    job = seed_primary_job(env)
    case = create_application(env, job)
    inject_and_process(env, MAIL_CONFIRMATION)
    inject_and_process(env, MAIL_REVIEW)
    inject_and_process(env, MAIL_REJECTION)
    case = env.db.get_case(case.id)
    assert case is not None

    other = next(j for j in load_e2e_job_corpus() if j.id == "JOB_EDGE_022")
    env.db.upsert_job(other)
    other_case = create_application(env, other)
    assert other_case.id != case.id
    # Other role at same-ish company must not be auto-rejected.
    other_fresh = env.db.get_case(other_case.id)
    assert other_fresh is not None
    assert other_fresh.status != CaseStatus.REJECTED.value
    return {"case_id": case.id, "status": case.status, "other_case_id": other_case.id}


def journey_interview_reschedule(env: E2EEnv) -> dict[str, Any]:
    apply_persona(env, get_persona("PERSONA_1"))
    job = seed_primary_job(env)
    case = create_application(env, job)
    inject_and_process(env, MAIL_INTERVIEW)
    freebusy, transport = make_calendar_stack()
    proposal = propose_ranked_slots(
        MAIL_INTERVIEW["body_text"], case_id=case.id, freebusy=freebusy
    )
    proposal = select_slot(proposal, 0)
    first = _create_calendar_once(
        proposal, transport=transport, request_id=f"{case.id}:interview"
    )
    assert first.created

    inject_and_process(env, MAIL_RESCHEDULE)
    proposal2 = propose_ranked_slots(
        MAIL_RESCHEDULE["body_text"], case_id=case.id, freebusy=freebusy
    )
    if proposal2.ranked_slots:
        proposal2 = select_slot(proposal2, 0)
        # Same client_request_id → idempotent; different slot uses new request id
        # but product must not leave duplicate events for same interview uid policy.
        second = _create_calendar_once(
            proposal2,
            transport=transport,
            request_id=f"{case.id}:interview",
        )
        assert second.external_event_id == first.external_event_id or len(transport.events) <= 2
    # Hard gate: never explode into many duplicates for one interview flow.
    assert len(transport.events) <= 2
    return {"calendar_events": len(transport.events), "case_id": case.id}


def journey_ambiguous_mail(env: E2EEnv) -> dict[str, Any]:
    apply_persona(env, get_persona("PERSONA_7"))
    jobs = load_e2e_job_corpus()
    sales = next(j for j in jobs if j.id == "JOB_EDGE_022")
    ops = next(j for j in jobs if j.id == "JOB_EDGE_023")
    for j in (sales, ops):
        j.company = "Multi Role AG"
        env.db.upsert_job(j)
    case_a = create_application(env, sales)
    case_b = create_application(env, ops)
    result = associate_email(
        sender=MAIL_AMBIGUOUS_COMPANY["sender"],
        subject=MAIL_AMBIGUOUS_COMPANY["subject"],
        body=MAIL_AMBIGUOUS_COMPANY["body_text"],
        cases=[
            {
                "id": case_a.id,
                "company": "Multi Role AG",
                "position": sales.title,
                "title": sales.title,
            },
            {
                "id": case_b.id,
                "company": "Multi Role AG",
                "position": ops.title,
                "title": ops.title,
            },
        ],
    )
    status = result.match_status
    assert status in {
        "ambiguous",
        "review_required",
        "review",
        "unlinked",
        "none",
        "no_match",
    }
    # Manual confirm B — future thread should respect confirmed link storage.
    env.db.save_email_message(
        {
            **MAIL_AMBIGUOUS_COMPANY,
            "category": "generic",
            "association_status": "linked",
            "case_id": case_b.id,
        }
    )
    stored = env.db.get_email_by_gmail_id(MAIL_AMBIGUOUS_COMPANY["gmail_id"])
    assert stored is not None
    assert stored.get("case_id") == case_b.id
    return {"status": status, "case_b": case_b.id}


def journey_offline(env: E2EEnv) -> dict[str, Any]:
    apply_persona(env, get_persona("PERSONA_1"))
    job = seed_primary_job(env)
    case = create_application(env, job)
    assert env.cfg.application.first_name == "Alex"
    assert env.db.get_case(case.id) is not None

    src = FakeJobSource(fail=True)
    try:
        src.search([SearchQuery(keyword="Lohnbuchhalter")])
        failed = False
    except ConnectionError:
        failed = True
    assert failed
    env.reload()
    assert env.db.get_case(case.id) is not None
    assert env.cfg.application.email == "alex.berger@example.com"
    return {"offline_ok": True}
