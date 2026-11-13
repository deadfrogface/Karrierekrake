"""Where an application really stands, and what proves it.

A step is "done" only with evidence: an event the person confirmed, or the employer's own mail. A "sent" that only
the program itself recorded stays "uncertain" until a receipt shows up, so the screen never reports a success it
cannot back.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from desktop.i18n import de_en

DONE, UNCERTAIN, OPEN, FAILED = "done", "uncertain", "open", "failed"

_USER_SOURCES = {"manual", "user", "ui", "desktop", "manual_override", "person"}
_REPLY_TYPES = {
    "UNDER_REVIEW": ("In Prüfung", "Under review"),
    "DOCUMENT_REQUESTED": ("Unterlagen angefordert", "Documents requested"),
    "ASSESSMENT_RECEIVED": ("Aufgabe erhalten", "Assessment received"),
    "INTERVIEW_REQUESTED": ("Einladung zum Gespräch", "Interview invitation"),
    "INTERVIEW_SCHEDULED": ("Gespräch vereinbart", "Interview scheduled"),
    "INTERVIEW_COMPLETED": ("Gespräch geführt", "Interview held"),
}


@dataclass(frozen=True)
class RailStep:
    key: str
    label: str
    state: str
    evidence: str = ""


def _day(value: str) -> str:
    text = (value or "")[:10]
    if len(text) == 10 and text[4] == "-" and text[7] == "-":
        return f"{text[8:10]}.{text[5:7]}.{text[0:4]}"
    return text


def _is_user(source: str) -> bool:
    low = (source or "").lower()
    return low in _USER_SOURCES or low.startswith("user")


def _how(source: str) -> str:
    low = (source or "").lower()
    if _is_user(low):
        return de_en("von dir bestätigt", "confirmed by you")
    if "mail" in low or "imap" in low or "gmail" in low:
        return de_en("per E-Mail belegt", "proven by e-mail")
    if low in {"", "unknown"}:
        return de_en("ohne Quelle", "no source")
    return de_en("vom Programm erfasst", "recorded by the program")


def _first(events: Sequence, types: Iterable[str]):
    wanted = set(types)
    matches = [e for e in events if (e.event_type or "").strip() in wanted]
    return min(matches, key=lambda e: e.occurred_at or e.recorded_at or "") if matches else None


def build_evidence_rail(events: Sequence, *, application_status: str = "") -> list[RailStep]:
    status = (application_status or "").lower()
    created = _first(events, ["APPLICATION_CREATED"])
    sent_events = [e for e in events if (e.event_type or "").strip() == "APPLICATION_SENT"]
    # your own statement outranks a program-written or seeded "sent" event, whatever the order
    sent = next((e for e in sent_events if _is_user(e.source)), None) or _first(events, ["APPLICATION_SENT"])
    received = _first(events, ["APPLICATION_RECEIVED"])
    reply = _first(events, list(_REPLY_TYPES))
    offer = _first(events, ["OFFER_RECEIVED"])
    rejection = _first(events, ["REJECTION_RECEIVED"])
    ended = _first(events, ["WITHDRAWN", "GHOSTED", "ARCHIVED"])

    draft = RailStep("draft", de_en("Entwurf", "Draft"), DONE if (created or events or status) else OPEN,
                     f"{_day(created.occurred_at)} · {_how(created.source)}" if created else "")

    sent_label = de_en("Gesendet", "Sent")
    receipt_label = de_en("Eingang bestätigt", "Receipt confirmed")
    if received:
        sent_step = RailStep("sent", sent_label, DONE, de_en("Durch den Eingang beim Arbeitgeber belegt", "Proven by the employer's receipt"))
    elif sent and _is_user(sent.source):
        sent_step = RailStep("sent", sent_label, DONE, f"{_day(sent.occurred_at)} · {_how(sent.source)}")
    elif sent or status in {"applied", "confirmation"}:
        sent_step = RailStep("sent", sent_label, UNCERTAIN,
                             de_en("Kein Beleg. Warte auf die Eingangsbestätigung oder bestätige selbst.",
                                   "No proof. Wait for the receipt or confirm it yourself."))
    else:
        sent_step = RailStep("sent", sent_label, OPEN)

    receipt = (RailStep("receipt", receipt_label, DONE, f"{_day(received.occurred_at)} · {_how(received.source)}")
               if received else RailStep("receipt", receipt_label, OPEN))

    answer = (RailStep("reply", de_en(*_REPLY_TYPES[reply.event_type]), DONE, f"{_day(reply.occurred_at)} · {_how(reply.source)}")
              if reply else RailStep("reply", de_en("Antwort", "Reply"), OPEN))

    if offer:
        outcome = RailStep("outcome", de_en("Angebot", "Offer"), DONE, f"{_day(offer.occurred_at)} · {_how(offer.source)}")
    elif rejection:
        outcome = RailStep("outcome", de_en("Absage", "Rejection"), FAILED, f"{_day(rejection.occurred_at)} · {_how(rejection.source)}")
    elif ended:
        label = de_en(*{"WITHDRAWN": ("Zurückgezogen", "Withdrawn"), "GHOSTED": ("Keine Antwort", "No reply"),
                        "ARCHIVED": ("Archiviert", "Archived")}.get(ended.event_type, ("Beendet", "Ended")))
        outcome = RailStep("outcome", label, FAILED if ended.event_type == "GHOSTED" else DONE,
                           f"{_day(ended.occurred_at)} · {_how(ended.source)}")
    else:
        outcome = RailStep("outcome", de_en("Ergebnis", "Outcome"), OPEN)
    return [draft, sent_step, receipt, answer, outcome]
