"""Synthetic recruiting mail helpers for product E2E journeys."""

from __future__ import annotations

from typing import Any

from tests.lifecycle_e2e.loader import load_injection_mails, load_recruiting_mails


def parsed_mail(
    *,
    gmail_id: str,
    sender: str,
    subject: str,
    body: str,
    thread_id: str | None = None,
) -> dict[str, Any]:
    return {
        "gmail_id": gmail_id,
        "thread_id": thread_id or f"t-{gmail_id}",
        "sender": sender,
        "subject": subject,
        "body_text": body,
        "received_at": "2026-09-20T12:00:00+00:00",
    }


# Stable journey mails (RFC6761 *.example only).
MAIL_CONFIRMATION = parsed_mail(
    gmail_id="EMAIL_001",
    sender="HR Nordlicht <hr@nordlicht.example.com>",
    subject="Eingangsbestätigung Ihrer Bewerbung",
    body=(
        "Guten Tag,\n\nIhre Bewerbung als Lohnbuchhalter ist bei Nordlicht Beispiel "
        "GmbH eingegangen. Wir melden uns in Kürze.\n\nMit freundlichen Grüßen\nHR"
    ),
)

MAIL_REVIEW = parsed_mail(
    gmail_id="EMAIL_002",
    sender="HR Nordlicht <hr@nordlicht.example.com>",
    subject="Ihre Bewerbung wird geprüft",
    body="Wir prüfen derzeit Ihre Unterlagen für die Stelle Lohnbuchhalter.",
    thread_id="t-EMAIL_001",
)

MAIL_INTERVIEW = parsed_mail(
    gmail_id="EMAIL_003",
    sender="HR Nordlicht <hr@nordlicht.example.com>",
    subject="Einladung zum Vorstellungsgespräch",
    body=(
        "Wir laden Sie herzlich zum Vorstellungsgespräch ein.\n"
        "Vorschlag: Dienstag 10:00 Uhr oder Mittwoch 14:00 Uhr (Europe/Berlin), Zoom.\n"
        "Bitte bestätigen Sie einen Termin."
    ),
    thread_id="t-EMAIL_001",
)

MAIL_RESCHEDULE = parsed_mail(
    gmail_id="EMAIL_004",
    sender="HR Nordlicht <hr@nordlicht.example.com>",
    subject="Terminverschiebung Vorstellungsgespräch",
    body=(
        "Leider müssen wir den Termin verschieben. "
        "Neuer Vorschlag: Donnerstag 11:00 Uhr Europe/Berlin."
    ),
    thread_id="t-EMAIL_001",
)

MAIL_FOLLOWUP = parsed_mail(
    gmail_id="EMAIL_005",
    sender="HR Nordlicht <hr@nordlicht.example.com>",
    subject="Nachfrage nach unserem Gespräch",
    body="Haben Sie noch Fragen zum Prozess? Wir freuen uns auf Ihre Rückmeldung.",
    thread_id="t-EMAIL_001",
)

MAIL_OFFER = parsed_mail(
    gmail_id="EMAIL_006",
    sender="HR Nordlicht <hr@nordlicht.example.com>",
    subject="Angebot — Lohnbuchhalter",
    body=(
        "Wir freuen uns, Ihnen ein Angebot für die Position Lohnbuchhalter "
        "unterbreiten zu dürfen. Details im Anhang."
    ),
    thread_id="t-EMAIL_001",
)

MAIL_REJECTION = parsed_mail(
    gmail_id="EMAIL_010",
    sender="HR Nordlicht <hr@nordlicht.example.com>",
    subject="Rückmeldung zu Ihrer Bewerbung",
    body="Leider müssen wir Ihnen absagen. Wir wünschen Ihnen viel Erfolg.",
    thread_id="t-EMAIL_001",
)

MAIL_AMBIGUOUS_COMPANY = parsed_mail(
    gmail_id="EMAIL_020",
    sender="Recruiter <talent@multirole.example.com>",
    subject="Ihre Bewerbung bei Multi Role AG",
    body=(
        "Vielen Dank für Ihre Bewerbung bei Multi Role AG. "
        "Wir melden uns in Kürze. (keine Rollenangabe)"
    ),
)

MAIL_QUOTED_OLD_REJECTION = parsed_mail(
    gmail_id="EMAIL_030",
    sender="HR Nordlicht <hr@nordlicht.example.com>",
    subject="Einladung zum Gespräch — neue Rolle",
    body=(
        "Wir laden Sie zum Interview für Office Manager ein.\n\n"
        "--- Weitergeleitete Nachricht ---\n"
        "Betreff: Absage\nLeider müssen wir Ihnen absagen.\n"
    ),
)


def load_mail_volume(min_count: int = 150) -> list[dict[str, Any]]:
    """At least 150 synthetic mails from lifecycle corpora."""
    rows = list(load_recruiting_mails()) + list(load_injection_mails())
    assert len(rows) >= min_count
    return rows
