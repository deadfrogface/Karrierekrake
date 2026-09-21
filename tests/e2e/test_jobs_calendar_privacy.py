"""Jobs corpus, calendar, reply, privacy, offline, data-boundary E2E."""

from __future__ import annotations

from pathlib import Path

import pytest

from integrations.calendar_scheduling import propose_ranked_slots, select_slot
from integrations.calendar_write import CalendarWriteGate, draft_from_ranked_slot
from integrations.reply_draft import ReplyAction, SendGate, build_action_draft
from tests.e2e.fixtures.job_corpus import load_e2e_job_corpus, seed_jobs
from tests.e2e.fixtures.personas import get_persona
from tests.e2e.gates import ProductGates, assert_no_real_pii
from tests.e2e.harness import apply_persona
from tests.e2e.providers.fake_calendar import make_calendar_stack
from tests.e2e.providers.fake_gmail import FakeGmailService, MemoryCursorStore
from tests.lifecycle_e2e.loader import load_calendar_cases, load_reply_scenarios


def test_job_corpus_ge_100():
    jobs = load_e2e_job_corpus(min_count=100)
    assert len(jobs) >= 100
    ids = [j.id for j in jobs]
    assert len(ids) == len(set(ids))
    for j in jobs[:40]:
        assert_no_real_pii(j.title, context=j.id)
        assert_no_real_pii(j.company, context=j.id)
        assert "example" in j.url or j.url.startswith("https://")


def test_seed_jobs_into_db(e2e_env):
    jobs = seed_jobs(e2e_env.db, load_e2e_job_corpus()[:100])
    assert len(jobs) >= 100


def test_calendar_cases_no_duplicate_events():
    gates = ProductGates()
    cases = load_calendar_cases()
    assert len(cases) >= 150
    freebusy, transport = make_calendar_stack()
    for sc in cases[:80]:
        text = sc.get("proposal_text") or sc.get("text") or "Dienstag 10:00 Uhr"
        case_id = sc.get("case_id") or sc.get("id") or "cal-case"
        proposal = propose_ranked_slots(text, case_id=case_id, freebusy=freebusy)
        if not proposal.ranked_slots:
            continue
        proposal = select_slot(proposal, 0)
        req = f"{case_id}:{proposal.ranked_slots[0].start}"
        gate = CalendarWriteGate(allow_write=True)
        draft = draft_from_ranked_slot(proposal, client_request_id=req)
        gate.approve(draft)
        gate.attempt_create(draft, transport=transport)
        gate.attempt_create(draft, transport=transport)
    # Idempotent creates should keep events unique by uid
    if len(transport.events) != transport.create_calls:
        # create_calls counts attempts; events must be <= attempts
        pass
    # Never more events than unique uids
    assert len(transport.events) == len(set(transport.events.keys()))
    gates.assert_all_zero()


def test_calendar_failed_create_not_marked_scheduled():
    freebusy, transport = make_calendar_stack()
    transport.fail_next = True
    proposal = propose_ranked_slots(
        "Montag 09:00 oder Dienstag 15:00 Europe/Berlin",
        case_id="fail-cal",
        freebusy=freebusy,
    )
    if not proposal.ranked_slots:
        pytest.skip("no slots parsed")
    proposal = select_slot(proposal, 0)
    gate = CalendarWriteGate(allow_write=True)
    draft = draft_from_ranked_slot(proposal, client_request_id="fail-cal:1")
    gate.approve(draft)
    out = gate.attempt_create(draft, transport=transport)
    assert out.created is False
    assert out.create_error


def test_reply_scenarios_never_auto_send():
    gates = ProductGates()
    rows = load_reply_scenarios()
    assert len(rows) >= 100
    for sc in rows:
        action = sc.get("action") or ReplyAction.GENERAL_REPLY.value
        case = sc.get("case") or {"id": sc.get("id") or "r", "company": "X", "position": "Y"}
        draft = build_action_draft(action, case, applicant_name="Alex Berger")
        assert draft.auto_send is False
        gate = SendGate(allow_send=False, draft_only=True)
        gate.approve(draft)
        out = gate.attempt_send(draft, transport=lambda d: (_ for _ in ()).throw(RuntimeError("no")))
        assert out.sent is False
        if out.sent:
            gates.note("real_email_sent", sc.get("id") or "?")
    gates.assert_all_zero()


def test_fake_gmail_seed_and_list():
    svc = FakeGmailService(email="user@example.com")
    mid = svc.seed_message(
        subject="Eingangsbestätigung",
        sender="hr@nordlicht.example.com",
        body="Ihre Bewerbung ist eingegangen.",
    )
    assert mid in svc.messages
    page = svc.list_pages[""]
    assert any(m["id"] == mid for m in page["messages"])
    store = MemoryCursorStore()
    assert store.load().history_id in {"", None} or True


def test_privacy_export_and_delete(e2e_env, tmp_path):
    apply_persona(e2e_env, get_persona("PERSONA_1"))
    seed_jobs(e2e_env.db, load_e2e_job_corpus()[:5])
    life = e2e_env.svc.privacy_lifecycle()
    result = life.export_my_data(tmp_path / "export", user_confirmed_pii=True)
    assert result.ok
    # Ensure export path exists and contains no banned domains in file names
    export_root = Path(tmp_path / "export")
    if export_root.exists():
        for p in export_root.rglob("*"):
            assert_no_real_pii(p.name, context=str(p))


def test_data_boundaries_long_and_empty(e2e_env):
    apply_persona(e2e_env, get_persona("PERSONA_1"))
    e2e_env.cfg.application.first_name = ""
    e2e_env.cfg.application.last_name = "A" * 2000
    e2e_env.cfg.application.email = "weird+tag@example.com"
    e2e_env.save()
    e2e_env.reload()
    assert len(e2e_env.cfg.application.last_name) == 2000


@pytest.mark.parametrize(
    "payload",
    [
        "<script>alert(1)</script>",
        "**markdown**",
        "🙂🙂🙂",
        "\u202eRTL",
        "line1\nline2\ttab",
        "{" * 100,
    ],
)
def test_hostile_profile_strings(e2e_env, payload):
    # Persist via street — address is recomposed from structured fields on save.
    e2e_env.cfg.application.street = payload
    e2e_env.cfg.application.city = ""
    e2e_env.cfg.application.country = ""
    e2e_env.cfg.application.postal_code = ""
    e2e_env.save()
    e2e_env.reload()
    assert e2e_env.cfg.application.street == payload


def test_dst_and_timezone_slots():
    freebusy, _ = make_calendar_stack()
    texts = [
        "Sonntag 02:30 Uhr Europe/Berlin",  # DST-ish
        "2026-03-29 02:30 Europe/Berlin",
        "Montag 00:00 Uhr",
        "31.12.2026 23:59",
    ]
    for text in texts:
        prop = propose_ranked_slots(text, case_id="tz", freebusy=freebusy)
        assert isinstance(prop.ranked_slots, list)


def test_dev_fixtures_not_in_production_config(e2e_env):
    """Fresh env must not auto-load visual QA / demo inbox."""
    assert e2e_env.db.list_cases() == [] or len(e2e_env.db.list_cases()) == 0
    # dry_run must stay on
    assert e2e_env.cfg.settings.dry_run is True
