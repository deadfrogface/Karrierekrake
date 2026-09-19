"""Action-specific employer reply drafts — draft-only by default.

PR32: free-form mail generation is replaced by typed ReplyAction contracts.
Only verified company / job / contact / date facts may appear in the body.
DEFAULT: DRAFT ONLY — never auto-send. Binding actions (WITHDRAW, DECLINE_OFFER)
require an extra explicit review flag before any send attempt.
"""

from __future__ import annotations

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

    def __post_init__(self) -> None:
        self.auto_send = False
        if self.action in BINDING_ACTIONS:
            self.requires_explicit_review = True


def _greeting(facts: VerifiedFacts) -> str:
    if facts.contact_name:
        return f"Guten Tag {facts.contact_name},"
    return "Guten Tag,"


def _signoff(facts: VerifiedFacts) -> str:
    name = facts.applicant_name or "…"
    return f"Mit freundlichen Grüßen\n{name}\n"


def _role_line(facts: VerifiedFacts) -> str:
    parts: list[str] = []
    if facts.position:
        parts.append(f"als {facts.position}")
    if facts.company:
        parts.append(f"bei {facts.company}")
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
        when_line = f" am {facts.interview_when}"
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
        lines = "\n".join(f"- {s}" for s in facts.proposed_slots)
        slots_block = f"Gerne schlage ich folgende verifizierte Zeitfenster vor:\n{lines}"
    role = _role_line(facts)
    role_bit = f" {role}" if role else ""
    body = (
        f"{_greeting(facts)}\n\n"
        f"vielen Dank für Ihre Nachricht zur Bewerbung{role_bit}.\n"
        f"{slots_block}\n\n"
        f"{_signoff(facts)}"
    )
    return _base_draft(
        action=ReplyAction.PROPOSE_SLOTS,
        facts=facts,
        subject="Terminvorschläge",
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
            f" Den bisherigen Termin am {facts.interview_when} "
            "kann ich leider nicht wahrnehmen."
        )
        used.append("interview_when")
    else:
        blocking.append("unverified_interview_when")
    if facts.proposed_slots:
        used.append("proposed_slots")
        alt = "\n".join(f"- {s}" for s in facts.proposed_slots)
        alt_block = f" Alternative verifizierte Zeitfenster:\n{alt}"
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
            "Anbei bzw. nachfolgend übersende ich die angeforderten Unterlagen: "
            f"{doc_line}."
        )
    else:
        mid = (
            "Gerne übersende ich die angeforderten Unterlagen. "
            "(Dokumentliste nicht verifiziert — bitte vor Versand prüfen.)"
        )
        blocking.append("unverified_documents")
    role = _role_line(facts)
    role_bit = f" {role}" if role else ""
    body = (
        f"{_greeting(facts)}\n\n"
        f"vielen Dank für Ihre Nachricht zur Bewerbung{role_bit}. {mid}\n\n"
        f"{_signoff(facts)}"
    )
    return _base_draft(
        action=ReplyAction.DOCUMENT_REPLY,
        facts=facts,
        subject="Unterlagen zur Bewerbung",
        body=body,
        used=used,
        blocking=blocking,
    )


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
            "Ich melde mich bezogen auf den vorliegenden Fall."
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
