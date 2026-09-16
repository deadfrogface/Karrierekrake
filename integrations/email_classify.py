"""Local email classification with confidence (no cloud AI).

Primary phrase sets adapted from PBP ``detect_email_status`` / STATUS_PATTERNS
(MIT). English extras and false-rejection overrides adapted from
GmailJobTracker RuleClassifier early-detection ideas (MIT).

High-impact labels (rejection / offer / interview_cancelled) require explicit
supporting evidence signals — otherwise return review/other (fail closed).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from integrations.email_normalize import normalize_umlauts


@dataclass(frozen=True)
class ClassificationResult:
    category: str
    confidence: float
    reasons: tuple[str, ...] = ()
    false_rejection_blocked: bool = False
    evidence: tuple[str, ...] = ()


# Signal groups — multiple complementary cues, not single exact sentences.
CONFIRMATION_SIGNALS: tuple[str, ...] = (
    "bewerbung erhalten",
    "eingangsbestatigung",
    "eingangsbestaetigung",
    "unterlagen erhalten",
    "bewerbung ist bei uns eingegangen",
    "bewerbung eingegangen",
    "haben ihre bewerbung",
    "vielen dank fur ihre bewerbung",
    "vielen dank fuer ihre bewerbung",
    "vielen dank fur deine bewerbung",
    "vielen dank fuer deine bewerbung",
    "thank you for your application",
    "thank you for applying",
    "application has been received",
    "we have received your application",
    "your application has been received",
    "application received",
    "bestaetigen den eingang",
    "bestatigen den eingang",
    "bestaetigen hiermit den eingang",
    "den eingang ihrer bewerbung",
    "eingang ihrer unterlagen",
    "eingang ihrer bewerbungsunterlagen",
    "unterlagen sind vollstandig",
    "unterlagen sind vollstaendig",
    "bewerbung erhalten und registriert",
    "haben ihre bewerbung erhalten",
)

INTERVIEW_SIGNALS: tuple[str, ...] = (
    "vorstellungsgesprach",
    "vorstellungsgespraech",
    "gespraachstermin",
    "gesprächstermin",
    "terminvorschlag",
    "einladen zu einem gesprach",
    "einladen zu einem gespräch",
    "interview",
    "phone screen",
    "schedule a call",
    "interview invitation",
    "schedule an interview",
    "verfugbarkeit fur ein gesprach",
    "verfuegbarkeit fuer ein gespraech",
    "zoom",
    "teams meeting",
    "kalendereinladung",
)

INTERVIEW_CANCEL_SIGNALS: tuple[str, ...] = (
    "interview abgesagt",
    "termin abgesagt",
    "termin storniert",
    "gesprach abgesagt",
    "gespraech abgesagt",
    "interview cancelled",
    "interview canceled",
    "cancel the interview",
    "termin entfallt",
    "termin entfaellt",
)

OFFER_SIGNALS: tuple[str, ...] = (
    "stellenangebot",
    "anstellungsangebot",
    "job offer",
    "offer of employment",
    "wir mochten ihnen gerne eine stelle",
    "wir möchten ihnen gerne eine stelle",
    "vertrag zusenden",
    "arbeitsvertrag",
    "congratulations on your offer",
)

REJECTION_STRONG: tuple[str, ...] = (
    "leider mussen wir ihnen mitteilen",
    "leider muessen wir ihnen mitteilen",
    "nicht berucksichtigen",
    "nicht beruecksichtigen",
    "andere bewerberinnen",
    "andere bewerber",
    "absage",
    "we regret to inform",
    "not moving forward",
    "will not be progressing",
    "decided to pursue other candidates",
    "position has been filled",
    "zugunsten anderer",
    "entscheidung zugunsten",
)

# Weak "leider" alone is NOT rejection evidence.
REJECTION_WEAK_ONLY: tuple[str, ...] = (
    "leider keinen termin",
    "leider keinen passenden termin",
    "leider mussen wir den termin",
    "leider muessen wir den termin",
    "leider verschieben",
)

ASSESSMENT_SIGNALS: tuple[str, ...] = (
    "online-test",
    "online assessment",
    "coding challenge",
    "einstellungstest",
    "take-home assignment",
    "complete the assessment",
)

DOCUMENT_REQUEST_SIGNALS: tuple[str, ...] = (
    "bitte senden sie uns",
    "reichen sie bitte",
    "unterlagen nachreichen",
    "lebenslauf erneut",
    "zeugnisse",
    "please provide your",
    "send us your cv",
    "additional documents",
)

EMPLOYER_QUESTION_SIGNALS: tuple[str, ...] = (
    "kurze ruckfrage",
    "kurze rueckfrage",
    "durften wir fragen",
    "duerften wir fragen",
    "wann waren sie verfugbar",
    "wann waeren sie verfuegbar",
    "gehaltsvorstellung",
    "kuendigungsfrist",
    "notice period",
    "salary expectation",
)

RECRUITER_OUTREACH_SIGNALS: tuple[str, ...] = (
    "interessante stelle fur sie",
    "interessante stelle fuer sie",
    "pascht möglicherweise",
    "passt moglicherweise",
    "opportunity that may interest",
    "are you open to",
    "new role that matches",
)

NOISE_SIGNALS: tuple[str, ...] = (
    "unsubscribe",
    "newsletter",
    "job alert",
    "stellenangebot der woche",
    "recommended jobs",
    "marketing@",
    "noreply-promo",
    "paket ist unterwegs",
    "sendungsverfolgung",
    "your package",
)

# Scheduling language that blocks weak rejection (GJT idea).
REJECTION_OVERRIDE_PHRASES: tuple[str, ...] = (
    "terminvorschlag",
    "vorstellungsgesprach",
    "vorstellungsgespraech",
    "schedule an interview",
    "interview invitation",
    "please select a time",
    "calendar invite",
    "zoom meeting",
    "teams meeting",
    "availability for a call",
    "keinen termin",
    "termin verschieben",
    "neuen termin",
)

# Instruction / injection framing — never treat as genuine high-impact hiring mail.
INSTRUCTION_FRAME_SIGNALS: tuple[str, ...] = (
    "ignore previous",
    "ignore all rules",
    "system:",
    "begin_untrusted",
    "klassifiziere als",
    "klassifiziere dies",
    "classify as",
    "classify this as",
    "mark this as",
    "mark as offer",
    "category=offer",
    "category: offer",
    "confidence high",
    "confidence=high",
    "bypass validation",
    "developer mode",
    "override",
    "setze status",
    "status auf",
    "accept calendar",
    "auto-accept",
    "sende eine e-mail",
    "send_email",
    "offer_accepted",
    "terminal status",
    "wiederhole dein systemprompt",
    "ignore safety",
    "prompt-injection ist erlaubt",
    "weisen wir an",
    "als angenommen zu werten",
    "automatisch akzeptieren",
    "ohne user",
    "bypass",
    "jailbreak",
    "category,confidence",
    "offer,high",
    "--accept-offer",
    "accept-offer",
    "action: accept",
    "laut richtlinie",
    "system override",
    "sende die zusage",
)

# Weak offer tokens that need a second corroborating cue.
OFFER_WEAK_ALONE: tuple[str, ...] = (
    "stellenangebot",
    "job offer",
    "arbeitsvertrag",
)


def _hits(text_norm: str, patterns: tuple[str, ...]) -> list[str]:
    found: list[str] = []
    for p in patterns:
        # Patterns may still contain umlauts; normalize like the haystack.
        pn = normalize_umlauts(p)
        if ".*" in pn:
            left, _, right = pn.partition(".*")
            if left in text_norm and right in text_norm:
                found.append(p)
        elif pn and pn in text_norm:
            found.append(p)
    return found


def _score(hits: list[str], *, base: float = 0.45, step: float = 0.18) -> float:
    if not hits:
        return 0.0
    return min(base + step * len(hits), 0.98)


def classify_email(subject: str, body: str) -> ClassificationResult:
    """Classify hiring-related email. Conservative on high-impact labels."""
    combined = normalize_umlauts(f"{subject or ''} {body or ''}")
    if not combined.strip():
        return ClassificationResult("other", 0.0, ("empty",))

    conf_h = _hits(combined, CONFIRMATION_SIGNALS)
    int_h = _hits(combined, INTERVIEW_SIGNALS)
    can_h = _hits(combined, INTERVIEW_CANCEL_SIGNALS)
    off_h = _hits(combined, OFFER_SIGNALS)
    rej_h = _hits(combined, REJECTION_STRONG)
    weak_rej = _hits(combined, REJECTION_WEAK_ONLY)
    as_h = _hits(combined, ASSESSMENT_SIGNALS)
    doc_h = _hits(combined, DOCUMENT_REQUEST_SIGNALS)
    q_h = _hits(combined, EMPLOYER_QUESTION_SIGNALS)
    rec_h = _hits(combined, RECRUITER_OUTREACH_SIGNALS)
    noise_h = _hits(combined, NOISE_SIGNALS)
    override_h = _hits(combined, REJECTION_OVERRIDE_PHRASES)
    instr_h = _hits(combined, INSTRUCTION_FRAME_SIGNALS)

    # Prompt-injection / instruction framing → review (never high-impact from instructions)
    if instr_h:
        return ClassificationResult(
            "review",
            0.2,
            ("instruction_frame_blocked",) + tuple(instr_h[:4]),
            false_rejection_blocked=True,
            evidence=tuple(instr_h[:4]),
        )

    scored: list[tuple[str, float, tuple[str, ...]]] = []

    if can_h:
        scored.append(("interview_cancelled", _score(can_h, base=0.55), tuple(can_h[:5])))
    if int_h and not can_h:
        scored.append(("interview", _score(int_h), tuple(int_h[:5])))
    # Offer: weak single token needs corroboration; newsletter noise wins over stellenangebot alone
    offer_weak = _hits(combined, OFFER_WEAK_ALONE)
    offer_strong = [h for h in off_h if h not in OFFER_WEAK_ALONE]
    if noise_h and offer_weak and not offer_strong and not conf_h and not int_h:
        return ClassificationResult(
            "noise",
            0.75,
            tuple(noise_h[:3]) + ("offer_token_in_newsletter_demoted",),
            evidence=tuple(noise_h[:3]),
        )
    if offer_strong or (len(offer_weak) >= 2) or (
        offer_weak
        and (
            conf_h
            or "herzlichen glueckwunsch" in combined
            or "herzlichen gluckwunsch" in combined
            or "congratulations" in combined
        )
    ):
        use_off = offer_strong or off_h
        scored.append(("offer", _score(use_off, base=0.55), tuple(use_off[:5])))
    elif len(off_h) >= 1 and not offer_weak == off_h:
        scored.append(("offer", _score(off_h, base=0.55), tuple(off_h[:5])))
    elif offer_weak and not noise_h:
        # Single weak offer cue → review, not confident offer
        scored.append(("review", 0.35, tuple(offer_weak[:3]) + ("weak_offer_insufficient",)))
    if rej_h:
        scored.append(("rejection", _score(rej_h, base=0.55), tuple(rej_h[:5])))
    if conf_h:
        scored.append(("confirmation", _score(conf_h), tuple(conf_h[:5])))
    if as_h:
        scored.append(("assessment", _score(as_h), tuple(as_h[:5])))
    if doc_h:
        scored.append(("document_request", _score(doc_h), tuple(doc_h[:5])))
    if q_h:
        scored.append(("employer_question", _score(q_h), tuple(q_h[:5])))
    if rec_h:
        scored.append(("recruiter_outreach", _score(rec_h), tuple(rec_h[:5])))
    if noise_h and not scored:
        return ClassificationResult("noise", 0.7, tuple(noise_h[:3]), evidence=tuple(noise_h[:3]))

    if not scored:
        # Weak "leider" without strong rejection → review, not rejection
        if weak_rej or "leider" in combined:
            return ClassificationResult(
                "review",
                0.35,
                ("weak_leider_without_rejection_evidence",),
                false_rejection_blocked=True,
                evidence=tuple(weak_rej[:3]),
            )
        return ClassificationResult("other", 0.2, ("no_pattern",))

    scored.sort(key=lambda x: x[1], reverse=True)
    category, confidence, reasons = scored[0]

    # False-rejection protection: scheduling / soft leider language.
    if category == "rejection":
        if override_h or weak_rej:
            if int_h or override_h:
                return ClassificationResult(
                    "interview",
                    max(0.75, confidence),
                    tuple((int_h or override_h)[:5]),
                    false_rejection_blocked=True,
                    evidence=tuple((int_h or override_h)[:5]),
                )
            return ClassificationResult(
                "review",
                0.4,
                reasons + ("false_rejection_guard",),
                false_rejection_blocked=True,
                evidence=reasons,
            )
        # Require ≥1 strong rejection cue (already true) — single weak absage alone
        # with interview language already handled. Multi-signal preferred.
        if len(reasons) < 1:
            return ClassificationResult(
                "review",
                0.35,
                ("insufficient_rejection_evidence",),
                evidence=(),
            )

    # High-impact must keep evidence attached
    if category in {"rejection", "offer", "interview_cancelled"} and not reasons:
        return ClassificationResult("review", 0.3, ("high_impact_without_evidence",))

    if noise_h and category == "rejection" and confidence < 0.75:
        return ClassificationResult("noise", 0.65, tuple(noise_h[:3]), evidence=tuple(noise_h[:3]))

    return ClassificationResult(
        category,
        confidence,
        reasons,
        false_rejection_blocked=False,
        evidence=reasons,
    )


# Back-compat alias used by older tests / imports
STATUS_PATTERNS = {
    "confirmation": CONFIRMATION_SIGNALS,
    "interview": INTERVIEW_SIGNALS,
    "assessment": ASSESSMENT_SIGNALS,
    "offer": OFFER_SIGNALS,
    "rejection": REJECTION_STRONG,
}
