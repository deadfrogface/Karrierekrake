"""T01.10: which reply draft an incoming mail gets (integrations.reply_draft.plan_mail_reply)."""
from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace as NS
from zoneinfo import ZoneInfo

import pytest

from integrations.calendar_write import interview_location
from integrations.proposal_parse import parse_scheduling_proposal
from integrations.reply_draft import (
    ALL_OFFERED_SLOTS_TAKEN,
    ReplyAction,
    SendGate,
    mail_reference,
    match_requested_documents,
    plan_mail_reply,
    requested_documents,
)

BERLIN = ZoneInfo("Europe/Berlin")
CASE = {
    "id": "case-1", "company": "Beispiel GmbH", "position": "Sachbearbeitung Einkauf",
    "contact_name": "Frau Dr. Erika Muster", "contact_email": "erika.muster@beispiel.example.org",
}


def mail(category: str, body: str = "", subject: str = "") -> dict:
    return {"category": category, "subject": subject, "body_text": body}


@pytest.mark.parametrize("category", ["confirmation", "under_review", "noise"])
def test_notifications_get_no_reply(category):
    assert plan_mail_reply(mail(category, "Kennziffer AB-123"), CASE) is None


def test_no_case_no_reply():
    assert plan_mail_reply(mail("rejection"), None) is None


def test_interview_accepts_exactly_the_rank_one_slot():
    slots = [NS(start=datetime(2026, 11, 3, 10, tzinfo=BERLIN)), NS(start=datetime(2026, 11, 4, 9, tzinfo=BERLIN))]
    draft = plan_mail_reply(mail("interview", "Kennziffer AB-123"), CASE, proposal=NS(ranked_slots=slots, stop_reason=""))
    assert draft.action == ReplyAction.PROPOSE_SLOTS.value
    assert "03.11.2026" in draft.body and "04.11.2026" not in draft.body
    assert "AB-123" in draft.body


def test_interview_with_all_slots_taken_asks_for_alternatives_without_reason():
    proposal = NS(ranked_slots=[], stop_reason=ALL_OFFERED_SLOTS_TAKEN)
    draft = plan_mail_reply(mail("interview"), CASE, proposal=proposal)
    assert draft.action == ReplyAction.REQUEST_ALTERNATIVES.value
    assert "alternative Termine" in draft.body
    assert "weil" not in draft.body and "da ich" not in draft.body


@pytest.mark.parametrize("stop", ["fail_safe:no_candidates", "fail_safe:ambiguous:time_window_without_weekdays"])
def test_unparsed_invitation_gets_no_draft(stop):
    assert plan_mail_reply(mail("interview"), CASE, proposal=NS(ranked_slots=[], stop_reason=stop)) is None
    assert plan_mail_reply(mail("interview"), CASE, proposal=None) is None


def test_rejection_is_a_short_thanks_without_follow_up():
    draft = plan_mail_reply(mail("rejection"), CASE)
    assert draft.body.startswith("Sehr geehrte Frau Dr. Muster,")
    assert "Rückmeldung" in draft.body
    for phrase in ("Rückfragen", "nächsten Schritte", "Gespräch"):
        assert phrase not in draft.body


def test_cancellation_is_acknowledged_without_own_dates():
    draft = plan_mail_reply(mail("interview_cancelled"), CASE)
    assert draft.action == ReplyAction.ACKNOWLEDGE_CANCELLATION.value
    assert "zur Kenntnis" in draft.body and "Termin vor" not in draft.body


DOC_REQUEST = """Guten Tag,

uns fehlen noch folgende Unterlagen (Kennziffer EK-2026-07):

  - Ihr aktuelles Zwischenzeugnis
  - das in Ihrem Lebenslauf genannte SAP-Zertifikat
  1) eine Kopie Ihres Staplerscheins

Viele Grüße
"""


def test_document_request_attaches_only_own_matching_files_and_names_missing_ones():
    draft = plan_mail_reply(
        mail("document_request", DOC_REQUEST), CASE,
        available_documents=["Lebenslauf.pdf", "Zwischenzeugnis_2025.pdf", "Zertifikat_Excel.pdf"],
    )
    assert draft.action == ReplyAction.DOCUMENT_REPLY.value
    assert draft.attachments == ["Zwischenzeugnis_2025.pdf"]
    assert "SAP-Zertifikat" in draft.body and "nicht vor" in draft.body
    assert "requested_documents_unavailable" in draft.blocking_reasons
    assert "EK-2026-07" in draft.body


def test_requested_documents_only_known_kinds():
    assert requested_documents(DOC_REQUEST) == [
        "Ihr aktuelles Zwischenzeugnis", "das in Ihrem Lebenslauf genannte SAP-Zertifikat",
    ]


def test_match_uses_head_noun_and_qualifier():
    attach, missing = match_requested_documents(
        ["das in Ihrem Lebenslauf genannte SQL-Zertifikat"], ["Lebenslauf.pdf", "SQL-Zertifikat_2024.pdf"]
    )
    assert attach == ["SQL-Zertifikat_2024.pdf"] and missing == []


@pytest.mark.parametrize(("subject", "body", "expected"), [
    ("Einladung (BW-DA-7731)", "Kennziffer BW-DA-7731.", "BW-DA-7731"),
    ("", "Position X, Referenz TM/26/118. Gern", "TM/26/118"),
    ("Ihre Bewerbung", "Ihr Zeichen: 2026-0412", "2026-0412"),
    ("", "Referenz folgt später", ""),
])
def test_mail_reference(subject, body, expected):
    assert mail_reference(subject, body) == expected


def test_send_gate_refuses_attachments_without_attachment_transport():
    draft = plan_mail_reply(mail("document_request", DOC_REQUEST), CASE, available_documents=["Zwischenzeugnis.pdf"])
    gate = SendGate(allow_send=True, draft_only=False)
    draft.draft_only = False
    gate.approve(draft)
    sent = []
    result = gate.attempt_send(draft, transport=sent.append)
    assert result.sent is False and result.send_error == "attachments_require_manual_send" and not sent


def test_interview_location_up_to_postcode_and_city():
    text = 'Ort: Beispiel GmbH, Hauptstraße 1, 2. OG,\n60311 Frankfurt am Main. Bitte am Empfang melden.\n'
    assert interview_location(text) == "Beispiel GmbH, Hauptstraße 1, 2. OG, 60311 Frankfurt am Main"
    assert interview_location("Kein Ort genannt.") == ""


def test_explicit_dated_slots_are_authoritative():
    text = ("Termine: Dienstag, 27.10.2026, 10:00-11:00 Uhr oder 02.11.2026 von 14:30 bis 15:15 Uhr. "
            "Bitte bis Freitag, 23.10.2026, antworten.")
    parsed = parse_scheduling_proposal(text, reference=datetime(2026, 10, 18, 9, tzinfo=BERLIN))
    assert [(s.strftime("%d.%m. %H:%M"), e.strftime("%H:%M")) for s, e in parsed.explicit_slots] == [
        ("27.10. 10:00", "11:00"), ("02.11. 14:30", "15:15"),
    ]
    assert parsed.windows == [] and parsed.ok
