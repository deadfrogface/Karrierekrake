"""Isolated, opt-in fake mailbox for testing the actual lifecycle pipeline.

Run ``python -m desktop.app --fake-mail-demo`` (or the test EXE with the same
flag). Never opens an OAuth session, sends mail, or writes a real calendar.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path


DEMO_MESSAGES = (
    ("confirmation", "recruiting@nordlicht.example.test", "Eingangsbestätigung Ihrer Bewerbung", "Vielen Dank für Ihre Bewerbung als Sachbearbeiter Verwaltung. Wir haben Ihre Bewerbung erhalten."),
    ("interview", "hr@nordlicht.example.test", "Einladung zum Vorstellungsgespräch", "Nordlicht Beispiel GmbH lädt Sie zum Vorstellungsgespräch für Sachbearbeiter Verwaltung ein. Terminvorschlag: 06.10.2026 um 10:00 Uhr oder 07.10.2026 um 14:00 Uhr, Europe/Berlin."),
    ("rejection", "jobs@westufer.example.test", "Absage Ihrer Bewerbung", "Leider müssen wir Ihnen mitteilen, dass wir Ihre Bewerbung als Projektassistenz nicht berücksichtigen können."),
    ("noise", "offers@newsletter.example.test", "Newsletter: neue Stellen", "Aktuelle Stellenangebote. Unsubscribe here."),
    ("ambiguous", "jobs@nordlicht.example.test", "Rückfrage zu Ihrer Bewerbung", "Nordlicht Beispiel GmbH: Können Sie uns einen Rückruf anbieten?"),
)


def configure_isolation() -> Path:
    """Select a distinct profile before ConfigService and the GUI are imported."""
    root = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    demo_base = root / "Karrierekrake-FakeMailDemo"
    demo_base.mkdir(parents=True, exist_ok=True)
    os.environ["LOCALAPPDATA"] = str(demo_base)
    os.environ["KARRIEREKRAKE_ALLOW_FAKE_PROVIDERS"] = "1"
    os.environ["KARRIEREKRAKE_FAKE_MAIL_DEMO"] = "1"
    return demo_base


def seed_demo() -> list[dict]:
    """Seed through the same registry and case pipeline as live providers."""
    from core.case_pipeline import process_parsed_email
    from core.database import Database
    from core.lifecycle import ApplicationCase, CaseStatus
    from desktop.services import ConfigService
    from integrations.mail.contracts import NormalizedEmail
    from integrations.mail.registry import resolve_mail_adapter
    from integrations.providers.enums import MailProvider

    service = ConfigService()
    cfg = service.load()
    # Never grant mail sending to the demonstration profile.
    cfg.settings.allow_employer_email_send = False
    cfg.settings.email_draft_only = True
    if not cfg.application.first_name and not cfg.application.last_name:
        cfg.application.first_name = "Alex"
        cfg.application.last_name = "Beispiel"
    service.save(cfg)
    db = Database(cfg.db_path)
    cases = (
        ("demo-nordlicht-verwaltung", "Nordlicht Beispiel GmbH", "Sachbearbeiter Verwaltung", "hr@nordlicht.example.test"),
        ("demo-nordlicht-service", "Nordlicht Beispiel GmbH", "Kundenservice", "jobs@nordlicht.example.test"),
        ("demo-westufer", "Westufer Beispiel AG", "Projektassistenz", "jobs@westufer.example.test"),
    )
    for case_id, company, position, contact in cases:
        if db.get_case(case_id) is None:
            db.upsert_case(ApplicationCase(
                id=case_id, company=company, position=position,
                contact_email=contact, status=CaseStatus.APPLIED.value,
                source="fake_mail_demo", applied_at="2026-09-29T10:00:00Z",
            ))

    adapter = resolve_mail_adapter(MailProvider.FAKE_INPROCESS)
    adapter.seed([
        NormalizedEmail(
            provider=MailProvider.FAKE_INPROCESS,
            external_message_id=f"kk-demo-{kind}-v1",
            provider_message_id=f"kk-demo-{kind}-v1",
            subject=subject, sender=sender, body_text=body,
            internal_date=f"2026-09-30T10:0{index}:00Z",
        )
        for index, (kind, sender, subject, body) in enumerate(DEMO_MESSAGES)
    ])
    return [process_parsed_email(db, message.to_pipeline_payload()) for message in adapter.sync().messages]


def demo_freebusy():
    """Adapt the fake calendar registry to the scheduling engine's FreeBusy API."""
    from datetime import datetime

    from integrations.calendar.contracts import BusyInterval
    from integrations.calendar.registry import resolve_calendar_adapter
    from integrations.providers.enums import CalendarProvider

    adapter = resolve_calendar_adapter(CalendarProvider.FAKE_INPROCESS)
    adapter.seed_busy([
        BusyInterval(
            datetime.fromisoformat("2026-10-06T09:30:00+02:00"),
            datetime.fromisoformat("2026-10-06T11:30:00+02:00"),
        )
    ])

    class FakeCalendarFreeBusy:
        def query(self, query):
            return [item.to_time_window() for item in adapter.query_busy(query)]

    return FakeCalendarFreeBusy()


def inject_demo_message(*, sender: str, subject: str, body: str) -> dict:
    """User-created synthetic mail via fake registry → sync → lifecycle pipeline."""
    from core.case_pipeline import process_parsed_email
    from core.database import Database
    from desktop.services import ConfigService
    from integrations.mail.contracts import NormalizedEmail
    from integrations.mail.registry import resolve_mail_adapter
    from integrations.providers.enums import MailProvider

    if os.environ.get("KARRIEREKRAKE_FAKE_MAIL_DEMO") != "1":
        raise RuntimeError("synthetic_mail_requires_test_mode")
    if not sender.strip() or not subject.strip() or not body.strip():
        raise ValueError("sender, subject and body are required")
    adapter = resolve_mail_adapter(MailProvider.FAKE_INPROCESS)
    mid = f"kk-user-demo-{uuid.uuid4().hex}"
    adapter.seed([NormalizedEmail(
        provider=MailProvider.FAKE_INPROCESS,
        external_message_id=mid, provider_message_id=mid,
        sender=sender.strip(), subject=subject.strip(), body_text=body.strip(),
    )])
    db = Database(ConfigService().load().db_path)
    return process_parsed_email(db, adapter.sync().messages[0].to_pipeline_payload())


def launch() -> int:
    configure_isolation()
    seed_demo()
    from desktop.app import run

    return run()


def smoke_check(output: Path) -> int:
    """Packaged smoke without GUI: fake sync → classify/link → calendar → draft."""
    import json

    from core.database import Database
    from desktop.services import ConfigService
    from integrations.calendar_scheduling import propose_ranked_slots
    from integrations.reply_draft import ReplyAction, build_action_draft

    configure_isolation()
    seed_demo()
    db = Database(ConfigService().load().db_path)
    messages = db.list_inbox_emails()
    invite = next((m for m in messages if m["category"] == "interview"), None)
    slots = []
    draft_only = False
    if invite and invite.get("case_id"):
        proposal = propose_ranked_slots(
            invite["body_text"], case_id=invite["case_id"],
            freebusy=demo_freebusy(),
        )
        slots = [slot.start.isoformat() for slot in proposal.ranked_slots]
        case = db.get_case(invite["case_id"])
        draft = build_action_draft(
            ReplyAction.PROPOSE_SLOTS, case.to_dict(), proposed_slots=slots,
        )
        draft_only = draft.draft_only and not draft.sent and all(
            slot in draft.body for slot in slots
        )
    summary = {
        "kind": "FAKE_MAIL_DEMO_ONLY", "message_count": len(messages),
        "categories": sorted({m["category"] for m in messages}),
        "linked_interview": bool(invite and invite.get("case_id")),
        "available_slots": slots, "draft_only": draft_only,
        "isolated_db": "Karrierekrake-FakeMailDemo" in str(db.path),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if (
        len(messages) == len(DEMO_MESSAGES)
        and {"confirmation", "interview", "rejection"} <= set(summary["categories"])
        and summary["linked_interview"] and len(slots) == 1
        and draft_only and summary["isolated_db"]
    ) else 1
