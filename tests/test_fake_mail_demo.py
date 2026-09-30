"""The opt-in demo goes through provider sync and the real lifecycle pipeline."""

from __future__ import annotations

from core.database import Database
from desktop.fake_mail_demo import configure_isolation, demo_freebusy, inject_demo_message, seed_demo
from desktop.services import ConfigService
from integrations.calendar_scheduling import propose_ranked_slots
from integrations.reply_draft import ReplyAction, SendGate, build_action_draft
from integrations.mail.registry import resolve_mail_adapter
from integrations.calendar.registry import resolve_calendar_adapter
from integrations.providers.enums import ProviderError
import pytest


def test_demo_is_isolated_idempotent_and_draft_only(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    base = configure_isolation()
    assert base == tmp_path / "Karrierekrake-FakeMailDemo"
    first = seed_demo()
    second = seed_demo()
    db = Database(ConfigService().load().db_path)
    emails = db.list_inbox_emails()
    assert len(first) == len(second) == len(emails) == 5
    assert all(item["status"] == "duplicate" for item in second)
    assert {e["category"] for e in emails} >= {"confirmation", "interview", "rejection"}
    assert not ConfigService().load().settings.allow_employer_email_send
    assert "Karrierekrake-FakeMailDemo" in str(db.path)
    with pytest.raises(ProviderError, match="real_provider_forbidden_in_fake_demo"):
        resolve_mail_adapter("google_gmail")
    with pytest.raises(ProviderError, match="real_provider_forbidden_in_fake_demo"):
        resolve_calendar_adapter("google_calendar")

    interview = next(e for e in emails if e["category"] == "interview")
    assert interview["case_id"]
    case = db.get_case(interview["case_id"])
    proposal = propose_ranked_slots(
        interview["body_text"], case_id=case.id, freebusy=demo_freebusy()
    )
    assert len(proposal.ranked_slots) == 1
    assert proposal.ranked_slots[0].start.day == 7
    # Only explicit slots may enter a reply draft; an unparseable invite must stop.
    if proposal.ranked_slots:
        slots = [s.start.isoformat() for s in proposal.ranked_slots]
        draft = build_action_draft(ReplyAction.PROPOSE_SLOTS, case.to_dict(), proposed_slots=slots)
        assert any(slot in draft.body for slot in slots)
    else:
        draft = build_action_draft(ReplyAction.PROPOSE_SLOTS, case.to_dict())
        assert "unverified_slots" in draft.blocking_reasons
    assert draft.draft_only
    assert not SendGate(allow_send=False).attempt_send(draft, transport=lambda _: 1).sent


def test_demo_inbox_ui_shows_sorted_invite_slot_and_reply(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    configure_isolation()
    seed_demo()

    from PySide6.QtWidgets import QApplication
    from desktop.pages.inbox import InboxPage

    app = QApplication.instance() or QApplication([])
    page = InboxPage(ConfigService())
    page.refresh()
    assert page.list.count() == 5
    assert page.account_chip.text() == "FAKE-POSTFACH · TEST"
    index = next(i for i, mail in enumerate(page._emails) if mail["category"] == "interview")
    page.list.setCurrentRow(index)
    page._action_calendar()
    summary = page.lifecycle._pending_calendar["summary"]
    assert "2026-10-07T14:00:00" in summary
    assert "2026-10-06T10:00:00" not in summary
    page._action_draft()
    draft = page.lifecycle._pending_draft
    assert draft.draft_only and not draft.sent
    assert "2026-10-07T14:00:00" in draft.body
    assert "2026-10-06T10:00:00" not in draft.body
    assert not page.add_test_mail_btn.isHidden()
    injected = inject_demo_message(
        sender="recruiting@new.example.test", subject="Absage Ihrer Bewerbung",
        body="Leider müssen wir Ihnen mitteilen, dass wir Ihre Bewerbung nicht berücksichtigen können.",
    )
    assert injected["category"] == "rejection"
    page.refresh()
    assert page.list.count() == 6
    page.close()
    assert app is not None
