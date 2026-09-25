"""Hostile post-application lifecycle tests — fictional email corpus only."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from apply.manager import ApplicationManager
from core.case_pipeline import process_parsed_email, refresh_follow_up_tasks
from core.config import empty_app_config
from core.database import Database
from core.known_jobs import refuse_reapply, should_suppress_as_new
from core.lifecycle import CaseStatus, can_transition
from core.models import Job, JobStatus, utc_now_iso
from integrations.calendar_availability import TimeWindow, check_interview_slot
from integrations.email_associate import associate_email
from integrations.email_classify import classify_email
from integrations.ics_export import build_meetings_ics
from integrations.interview_prep import build_interview_prep
from integrations.reply_draft import SendGate, build_follow_up_draft
from integrations.secure_tokens import delete_token, load_token, store_token


CORPUS = Path(__file__).parent / "fixtures" / "fictional_emails" / "corpus.json"


@pytest.fixture()
def db(tmp_path: Path) -> Database:
    return Database(tmp_path / "life.db")


def _case(db: Database, **kwargs):
    from core.lifecycle import ApplicationCase

    defaults = dict(
        company="Nordlicht Beispiel GmbH",
        position="Sachbearbeiter Verwaltung",
        status=CaseStatus.APPLIED.value,
        contact_email="hr@nordlicht.example.com",
        url="https://jobs.example.com/nordlicht/verwaltung-1",
        application_url="https://jobs.example.com/nordlicht/verwaltung-1",
        applied_at=utc_now_iso(),
    )
    defaults.update(kwargs)
    return db.upsert_case(ApplicationCase(**defaults))


def test_corpus_classification_matches_expectations():
    data = json.loads(CORPUS.read_text(encoding="utf-8"))
    assert len(data) >= 6
    for row in data:
        result = classify_email(row["subject"], row["body"])
        assert result.category == row["expect_category"], row["id"]
        if row.get("expect_false_rejection_blocked"):
            assert result.false_rejection_blocked or result.category == "interview"


def test_rejection_does_not_suppress_different_job_same_company(db: Database):
    _case(
        db,
        status=CaseStatus.REJECTED.value,
        position="Sachbearbeiter Verwaltung",
        url="https://jobs.example.com/nordlicht/verwaltung-1",
        application_url="https://jobs.example.com/nordlicht/verwaltung-1",
    )
    other = Job(
        id="j2",
        title="Fachkraft Lager",
        company="Nordlicht Beispiel GmbH",
        url="https://jobs.example.com/nordlicht/lager-9",
        application_url="https://jobs.example.com/nordlicht/lager-9",
        source="indeed",
    )
    suppress, reason = should_suppress_as_new(db, other)
    assert suppress is False, reason
    blocked, _ = refuse_reapply(db, other)
    assert blocked is False


def test_rejection_suppresses_same_vacancy_across_sources(db: Database):
    _case(
        db,
        status=CaseStatus.REJECTED.value,
        position="Sachbearbeiter Verwaltung",
        url="https://jobs.example.com/viewjob?jk=abc123",
        application_url="https://jobs.example.com/viewjob?jk=abc123",
    )
    twin = Job(
        id="twin",
        title="Sachbearbeiter Verwaltung",
        company="Nordlicht Beispiel GmbH",
        url="https://jobs.example.com/viewjob?jk=abc123&utm_source=x",
        application_url="",
        source="bundesagentur",
    )
    suppress, reason = should_suppress_as_new(db, twin)
    assert suppress is True
    assert "known_case" in reason


def test_interview_status_suppresses_search_rediscovery(db: Database):
    _case(db, status=CaseStatus.INTERVIEW.value)
    job = Job(
        id="j1",
        title="Sachbearbeiter Verwaltung",
        company="Nordlicht Beispiel GmbH",
        url="https://jobs.example.com/nordlicht/verwaltung-1",
        application_url="https://jobs.example.com/nordlicht/verwaltung-1",
    )
    suppress, _ = should_suppress_as_new(db, job)
    assert suppress is True


def test_manager_refuses_known_case_even_without_job_row(db: Database, tmp_path: Path):
    _case(db, status=CaseStatus.REJECTED.value)
    cfg = empty_app_config(root=tmp_path)
    cfg.settings.dry_run = True
    mgr = ApplicationManager(cfg, db)
    job = Job(
        id="new-id",
        source="indeed",
        title="Sachbearbeiter Verwaltung",
        company="Nordlicht Beispiel GmbH",
        url="https://jobs.example.com/nordlicht/verwaltung-1",
        application_url="https://jobs.example.com/nordlicht/verwaltung-1",
        match_score=99,
        ats_type="greenhouse",
    )
    # Create a dummy CV so CV checks are not the failure reason.
    cv = tmp_path / "cv.pdf"
    cv.write_bytes(b"%PDF-1.4 fictional")
    cfg.application.first_name = "Max"
    cfg.application.last_name = "Mustermann"
    cfg.application.email = "max@applicant.example.com"
    cfg.application.phone = "0123"
    cfg.application.cv_path = str(cv)
    ok, reason = mgr.can_auto_apply(job)
    assert ok is False
    assert "already applied" in reason


def test_ambiguous_association_when_two_cases_share_domain(db: Database):
    _case(
        db,
        position="Sachbearbeiter Verwaltung",
        contact_email="hr@nordlicht.example.com",
        status=CaseStatus.APPLIED.value,
    )
    _case(
        db,
        position="Teamassistenz",
        contact_email="jobs@nordlicht.example.com",
        url="https://jobs.example.com/nordlicht/assistenz",
        application_url="https://jobs.example.com/nordlicht/assistenz",
        status=CaseStatus.APPLIED.value,
    )
    cases = [c.to_dict() for c in db.list_cases()]
    result = associate_email(
        sender="People Team <noreply@nordlicht.example.com>",
        subject="Update zu Ihrer Bewerbung",
        cases=cases,
    )
    assert result.case_id is None
    assert result.ambiguous is True


def test_false_rejection_guard_does_not_force_rejected(db: Database):
    case = _case(db, status=CaseStatus.APPLIED.value, contact_email="noreply@ats.example.com")
    corpus = {r["id"]: r for r in json.loads(CORPUS.read_text(encoding="utf-8"))}
    row = corpus["fic-false-reject"]
    out = process_parsed_email(
        db,
        {
            "gmail_id": row["id"],
            "subject": row["subject"],
            "sender": row["sender"],
            "body_text": row["body"],
        },
    )
    assert out["category"] == "interview"
    refreshed = db.get_case(case.id)
    assert refreshed is not None
    assert refreshed.status != CaseStatus.REJECTED.value


def test_rejection_email_updates_case(db: Database):
    case = _case(db, status=CaseStatus.APPLIED.value)
    corpus = {r["id"]: r for r in json.loads(CORPUS.read_text(encoding="utf-8"))}
    row = corpus["fic-reject-1"]
    out = process_parsed_email(
        db,
        {
            "gmail_id": row["id"],
            "subject": row["subject"],
            "sender": row["sender"],
            "body_text": row["body"],
        },
    )
    assert out["status"] == "linked"
    assert db.get_case(case.id).status == CaseStatus.REJECTED.value


def test_calendar_working_hours_and_busy_conflict():
    busy = [
        TimeWindow(
            datetime(2026, 9, 20, 10, 0, tzinfo=timezone.utc),
            datetime(2026, 9, 20, 11, 0, tzinfo=timezone.utc),
        )
    ]
    hit = check_interview_slot(
        "2026-09-20T10:30:00+00:00",
        busy=busy,
        working_hours="09:00-17:00",
    )
    assert hit.ok is False
    assert "calendar_busy" in hit.conflicts

    outside = check_interview_slot(
        "2026-09-20T20:00:00+00:00",
        busy=[],
        working_hours="09:00-17:00",
    )
    assert outside.outside_working_hours is True
    assert outside.ok is False


def test_send_failure_keeps_draft_and_records_error():
    draft = build_follow_up_draft(
        {
            "id": "c1",
            "company": "Acme Fiktiv",
            "position": "Analyst",
            "contact_email": "hr@acme.example.com",
        },
        applicant_name="Max Mustermann",
    )
    gate = SendGate(allow_send=True)
    gate.approve(draft)

    def boom(_d):
        raise ConnectionError("smtp down")

    out = gate.attempt_send(draft, transport=boom)
    assert out.sent is False
    assert "send_failed" in out.send_error
    assert out.body  # draft preserved


def test_draft_only_default_blocks_send():
    draft = build_follow_up_draft({"id": "c1", "company": "X", "position": "Y"})
    gate = SendGate(allow_send=False)
    gate.approve(draft)
    out = gate.attempt_send(draft, transport=lambda d: None)
    assert out.sent is False
    assert out.send_error


def test_token_roundtrip_survives_restart(tmp_path: Path):
    payload = {"refresh_token": "fic-refresh", "token": "fic-access", "scopes": ["gmail.readonly"]}
    store_token("gmail_readonly", payload, fallback_dir=tmp_path / "private")
    loaded = load_token("gmail_readonly", fallback_dir=tmp_path / "private")
    assert loaded is not None
    assert loaded["refresh_token"] == "fic-refresh"
    # Simulate restart: new load
    again = load_token("gmail_readonly", fallback_dir=tmp_path / "private")
    assert again["token"] == "fic-access"
    delete_token("gmail_readonly", fallback_dir=tmp_path / "private")
    assert load_token("gmail_readonly", fallback_dir=tmp_path / "private") is None


def test_status_rank_blocks_downgrade():
    assert can_transition(CaseStatus.INTERVIEW.value, CaseStatus.CONFIRMATION.value) is False
    assert can_transition(CaseStatus.APPLIED.value, CaseStatus.INTERVIEW.value) is True


def test_follow_up_suggest_only_never_auto_send(db: Database):
    old = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    _case(db, status=CaseStatus.APPLIED.value, applied_at=old, updated_at=old)
    n = refresh_follow_up_tasks(db, follow_up_days=14, ghosted_days=21)
    assert n >= 1
    tasks = db.list_lifecycle_tasks(status="open")
    assert tasks
    assert all(int(t.get("auto_send") or 0) == 0 for t in tasks)


def test_ics_export_contains_vevent():
    ics = build_meetings_ics(
        [
            {
                "id": "m1",
                "scheduled_at": "2026-09-22T09:00:00+00:00",
                "title": "Interview (Karrierekrake)",
                "description": "Nordlicht Beispiel",
            }
        ]
    )
    assert "BEGIN:VEVENT" in ics
    assert "SUMMARY:Interview" in ics


def test_interview_prep_uses_evidence_levels():
    prep = build_interview_prep(
        case_id="c1",
        company="Acme",
        position="Analyst",
        evidence=[
            {"claim": "Excel", "support": "DIRECT", "note": "3 Jahre"},
            {"claim": "SAP", "support": "NOT_SUPPORTED"},
            {"claim": "Kundenkontakt", "support": "RELATED"},
        ],
    )
    assert prep.strengths
    assert prep.gaps
    assert any("SAP" in p for p in prep.talking_points)


def test_contact_preference_settings_defaults():
    cfg = empty_app_config()
    assert cfg.settings.preferred_contact == "email"
    assert cfg.settings.phone_available is True
    assert "09:00" in cfg.settings.telephone_availability
    assert cfg.settings.email_draft_only is True
    assert cfg.settings.allow_employer_email_send is False
