"""Where an application really stands, and what proves it.

A step is "done" only with evidence: an event the person confirmed, or the employer's own mail. A "sent" that only
the program itself recorded stays "uncertain" until a receipt shows up, so the screen never reports a success it
cannot back.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

DONE, UNCERTAIN, OPEN, FAILED = "done", "uncertain", "open", "failed"

_USER_SOURCES = {"manual", "user", "ui", "desktop", "manual_override", "person"}
_REPLY_TYPES = {
    "UNDER_REVIEW": "In Prüfung",
    "DOCUMENT_REQUESTED": "Unterlagen angefordert",
    "ASSESSMENT_RECEIVED": "Aufgabe erhalten",
    "INTERVIEW_REQUESTED": "Einladung zum Gespräch",
    "INTERVIEW_SCHEDULED": "Gespräch vereinbart",
    "INTERVIEW_COMPLETED": "Gespräch geführt",
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
        return "von dir bestätigt"
    if "mail" in low or "imap" in low or "gmail" in low:
        return "per E-Mail belegt"
    if low in {"", "unknown"}:
        return "ohne Quelle"
    return "vom Programm erfasst"


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

    draft = RailStep("draft", "Entwurf", DONE if (created or events or status) else OPEN,
                     f"{_day(created.occurred_at)} · {_how(created.source)}" if created else "")

    if received:
        sent_step = RailStep("sent", "Gesendet", DONE, "Durch den Eingang beim Arbeitgeber belegt")
    elif sent and _is_user(sent.source):
        sent_step = RailStep("sent", "Gesendet", DONE, f"{_day(sent.occurred_at)} · von dir bestätigt")
    elif sent or status in {"applied", "confirmation"}:
        sent_step = RailStep("sent", "Gesendet", UNCERTAIN,
                             "Kein Beleg. Warte auf die Eingangsbestätigung oder bestätige selbst.")
    else:
        sent_step = RailStep("sent", "Gesendet", OPEN)

    receipt = (RailStep("receipt", "Eingang bestätigt", DONE, f"{_day(received.occurred_at)} · {_how(received.source)}")
               if received else RailStep("receipt", "Eingang bestätigt", OPEN))

    answer = (RailStep("reply", _REPLY_TYPES[reply.event_type], DONE, f"{_day(reply.occurred_at)} · {_how(reply.source)}")
              if reply else RailStep("reply", "Antwort", OPEN))

    if offer:
        outcome = RailStep("outcome", "Angebot", DONE, f"{_day(offer.occurred_at)} · {_how(offer.source)}")
    elif rejection:
        outcome = RailStep("outcome", "Absage", FAILED, f"{_day(rejection.occurred_at)} · {_how(rejection.source)}")
    elif ended:
        label = {"WITHDRAWN": "Zurückgezogen", "GHOSTED": "Keine Antwort", "ARCHIVED": "Archiviert"}.get(
            ended.event_type, "Beendet")
        outcome = RailStep("outcome", label, FAILED if ended.event_type == "GHOSTED" else DONE,
                           f"{_day(ended.occurred_at)} · {_how(ended.source)}")
    else:
        outcome = RailStep("outcome", "Ergebnis", OPEN)
    return [draft, sent_step, receipt, answer, outcome]
