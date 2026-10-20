"""Action-specific employer reply drafts — draft-only by default.

PR32: free-form mail generation is replaced by typed ReplyAction contracts.
Only verified company / job / contact / date facts may appear in the body.
DEFAULT: DRAFT ONLY — never auto-send. Binding actions (WITHDRAW, DECLINE_OFFER)
require an extra explicit review flag before any send attempt.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Sequence

from core.models import utc_now_iso


class ReplyAction(str, Enum):
    CONFIRM_INTERVIEW = "CONFIRM_INTERVIEW"
    PROPOSE_SLOTS = "PROPOSE_SLOTS"
    RESCHEDULE = "RESCHEDULE"
    DOCUMENT_REPLY = "DOCUMENT_REPLY"
    THANK_YOU = "THANK_YOU"
    FOLLOWUP = "FOLLOWUP"
    WITHDRAW = "WITHDRAW"
    DECLINE_OFFER = "DECLINE_OFFER"
    GENERAL_REPLY = "GENERAL_REPLY"
    REQUEST_ALTERNATIVES = "REQUEST_ALTERNATIVES"
    ACKNOWLEDGE_REJECTION = "ACKNOWLEDGE_REJECTION"
    ACKNOWLEDGE_CANCELLATION = "ACKNOWLEDGE_CANCELLATION"


BINDING_ACTIONS: frozenset[str] = frozenset(
    {
        ReplyAction.WITHDRAW.value,
        ReplyAction.DECLINE_OFFER.value,
    }
)

DATE_SENSITIVE_ACTIONS: frozenset[str] = frozenset(
    {
        ReplyAction.CONFIRM_INTERVIEW.value,
        ReplyAction.PROPOSE_SLOTS.value,
        ReplyAction.RESCHEDULE.value,
    }
)


@dataclass(frozen=True)
class VerifiedFacts:
    """Facts allowed in a draft. Unverified fields stay empty and must not leak."""

    case_id: str = ""
    company: str = ""
    position: str = ""
    contact_name: str = ""
    contact_email: str = ""
    interview_when: str = ""
    proposed_slots: tuple[str, ...] = ()
    documents: tuple[str, ...] = ()
    applicant_name: str = ""
    phone: str = ""
    # Employer reference number as written in the mail being answered.
    reference: str = ""
    # Requested documents the applicant does not have (named, never attached).
    missing_documents: tuple[str, ...] = ()

    @staticmethod
    def _flag(case: dict[str, Any], key: str) -> bool:
        explicit = case.get(f"{key}_verified")
        if explicit is not None:
            return bool(explicit)
        verified = case.get("verified")
        if isinstance(verified, dict) and key in verified:
            return bool(verified.get(key))
        # Legacy cases without flags: treat non-empty persisted case fields as
        # case-store verified (ApplicationCase row), never invent from LLM.
        return bool((case.get(key) or "").strip()) if key in case else False

    @classmethod
    def from_case(
        cls,
        case: dict[str, Any],
        *,
        applicant_name: str = "",
        phone: str = "",
        proposed_slots: Sequence[str] | None = None,
        documents: Sequence[str] | None = None,
        interview_when: str = "",
        reference: str = "",
        missing_documents: Sequence[str] = (),
    ) -> "VerifiedFacts":
        case = case or {}
        case_id = str(case.get("id") or "").strip()

        company = (case.get("company") or "").strip() if cls._flag(case, "company") else ""
        position_raw = case.get("position") or case.get("title") or ""
        position_ok = cls._flag(case, "position") or cls._flag(case, "title")
        position = position_raw.strip() if position_ok else ""

        contact_name = (
            (case.get("contact_name") or "").strip()
            if cls._flag(case, "contact_name")
            else ""
        )
        contact_email = (
            (case.get("contact_email") or "").strip()
            if cls._flag(case, "contact_email")
            else ""
        )

        # Explicit kwargs are trusted only when the case does not mark the
        # field as unverified (False). Missing flag + non-empty kwarg = ok.
        if "interview_when_verified" in case and case.get("interview_when_verified") is False:
            when = ""
        else:
            when = (interview_when or case.get("interview_when") or "").strip()
            when_ok = bool(interview_when) or cls._flag(case, "interview_when")
            if not when_ok:
                when = ""

        slots_src = proposed_slots
        if slots_src is None:
            slots_src = case.get("proposed_slots") or case.get("verified_slots") or []
        slots: list[str] = []
        for s in slots_src or []:
            text = str(s or "").strip()
            if text:
                slots.append(text)

        docs_src = documents
        if docs_src is None:
            docs_src = case.get("documents") or case.get("documents_requested") or []
        docs = [str(d).strip() for d in (docs_src or []) if str(d).strip()]

        if phone:
            phone_val = phone.strip()
        elif case.get("phone") and cls._flag(case, "phone"):
            phone_val = (case.get("phone") or "").strip()
        else:
            phone_val = ""

        return cls(
            case_id=case_id,
            company=company,
            position=position,
            contact_name=contact_name,
            contact_email=contact_email,
            interview_when=when,
            proposed_slots=tuple(slots),
            documents=tuple(docs),
            applicant_name=(applicant_name or "").strip(),
            phone=phone_val,
            reference=(reference or "").strip(),
            missing_documents=tuple(d.strip() for d in missing_documents if d and d.strip()),
        )


@dataclass
class ReplyDraft:
    case_id: str
    action: str
    to_address: str
    subject: str
    body: str
    created_at: str = field(default_factory=utc_now_iso)
    approved: bool = False
    binding_review_approved: bool = False
    sent: bool = False
    send_error: str = ""
    draft_only: bool = True
    auto_send: bool = False  # product invariant — always False
    requires_explicit_review: bool = False
    blocking_reasons: list[str] = field(default_factory=list)
    used_facts: list[str] = field(default_factory=list)
    # File names of the applicant's own documents to attach (never invented).
    attachments: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.auto_send = False
        if self.action in BINDING_ACTIONS:
            self.requires_explicit_review = True


# Explicit form of address as written in the contact name ("Frau Helene
# Brinkmann", "Herr Dr. Jonas Feldkamp", "Hr. Feldkamp"). Never inferred from a
# first name: without an explicit Frau/Herr the greeting stays neutral.
_FORM_OF_ADDRESS = {"frau": "Frau", "fr": "Frau", "herr": "Herr", "hr": "Herr"}
_ACADEMIC_TITLES = {"dr": "Dr.", "prof": "Prof."}
# Lower-case name particles start a multi-word surname ("von der Heide").
_SURNAME_PARTICLES = frozenset(
    {"von", "van", "vom", "zu", "zum", "zur", "der", "den", "de", "del", "della", "di", "da", "du", "la", "le", "ter", "ten"}
)


def _formal_salutation(contact_name: str) -> str:
    """'Sehr geehrte Frau <Titel> <Nachname>,' / 'Sehr geehrter Herr …,' or ''.

    Only when the contact name itself starts with an explicit form of address
    (Frau/Herr, Fr./Hr.). The first name never appears in a formal greeting.
    Returns '' when the form of address is unknown or no surname is left.
    """
    tokens = contact_name.replace(",", " ").split()
    if not tokens:
        return ""
    form = _FORM_OF_ADDRESS.get(tokens[0].casefold().rstrip("."))
    if form is None:
        return ""
    titles: list[str] = []
    rest = tokens[1:]
    while rest and rest[0].casefold().rstrip(".") in _ACADEMIC_TITLES:
        titles.append(_ACADEMIC_TITLES[rest[0].casefold().rstrip(".")])
        rest = rest[1:]
    names = [t.strip(".;:") for t in rest if t.strip(".;:")]
    if not names:
        return ""
    start = len(names) - 1  # default: last token is the surname
    for i, token in enumerate(names[1:], start=1):
        if token in _SURNAME_PARTICLES:  # case-sensitive: particles are lower-case
            start = i
            break
    surname = " ".join(names[start:]) if len(names) > 1 else names[0]
    core = " ".join([*titles, surname])
    lead = "Sehr geehrter" if form == "Herr" else "Sehr geehrte"
    return f"{lead} {form} {core},"


def _greeting(facts: VerifiedFacts) -> str:
    """Formal greeting when the form of address is explicit, else neutral.

    Gold rule (T01.10, Personaler 5cd3a994): known form of address ->
    'Sehr geehrte Frau Brinkmann,' / 'Sehr geehrter Herr Feldkamp,'; unknown
    (name without Frau/Herr) -> 'Guten Tag <Name wie geschrieben>,'; no
    contact -> 'Guten Tag,'.
    """
    name = facts.contact_name
    if not name:
        return "Guten Tag,"
    formal = _formal_salutation(name)
    if formal:
        return formal
    if _FORM_OF_ADDRESS.get(name.split()[0].casefold().rstrip(".")) is not None:
        return "Guten Tag,"  # form of address without any name left
    return f"Guten Tag {name},"


def _signoff(facts: VerifiedFacts) -> str:
    name = facts.applicant_name or "…"
    return f"Mit freundlichen Grüßen\n{name}\n"


def _role_line(facts: VerifiedFacts) -> str:
    parts: list[str] = []
    if facts.position:
        parts.append(f"als {facts.position}")
    if facts.company:
        parts.append(f"bei {facts.company}")
    if facts.reference:
        parts.append(f"(Kennziffer {facts.reference})")
    return " ".join(parts)


def _missing_core(facts: VerifiedFacts) -> list[str]:
    reasons: list[str] = []
    if not facts.case_id:
        reasons.append("missing_case_id")
    if not facts.company:
        reasons.append("unverified_company")
    if not facts.position:
        reasons.append("unverified_position")
    return reasons


def _base_draft(
    *,
    action: ReplyAction,
    facts: VerifiedFacts,
    subject: str,
    body: str,
    used: Iterable[str],
    blocking: Iterable[str] = (),
) -> ReplyDraft:
    return ReplyDraft(
        case_id=facts.case_id,
        action=action.value,
        to_address=facts.contact_email,
        subject=subject,
        body=body,
        draft_only=True,
        approved=False,
        sent=False,
        auto_send=False,
        requires_explicit_review=action.value in BINDING_ACTIONS,
        blocking_reasons=list(blocking),
        used_facts=list(used),
    )


def build_action_draft(
    action: ReplyAction | str,
    case: dict[str, Any],
    *,
    applicant_name: str = "",
    phone: str = "",
    offer_phone: bool = False,
    proposed_slots: Sequence[str] | None = None,
    documents: Sequence[str] | None = None,
    interview_when: str = "",
    general_note: str = "",
    reference: str = "",
    missing_documents: Sequence[str] = (),
) -> ReplyDraft:
    """Build a typed, draft-only reply. Never sends."""
    if isinstance(action, str):
        try:
            action = ReplyAction(action)
        except ValueError:
            facts = VerifiedFacts.from_case(case, applicant_name=applicant_name)
            return _base_draft(
                action=ReplyAction.GENERAL_REPLY,
                facts=facts,
                subject="Antwort zur Bewerbung",
                body="",
                used=[],
                blocking=["unknown_action"],
            )

    facts = VerifiedFacts.from_case(
        case,
        applicant_name=applicant_name,
        phone=phone,
        proposed_slots=proposed_slots,
        documents=documents,
        interview_when=interview_when,
        reference=reference,
        missing_documents=missing_documents,
    )
    builders = {
        ReplyAction.CONFIRM_INTERVIEW: _build_confirm_interview,
        ReplyAction.PROPOSE_SLOTS: _build_propose_slots,
        ReplyAction.RESCHEDULE: _build_reschedule,
        ReplyAction.DOCUMENT_REPLY: _build_document_reply,
        ReplyAction.THANK_YOU: _build_thank_you,
        ReplyAction.FOLLOWUP: _build_followup,
        ReplyAction.WITHDRAW: _build_withdraw,
        ReplyAction.DECLINE_OFFER: _build_decline_offer,
        ReplyAction.GENERAL_REPLY: _build_general,
        ReplyAction.REQUEST_ALTERNATIVES: _build_request_alternatives,
        ReplyAction.ACKNOWLEDGE_REJECTION: _build_acknowledge_rejection,
        ReplyAction.ACKNOWLEDGE_CANCELLATION: _build_acknowledge_cancellation,
    }
    return builders[action](
        facts,
        offer_phone=offer_phone,
        general_note=general_note,
    )


def _build_confirm_interview(
    facts: VerifiedFacts, *, offer_phone: bool = False, general_note: str = ""
) -> ReplyDraft:
    del general_note
    blocking = _missing_core(facts)
    used = [k for k in ("company", "position", "contact_name", "contact_email") if getattr(facts, k)]
    when_line = ""
    if facts.interview_when:
        when_line = f" am {human_slot(facts.interview_when)}"
        used.append("interview_when")
    else:
        blocking.append("unverified_interview_when")
    phone_line = ""
    if offer_phone and facts.phone:
        phone_line = (
            f"\nUnter {facts.phone} bin ich in den genannten Zeitfenstern "
            "telefonisch erreichbar.\n"
        )
        used.append("phone")
    role = _role_line(facts)
    role_bit = f" ({role})" if role else ""
    body = (
        f"{_greeting(facts)}\n\n"
        f"vielen Dank für die Einladung{role_bit}. Den vorgeschlagenen Termin"
        f"{when_line} kann ich wahrnehmen.{phone_line}\n"
        f"{_signoff(facts)}"
    )
    return _base_draft(
        action=ReplyAction.CONFIRM_INTERVIEW,
        facts=facts,
        subject="Bestätigung Interviewtermin",
        body=body,
        used=used,
        blocking=blocking,
    )


def human_slot(value: str) -> str:
    """Render a verified ISO time in its supplied timezone, without guessing."""
    from datetime import datetime
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value
    days = ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag")
    zone = stamp.strftime("%z")
    zone_label = f" (UTC{zone[:3]}:{zone[3:]})" if zone else ""
    return f"{days[stamp.weekday()]}, {stamp:%d.%m.%Y} um {stamp:%H:%M} Uhr{zone_label}"


def _build_propose_slots(
    facts: VerifiedFacts, *, offer_phone: bool = False, general_note: str = ""
) -> ReplyDraft:
    del offer_phone, general_note
    blocking = _missing_core(facts)
    used = [k for k in ("company", "position", "contact_name", "contact_email") if getattr(facts, k)]
    if not facts.proposed_slots:
        blocking.append("unverified_slots")
        slots_block = (
            "(Keine verifizierten Terminvorschläge hinterlegt — bitte manuell ergänzen.)"
        )
    else:
        used.append("proposed_slots")
        lines = "\n".join(f"- {human_slot(s)}" for s in facts.proposed_slots)
        if len(facts.proposed_slots) == 1:
            slots_block = f"Der vorgeschlagene Termin am {human_slot(facts.proposed_slots[0])} passt mir gut. Gerne nehme ich diesen Termin wahr."
        else:
            slots_block = f"Für das Vorstellungsgespräch passen mir folgende Termine:\n{lines}"
    role = _role_line(facts)
    role_bit = f" {role}" if role else ""
    body = (
        f"{_greeting(facts)}\n\n"
        f"vielen Dank für Ihre Nachricht zur Bewerbung{role_bit}.\n"
        f"{slots_block}\n\nBitte geben Sie mir eine kurze Rückmeldung zum Termin. Ich freue mich auf das Gespräch.\n\n"
        f"{_signoff(facts)}"
    )
    return _base_draft(
        action=ReplyAction.PROPOSE_SLOTS,
        facts=facts,
        subject=f"Vorstellungsgespräch – {facts.position}" if facts.position else "Terminvorschläge zum Vorstellungsgespräch",
        body=body,
        used=used,
        blocking=blocking,
    )


def _build_reschedule(
    facts: VerifiedFacts, *, offer_phone: bool = False, general_note: str = ""
) -> ReplyDraft:
    del offer_phone, general_note
    blocking = _missing_core(facts)
    used = [k for k in ("company", "position", "contact_name", "contact_email") if getattr(facts, k)]
    role = _role_line(facts)
    role_bit = f" ({role})" if role else ""
    old = ""
    if facts.interview_when:
        old = (
            f" Den bisherigen Termin am {human_slot(facts.interview_when)} "
            "kann ich leider nicht wahrnehmen."
        )
        used.append("interview_when")
    else:
        blocking.append("unverified_interview_when")
    if facts.proposed_slots:
        used.append("proposed_slots")
        alt = "\n".join(f"- {human_slot(s)}" for s in facts.proposed_slots)
        alt_block = f" Als Alternative passen mir folgende Termine:\n{alt}"
    else:
        blocking.append("unverified_slots")
        alt_block = " Bitte lassen Sie uns einen neuen Termin finden."
    body = (
        f"{_greeting(facts)}\n\n"
        f"könnten wir den Interviewtermin{role_bit} verschieben?{old}{alt_block}\n\n"
        f"{_signoff(facts)}"
    )
    return _base_draft(
        action=ReplyAction.RESCHEDULE,
        facts=facts,
        subject="Bitte um Terminverschiebung",
        body=body,
        used=used,
        blocking=blocking,
    )


def _build_document_reply(
    facts: VerifiedFacts, *, offer_phone: bool = False, general_note: str = ""
) -> ReplyDraft:
    del offer_phone, general_note
    blocking = _missing_core(facts)
    used = [k for k in ("company", "position", "contact_name", "contact_email") if getattr(facts, k)]
    if facts.documents:
        used.append("documents")
        doc_line = ", ".join(facts.documents)
        mid = (
            "Anbei sende ich Ihnen die angeforderten Unterlagen: "
            f"{doc_line}."
        )
    else:
        mid = (
            "Gerne übersende ich die angeforderten Unterlagen. "
            "(Dokumentliste nicht verifiziert — bitte vor Versand prüfen.)"
        )
        blocking.append("unverified_documents")
    if facts.missing_documents:
        # Name what is missing; never present it as available or to be sent later.
        used.append("missing_documents")
        blocking.append("requested_documents_unavailable")
        missing = ", ".join(facts.missing_documents)
        mid += f" Folgende angeforderte Unterlagen liegen mir nicht vor: {missing}."
    role = _role_line(facts)
    role_bit = f" {role}" if role else ""
    body = (
        f"{_greeting(facts)}\n\n"
        f"vielen Dank für Ihre Nachricht zur Bewerbung{role_bit}. {mid}\n\n"
        f"{_signoff(facts)}"
    )
    draft = _base_draft(
        action=ReplyAction.DOCUMENT_REPLY,
        facts=facts,
        subject="Unterlagen zur Bewerbung",
        body=body,
        used=used,
        blocking=blocking,
    )
    draft.attachments = list(facts.documents)
    return draft


def _build_thank_you(
    facts: VerifiedFacts, *, offer_phone: bool = False, general_note: str = ""
) -> ReplyDraft:
    del offer_phone, general_note
    blocking = _missing_core(facts)
    used = [k for k in ("company", "position", "contact_name", "contact_email") if getattr(facts, k)]
    role = _role_line(facts)
    role_bit = f" {role}" if role else ""
    body = (
        f"{_greeting(facts)}\n\n"
        f"vielen Dank für das Gespräch{role_bit}. Ich habe mich über den Austausch "
        f"sehr gefreut und bleibe bei Interesse gerne verfügbar.\n\n"
        f"{_signoff(facts)}"
    )
    return _base_draft(
        action=ReplyAction.THANK_YOU,
        facts=facts,
        subject="Danke für das Gespräch",
        body=body,
        used=used,
        blocking=blocking,
    )


def _build_followup(
    facts: VerifiedFacts, *, offer_phone: bool = False, general_note: str = ""
) -> ReplyDraft:
    del offer_phone, general_note
    blocking = _missing_core(facts)
    used = [k for k in ("company", "position", "contact_name", "contact_email") if getattr(facts, k)]
    role = _role_line(facts)
    if not role:
        mid = "kurz möchte ich höflich nach dem Stand meiner Bewerbung fragen."
    else:
        mid = (
            f"kurz möchte ich höflich nach dem Stand meiner Bewerbung {role} fragen."
        )
    body = (
        f"{_greeting(facts)}\n\n"
        f"{mid} Ich bleibe weiterhin sehr interessiert und stehe "
        f"für Rückfragen gerne zur Verfügung.\n\n"
        f"{_signoff(facts)}"
    )
    subject = (
        f"Nachfrage zur Bewerbung — {facts.position}"
        if facts.position
        else "Nachfrage zur Bewerbung"
    )
    return _base_draft(
        action=ReplyAction.FOLLOWUP,
        facts=facts,
        subject=subject,
        body=body,
        used=used,
        blocking=blocking,
    )


def _build_withdraw(
    facts: VerifiedFacts, *, offer_phone: bool = False, general_note: str = ""
) -> ReplyDraft:
    del offer_phone, general_note
    blocking = _missing_core(facts)
    used = [k for k in ("company", "position", "contact_name", "contact_email") if getattr(facts, k)]
    role = _role_line(facts)
    role_bit = f" {role}" if role else ""
    body = (
        f"{_greeting(facts)}\n\n"
        f"hiermit ziehe ich meine Bewerbung{role_bit} zurück. "
        f"Vielen Dank für die bisherige Berücksichtigung.\n\n"
        f"{_signoff(facts)}"
    )
    draft = _base_draft(
        action=ReplyAction.WITHDRAW,
        facts=facts,
        subject="Rücknahme der Bewerbung",
        body=body,
        used=used,
        blocking=blocking,
    )
    draft.requires_explicit_review = True
    return draft


def _build_decline_offer(
    facts: VerifiedFacts, *, offer_phone: bool = False, general_note: str = ""
) -> ReplyDraft:
    del offer_phone, general_note
    blocking = _missing_core(facts)
    used = [k for k in ("company", "position", "contact_name", "contact_email") if getattr(facts, k)]
    # Never invent salary / contract acceptance language.
    role = _role_line(facts)
    role_bit = f" {role}" if role else ""
    body = (
        f"{_greeting(facts)}\n\n"
        f"vielen Dank für Ihr Angebot{role_bit}. Nach sorgfältiger Überlegung "
        f"muss ich das Angebot leider ablehnen. Ich wünsche Ihnen weiterhin "
        f"viel Erfolg bei der Besetzung.\n\n"
        f"{_signoff(facts)}"
    )
    draft = _base_draft(
        action=ReplyAction.DECLINE_OFFER,
        facts=facts,
        subject="Rückmeldung zu Ihrem Angebot",
        body=body,
        used=used,
        blocking=blocking,
    )
    draft.requires_explicit_review = True
    return draft


def _build_general(
    facts: VerifiedFacts, *, offer_phone: bool = False, general_note: str = ""
) -> ReplyDraft:
    del offer_phone
    blocking = _missing_core(facts)
    used = [k for k in ("company", "position", "contact_name", "contact_email") if getattr(facts, k)]
    note = (general_note or "").strip()
    if note:
        mid = note[:800]
        used.append("general_note")
    else:
        role = _role_line(facts)
        role_bit = f" {role}" if role else ""
        mid = (
            f"vielen Dank für Ihre Nachricht zur Bewerbung{role_bit}. "
            "Gerne beantworte ich Ihre Rückfragen und freue mich auf die nächsten Schritte."
        )
    body = f"{_greeting(facts)}\n\n{mid}\n\n{_signoff(facts)}"
    return _base_draft(
        action=ReplyAction.GENERAL_REPLY,
        facts=facts,
        subject="Antwort zur Bewerbung",
        body=body,
        used=used,
        blocking=blocking,
    )


def _build_request_alternatives(
    facts: VerifiedFacts, *, offer_phone: bool = False, general_note: str = ""
) -> ReplyDraft:
    """None of the offered slots is free: ask for others without giving a reason."""
    del offer_phone, general_note
    blocking = _missing_core(facts)
    used = [k for k in ("company", "position", "contact_name", "contact_email", "reference") if getattr(facts, k)]
    role = _role_line(facts)
    role_bit = f" {role}" if role else ""
    body = (
        f"{_greeting(facts)}\n\n"
        f"vielen Dank für Ihre Einladung zum Gespräch{role_bit}. "
        "Leider kann ich keinen der vorgeschlagenen Termine wahrnehmen. "
        "Könnten Sie mir alternative Termine nennen?\n\n"
        f"{_signoff(facts)}"
    )
    return _base_draft(
        action=ReplyAction.REQUEST_ALTERNATIVES,
        facts=facts,
        subject=f"Terminabstimmung – {facts.position}" if facts.position else "Terminabstimmung",
        body=body,
        used=used,
        blocking=blocking,
    )


def _build_acknowledge_rejection(
    facts: VerifiedFacts, *, offer_phone: bool = False, general_note: str = ""
) -> ReplyDraft:
    """Short thanks after a rejection: no questions, no next steps, no discussion."""
    del offer_phone, general_note
    blocking = _missing_core(facts)
    used = [k for k in ("company", "position", "contact_name", "contact_email", "reference") if getattr(facts, k)]
    role = _role_line(facts)
    role_bit = f" {role}" if role else ""
    body = (
        f"{_greeting(facts)}\n\n"
        f"vielen Dank für Ihre Rückmeldung zu meiner Bewerbung{role_bit}. "
        "Ich wünsche Ihnen viel Erfolg bei der Besetzung der Stelle.\n\n"
        f"{_signoff(facts)}"
    )
    return _base_draft(
        action=ReplyAction.ACKNOWLEDGE_REJECTION,
        facts=facts,
        subject="Vielen Dank für Ihre Rückmeldung",
        body=body,
        used=used,
        blocking=blocking,
    )


def _build_acknowledge_cancellation(
    facts: VerifiedFacts, *, offer_phone: bool = False, general_note: str = ""
) -> ReplyDraft:
    """Short acknowledgement of a cancelled appointment: no own dates, no 'why'."""
    del offer_phone, general_note
    blocking = _missing_core(facts)
    used = [k for k in ("company", "position", "contact_name", "contact_email", "reference") if getattr(facts, k)]
    role = _role_line(facts)
    role_bit = f" {role}" if role else ""
    body = (
        f"{_greeting(facts)}\n\n"
        f"vielen Dank für die Information zu meiner Bewerbung{role_bit}. "
        "Die Absage des Termins habe ich zur Kenntnis genommen.\n\n"
        f"{_signoff(facts)}"
    )
    return _base_draft(
        action=ReplyAction.ACKNOWLEDGE_CANCELLATION,
        facts=facts,
        subject="Ihre Terminabsage",
        body=body,
        used=used,
        blocking=blocking,
    )


# --- Which draft for which incoming mail (shared by the inbox UI and T01.10) --

# Pure notifications: no reply (T01.10 gold, Eingangsbestätigung draft_allowed=false).
NO_REPLY_CATEGORIES = frozenset({"confirmation", "under_review", "noise"})
INTERVIEW_CATEGORIES = frozenset({"interview", "interview_invite", "interview_reschedule"})
# Stop reason of a parsed proposal whose offered slots are all taken.
ALL_OFFERED_SLOTS_TAKEN = "fail_safe:no_conflict_free_slots"

_MAIL_REFERENCE_RE = re.compile(
    r"\b(?:kennziffer|kennzeichen|referenz(?:nummer)?|ref\.|aktenzeichen|ihr zeichen)\s*[:#]?\s*"
    r"([A-Za-z0-9][A-Za-z0-9/_.\-]{2,40})",
    re.IGNORECASE,
)
_BULLET_RE = re.compile(r"^\s*(?:[-•*–]|\d{1,2}[.)])\s+(.+?)\s*$")
# Requested document noun -> words a matching file name must contain.
_DOCUMENT_KINDS: dict[str, tuple[str, ...]] = {
    "arbeitszeugnis": ("zeugnis",),
    "zwischenzeugnis": ("zeugnis",),
    "zeugnis": ("zeugnis",),
    "zertifikat": ("zertifikat", "certificate"),
    "nachweis": ("nachweis",),
    "lebenslauf": ("lebenslauf", "cv", "resume"),
    "anschreiben": ("anschreiben", "cover"),
}


def mail_reference(subject: str, body: str) -> str:
    """Reference number exactly as the employer wrote it (must contain a digit)."""
    for text in (subject or "", body or ""):
        for match in _MAIL_REFERENCE_RE.finditer(text):
            value = match.group(1).rstrip(".,;:)")
            if any(ch.isdigit() for ch in value):
                return value
    return ""


def requested_documents(body: str) -> list[str]:
    """Bulleted items of a document request that name a known document kind."""
    items = []
    for line in (body or "").splitlines():
        match = _BULLET_RE.match(line)
        if match and any(kind in match.group(1).casefold() for kind in _DOCUMENT_KINDS):
            items.append(match.group(1).rstrip(".,;"))
    return items


def _document_noun(item: str) -> tuple[str, str]:
    """(kind, display) of the requested document: the last kind word in the item
    is the head noun ("das im Lebenslauf genannte SQL-Zertifikat" -> Zertifikat)."""
    lowered = item.casefold()
    kind = max((k for k in _DOCUMENT_KINDS if k in lowered), key=lambda k: lowered.rfind(k))
    token = next((t.strip(".,;()") for t in reversed(item.split()) if kind in t.casefold()), kind)
    return kind, token


def match_requested_documents(
    requested: Sequence[str], available: Sequence[str]
) -> tuple[list[str], list[str]]:
    """(attach, missing): attach only the applicant's own files that match a requested
    document kind (and its qualifier, e.g. 'SQL' in 'SQL-Zertifikat')."""
    attach: list[str] = []
    missing: list[str] = []
    for item in requested:
        kind, token = _document_noun(item)
        qualifier = token.casefold().split("-")[0] if "-" in token else ""
        hits = [
            name for name in available
            if any(word in name.casefold() for word in _DOCUMENT_KINDS[kind])
            and (not qualifier or qualifier in name.casefold())
        ]
        if hits:
            attach.extend(h for h in hits[:1] if h not in attach)
        else:
            missing.append(token)
    return attach, missing


def plan_mail_reply(
    email: dict[str, Any],
    case: dict[str, Any] | None,
    *,
    applicant_name: str = "",
    proposal: Any = None,
    available_documents: Sequence[str] = (),
) -> ReplyDraft | None:
    """The reply draft for an incoming mail, or None when no reply is due.

    ``proposal`` is the ranked SchedulingProposal for interview mails; the draft
    accepts exactly its rank-1 slot. All offered slots taken -> ask for
    alternatives; unparsed proposal -> no draft (fail-safe).
    """
    if not case:
        return None
    category = str(email.get("category") or "").lower()
    if category in NO_REPLY_CATEGORIES:
        return None
    reference = mail_reference(str(email.get("subject") or ""), str(email.get("body_text") or ""))
    common = {"applicant_name": applicant_name, "reference": reference}
    if category in INTERVIEW_CATEGORIES:
        if proposal is None:
            return None
        if proposal.ranked_slots:
            return build_action_draft(
                ReplyAction.PROPOSE_SLOTS, case, proposed_slots=[proposal.ranked_slots[0].start.isoformat()], **common
            )
        if proposal.stop_reason == ALL_OFFERED_SLOTS_TAKEN:
            return build_action_draft(ReplyAction.REQUEST_ALTERNATIVES, case, **common)
        return None
    if category == "rejection":
        return build_action_draft(ReplyAction.ACKNOWLEDGE_REJECTION, case, **common)
    if category == "interview_cancelled":
        return build_action_draft(ReplyAction.ACKNOWLEDGE_CANCELLATION, case, **common)
    if category == "document_request":
        attach, missing = match_requested_documents(
            requested_documents(str(email.get("body_text") or "")), available_documents
        )
        return build_action_draft(
            ReplyAction.DOCUMENT_REPLY, case, documents=attach, missing_documents=missing, **common
        )
    return build_action_draft(ReplyAction.GENERAL_REPLY, case, **common)


def build_follow_up_draft(case: dict[str, Any], *, applicant_name: str = "") -> ReplyDraft:
    return build_action_draft(
        ReplyAction.FOLLOWUP, case, applicant_name=applicant_name
    )


def build_interview_confirm_draft(
    case: dict[str, Any],
    *,
    when_text: str = "",
    applicant_name: str = "",
    offer_phone: bool = False,
    phone: str = "",
) -> ReplyDraft:
    case_ext = dict(case or {})
    if when_text:
        case_ext["interview_when"] = when_text
        case_ext["interview_when_verified"] = True
    return build_action_draft(
        ReplyAction.CONFIRM_INTERVIEW,
        case_ext,
        applicant_name=applicant_name,
        phone=phone,
        offer_phone=offer_phone,
        interview_when=when_text,
    )


class SendGate:
    """Approval-before-send + failure safety. Default refuses real send.

    Commercial invariants:
    - 0 default auto-send
    - Failed send != sent
    - Binding actions need explicit binding_review_approved
    """

    def __init__(
        self,
        *,
        allow_send: bool = False,
        draft_only: bool = True,
    ) -> None:
        self.allow_send = bool(allow_send)
        self.draft_only = bool(draft_only)

    def approve(self, draft: ReplyDraft) -> ReplyDraft:
        draft.approved = True
        return draft

    def approve_binding_review(self, draft: ReplyDraft) -> ReplyDraft:
        """Explicit second confirmation for WITHDRAW / DECLINE_OFFER."""
        draft.binding_review_approved = True
        return draft

    def attempt_automatic_send(self, draft: ReplyDraft, *, transport) -> ReplyDraft:
        from core.commercial.features import PremiumFeature, require_premium
        require_premium(PremiumFeature.AUTOMATIC_REPLY)

    def attempt_send(self, draft: ReplyDraft, *, transport) -> ReplyDraft:
        """Call transport(draft) only when approved and allow_send.

        On failure: mark send_error, leave sent=False, keep draft for retry.
        Never silently drop the draft. Never treats failed send as sent.
        """
        draft.auto_send = False

        if (draft.draft_only or self.draft_only) and not self.allow_send:
            draft.send_error = "draft_only: send disabled (approval path required)"
            draft.sent = False
            return draft
        if not draft.approved:
            draft.send_error = "not_approved"
            draft.sent = False
            return draft
        if draft.requires_explicit_review and not draft.binding_review_approved:
            draft.send_error = "binding_review_required"
            draft.sent = False
            return draft
        if draft.blocking_reasons and draft.action in DATE_SENSITIVE_ACTIONS:
            critical = {
                "unverified_interview_when",
                "unverified_slots",
                "missing_case_id",
            }
            hit = critical.intersection(draft.blocking_reasons)
            if hit:
                draft.send_error = "blocked_unverified_facts:" + ",".join(sorted(hit))
                draft.sent = False
                return draft
        if not self.allow_send:
            draft.send_error = "send_not_enabled"
            draft.sent = False
            return draft
        if draft.attachments and not getattr(transport, "supports_attachments", False):
            # The text says "Anbei …": never send it without the files.
            draft.send_error = "attachments_require_manual_send"
            draft.sent = False
            return draft
        try:
            transport(draft)
            draft.sent = True
            draft.send_error = ""
        except Exception as exc:
            draft.sent = False
            draft.send_error = f"send_failed: {type(exc).__name__}: {exc}"
        return draft


def assert_cross_case_isolation(draft: ReplyDraft, case: dict[str, Any]) -> list[str]:
    """Return violations if draft identity does not match the given case."""
    violations: list[str] = []
    expected_id = str(case.get("id") or "")
    if draft.case_id != expected_id:
        violations.append("case_id_mismatch")
    other_company = (case.get("foreign_company") or "").strip()
    other_position = (case.get("foreign_position") or "").strip()
    company = (case.get("company") or "").strip()
    position = (case.get("position") or "").strip()
    if other_company and other_company in draft.body and other_company != company:
        violations.append("foreign_company_leak")
    if other_position and other_position in draft.body and other_position != position:
        violations.append("foreign_position_leak")
    return violations
