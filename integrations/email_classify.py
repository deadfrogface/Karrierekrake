"""Local recruiting-email classification with confidence + evidence (no cloud AI).

Primary phrase sets adapted from PBP ``detect_email_status`` / STATUS_PATTERNS
(MIT). English extras and false-rejection overrides adapted from
GmailJobTracker RuleClassifier early-detection ideas (MIT).

High-impact labels (rejection / offer / interview_cancelled) require explicit
supporting evidence signals — otherwise return review/UNKNOWN (fail closed).

Classifier versioning / rollback
--------------------------------
``CLASSIFIER_VERSION`` identifies the active rule set. Persist it with each
classification. To roll back after a regression:

1. Set ``CLASSIFIER_VERSION`` / ``ACTIVE_CLASSIFIER_VERSION`` to a prior pin
   (see ``SUPPORTED_CLASSIFIER_VERSIONS``), **or**
2. Force ``review_only_mode=True`` so all mails land in UNKNOWN/REVIEW and
   never drive status / send / calendar actions alone.

Commercial rule: the classifier must never solely trigger status mutation,
outbound mail, or calendar actions — callers enforce gates (see case_pipeline
``auto_status`` / SendGate).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from integrations.email_normalize import (
    NormalizedEmail,
    normalize_umlauts,
    split_quoted_history,
    split_signature,
)

# ---------------------------------------------------------------------------
# Version pin — bump when rule semantics change; keep old pins listed for
# rollback documentation. Unknown pins → review-only behaviour.
# ---------------------------------------------------------------------------
CLASSIFIER_VERSION = "1.0.0"
SUPPORTED_CLASSIFIER_VERSIONS: frozenset[str] = frozenset({"1.0.0"})
ACTIVE_CLASSIFIER_VERSION = CLASSIFIER_VERSION
DEFAULT_LOW_CONFIDENCE_THRESHOLD = 0.55
HIGH_IMPACT_MIN_CONFIDENCE = 0.65


class EmailLifecycleClass:
    """Canonical PR28 lifecycle classes (string values for JSON storage)."""

    APPLICATION_RECEIVED = "application_received"
    UNDER_REVIEW = "under_review"
    INTERVIEW_INVITE = "interview_invite"
    INTERVIEW_RESCHEDULE = "interview_reschedule"
    ASSESSMENT = "assessment"
    DOCUMENT_REQUEST = "document_request"
    REJECTION = "rejection"
    OFFER = "offer"
    GENERAL_RECRUITER_MESSAGE = "general_recruiter_message"
    GENERAL = "general"
    UNKNOWN = "unknown"
    NOISE = "noise"
    REVIEW = "review"
    INTERVIEW_CANCELLED = "interview_cancelled"


_LIFECYCLE_TO_LEGACY: dict[str, str] = {
    EmailLifecycleClass.APPLICATION_RECEIVED: "confirmation",
    EmailLifecycleClass.UNDER_REVIEW: "confirmation",
    EmailLifecycleClass.INTERVIEW_INVITE: "interview",
    EmailLifecycleClass.INTERVIEW_RESCHEDULE: "interview",
    EmailLifecycleClass.INTERVIEW_CANCELLED: "interview_cancelled",
    EmailLifecycleClass.ASSESSMENT: "assessment",
    EmailLifecycleClass.DOCUMENT_REQUEST: "document_request",
    EmailLifecycleClass.REJECTION: "rejection",
    EmailLifecycleClass.OFFER: "offer",
    EmailLifecycleClass.GENERAL_RECRUITER_MESSAGE: "recruiter_outreach",
    EmailLifecycleClass.GENERAL: "other",
    EmailLifecycleClass.UNKNOWN: "other",
    EmailLifecycleClass.NOISE: "noise",
    EmailLifecycleClass.REVIEW: "review",
}

_LEGACY_TO_LIFECYCLE: dict[str, str] = {
    "confirmation": EmailLifecycleClass.APPLICATION_RECEIVED,
    "eingangsbestaetigung": EmailLifecycleClass.APPLICATION_RECEIVED,
    "under_review": EmailLifecycleClass.UNDER_REVIEW,
    "interview": EmailLifecycleClass.INTERVIEW_INVITE,
    "interview_invite": EmailLifecycleClass.INTERVIEW_INVITE,
    "interview_reschedule": EmailLifecycleClass.INTERVIEW_RESCHEDULE,
    "interview_cancelled": EmailLifecycleClass.INTERVIEW_CANCELLED,
    "assessment": EmailLifecycleClass.ASSESSMENT,
    "document_request": EmailLifecycleClass.DOCUMENT_REQUEST,
    "rejection": EmailLifecycleClass.REJECTION,
    "offer": EmailLifecycleClass.OFFER,
    "recruiter_outreach": EmailLifecycleClass.GENERAL_RECRUITER_MESSAGE,
    "employer_question": EmailLifecycleClass.GENERAL,
    "other": EmailLifecycleClass.GENERAL,
    "noise": EmailLifecycleClass.NOISE,
    "review": EmailLifecycleClass.REVIEW,
    "unknown": EmailLifecycleClass.UNKNOWN,
}


@dataclass(frozen=True)
class ClassificationResult:
    category: str  # legacy operational label (confirmation / interview / …)
    confidence: float
    reasons: tuple[str, ...] = ()
    false_rejection_blocked: bool = False
    evidence: tuple[str, ...] = ()
    lifecycle_class: str = ""
    classifier_version: str = CLASSIFIER_VERSION
    needs_review: bool = False

    @property
    def is_low_confidence(self) -> bool:
        return self.confidence < DEFAULT_LOW_CONFIDENCE_THRESHOLD or self.needs_review


def lifecycle_to_legacy(lifecycle_class: str) -> str:
    return _LIFECYCLE_TO_LEGACY.get(lifecycle_class, "other")


def legacy_to_lifecycle(category: str) -> str:
    return _LEGACY_TO_LIFECYCLE.get(
        (category or "").strip().lower(), EmailLifecycleClass.UNKNOWN
    )


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

UNDER_REVIEW_SIGNALS: tuple[str, ...] = (
    "unterlagen werden gepruft",
    "unterlagen werden geprueft",
    "bewerbung wird gepruft",
    "bewerbung wird geprueft",
    "in bearbeitung",
    "currently under review",
    "application is under review",
    "we are reviewing your application",
    "prufen ihre unterlagen",
    "pruefen ihre unterlagen",
    "prufung ihrer bewerbung",
    "pruefung ihrer bewerbung",
    "reviewing your application",
    "shortlisting",
    "in der engeren auswahl",
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

INTERVIEW_RESCHEDULE_SIGNALS: tuple[str, ...] = (
    "termin verschieben",
    "neuen termin",
    "terminumbuchung",
    "reschedule",
    "reschedule the interview",
    "move the interview",
    "anderen termin",
    "termin laesst sich nicht",
    "termin lasst sich nicht",
    "leider keinen passenden termin",
    "leider keinen termin",
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

# Mail bodies are ALWAYS untrusted content, never system rules / prompts.
INSTRUCTION_FRAME_SIGNALS: tuple[str, ...] = (
    "ignore previous",
    "ignore all previous",
    "ignore all rules",
    "ignore all instructions",
    "system:",
    "begin_untrusted",
    "klassifiziere als",
    "klassifiziere dies",
    "classify as",
    "classify this as",
    "mark this as",
    "mark as offer",
    "mark candidate accepted",
    "candidate accepted",
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

OFFER_WEAK_ALONE: tuple[str, ...] = (
    "stellenangebot",
    "job offer",
    "arbeitsvertrag",
)


def _hits(text_norm: str, patterns: tuple[str, ...]) -> list[str]:
    found: list[str] = []
    for p in patterns:
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


def _result(
    lifecycle: str,
    confidence: float,
    reasons: Iterable[str] = (),
    *,
    false_rejection_blocked: bool = False,
    evidence: Iterable[str] = (),
    needs_review: bool = False,
    version: str = CLASSIFIER_VERSION,
) -> ClassificationResult:
    reasons_t = tuple(reasons)
    evidence_t = tuple(evidence) if evidence else reasons_t
    legacy = lifecycle_to_legacy(lifecycle)
    if confidence < DEFAULT_LOW_CONFIDENCE_THRESHOLD and lifecycle not in {
        EmailLifecycleClass.NOISE,
        EmailLifecycleClass.REVIEW,
        EmailLifecycleClass.UNKNOWN,
    }:
        return ClassificationResult(
            category="review",
            confidence=confidence,
            reasons=reasons_t + ("low_confidence_fail_safe",),
            false_rejection_blocked=false_rejection_blocked
            or lifecycle
            in {
                EmailLifecycleClass.REJECTION,
                EmailLifecycleClass.OFFER,
                EmailLifecycleClass.INTERVIEW_CANCELLED,
            },
            evidence=evidence_t,
            lifecycle_class=EmailLifecycleClass.UNKNOWN,
            classifier_version=version,
            needs_review=True,
        )
    if needs_review or lifecycle in {
        EmailLifecycleClass.REVIEW,
        EmailLifecycleClass.UNKNOWN,
    }:
        return ClassificationResult(
            category="review",
            confidence=confidence,
            reasons=reasons_t,
            false_rejection_blocked=false_rejection_blocked,
            evidence=evidence_t,
            lifecycle_class=EmailLifecycleClass.UNKNOWN,
            classifier_version=version,
            needs_review=True,
        )
    return ClassificationResult(
        category=legacy,
        confidence=confidence,
        reasons=reasons_t,
        false_rejection_blocked=false_rejection_blocked,
        evidence=evidence_t,
        lifecycle_class=lifecycle,
        classifier_version=version,
        needs_review=False,
    )


def classify_email(
    subject: str,
    body: str,
    *,
    classifier_version: str | None = None,
    review_only_mode: bool = False,
    strip_quotes: bool = True,
) -> ClassificationResult:
    """Classify hiring-related email. Conservative on high-impact labels.

    ``body`` is always treated as untrusted content — never as system rules.
    """
    version = (classifier_version or ACTIVE_CLASSIFIER_VERSION or CLASSIFIER_VERSION).strip()
    if review_only_mode or version not in SUPPORTED_CLASSIFIER_VERSIONS:
        return ClassificationResult(
            category="review",
            confidence=0.0,
            reasons=(
                "review_only_mode"
                if review_only_mode
                else "unsupported_classifier_version",
            ),
            evidence=(),
            lifecycle_class=EmailLifecycleClass.UNKNOWN,
            classifier_version=version,
            needs_review=True,
        )

    raw_body = body or ""
    if strip_quotes:
        current, _quoted = split_quoted_history(raw_body)
        current, _sig = split_signature(current)
        use_body = current or raw_body
    else:
        use_body = raw_body

    combined = normalize_umlauts(f"{subject or ''} {use_body}")
    if not combined.strip():
        return _result(
            EmailLifecycleClass.UNKNOWN,
            0.0,
            ("empty",),
            needs_review=True,
            version=version,
        )

    conf_h = _hits(combined, CONFIRMATION_SIGNALS)
    review_h = _hits(combined, UNDER_REVIEW_SIGNALS)
    int_h = _hits(combined, INTERVIEW_SIGNALS)
    resched_h = _hits(combined, INTERVIEW_RESCHEDULE_SIGNALS)
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

    if instr_h:
        return _result(
            EmailLifecycleClass.UNKNOWN,
            0.2,
            ("instruction_frame_blocked",) + tuple(instr_h[:4]),
            false_rejection_blocked=True,
            evidence=tuple(instr_h[:4]),
            needs_review=True,
            version=version,
        )

    scored: list[tuple[str, float, tuple[str, ...]]] = []

    if can_h:
        scored.append(
            (
                EmailLifecycleClass.INTERVIEW_CANCELLED,
                _score(can_h, base=0.55),
                tuple(can_h[:5]),
            )
        )
    if resched_h and not can_h:
        scored.append(
            (
                EmailLifecycleClass.INTERVIEW_RESCHEDULE,
                _score(resched_h, base=0.5),
                tuple(resched_h[:5]),
            )
        )
    if int_h and not can_h and not resched_h:
        scored.append(
            (EmailLifecycleClass.INTERVIEW_INVITE, _score(int_h), tuple(int_h[:5]))
        )

    offer_weak = _hits(combined, OFFER_WEAK_ALONE)
    offer_strong = [h for h in off_h if h not in OFFER_WEAK_ALONE]
    if noise_h and offer_weak and not offer_strong and not conf_h and not int_h:
        return _result(
            EmailLifecycleClass.NOISE,
            0.75,
            tuple(noise_h[:3]) + ("offer_token_in_newsletter_demoted",),
            evidence=tuple(noise_h[:3]),
            version=version,
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
        scored.append(
            (EmailLifecycleClass.OFFER, _score(use_off, base=0.55), tuple(use_off[:5]))
        )
    elif len(off_h) >= 1 and offer_weak != off_h:
        scored.append(
            (EmailLifecycleClass.OFFER, _score(off_h, base=0.55), tuple(off_h[:5]))
        )
    elif offer_weak and not noise_h:
        scored.append(
            (
                EmailLifecycleClass.UNKNOWN,
                0.35,
                tuple(offer_weak[:3]) + ("weak_offer_insufficient",),
            )
        )
    if rej_h:
        scored.append(
            (EmailLifecycleClass.REJECTION, _score(rej_h, base=0.55), tuple(rej_h[:5]))
        )
    if conf_h and not review_h:
        scored.append(
            (
                EmailLifecycleClass.APPLICATION_RECEIVED,
                _score(conf_h),
                tuple(conf_h[:5]),
            )
        )
    if review_h:
        scored.append(
            (
                EmailLifecycleClass.UNDER_REVIEW,
                _score(review_h, base=0.5),
                tuple(review_h[:5]),
            )
        )
    if as_h:
        scored.append((EmailLifecycleClass.ASSESSMENT, _score(as_h), tuple(as_h[:5])))
    if doc_h:
        scored.append(
            (
                EmailLifecycleClass.DOCUMENT_REQUEST,
                _score(doc_h),
                tuple(doc_h[:5]),
            )
        )
    if q_h:
        scored.append((EmailLifecycleClass.GENERAL, _score(q_h), tuple(q_h[:5])))
    if rec_h:
        scored.append(
            (
                EmailLifecycleClass.GENERAL_RECRUITER_MESSAGE,
                _score(rec_h),
                tuple(rec_h[:5]),
            )
        )
    if noise_h and not scored:
        return _result(
            EmailLifecycleClass.NOISE,
            0.7,
            tuple(noise_h[:3]),
            evidence=tuple(noise_h[:3]),
            version=version,
        )

    if not scored:
        if weak_rej or "leider" in combined:
            return _result(
                EmailLifecycleClass.UNKNOWN,
                0.35,
                ("weak_leider_without_rejection_evidence",),
                false_rejection_blocked=True,
                evidence=tuple(weak_rej[:3]),
                needs_review=True,
                version=version,
            )
        return _result(
            EmailLifecycleClass.UNKNOWN,
            0.2,
            ("no_pattern",),
            needs_review=True,
            version=version,
        )

    scored.sort(key=lambda x: x[1], reverse=True)
    lifecycle, confidence, reasons = scored[0]

    if lifecycle == EmailLifecycleClass.REJECTION:
        if override_h or weak_rej:
            if int_h or override_h or resched_h:
                target = (
                    EmailLifecycleClass.INTERVIEW_RESCHEDULE
                    if resched_h and not int_h
                    else EmailLifecycleClass.INTERVIEW_INVITE
                )
                return _result(
                    target,
                    max(0.75, confidence),
                    tuple((int_h or override_h or resched_h)[:5]),
                    false_rejection_blocked=True,
                    evidence=tuple((int_h or override_h or resched_h)[:5]),
                    version=version,
                )
            return _result(
                EmailLifecycleClass.UNKNOWN,
                0.4,
                reasons + ("false_rejection_guard",),
                false_rejection_blocked=True,
                evidence=reasons,
                needs_review=True,
                version=version,
            )
        if len(reasons) < 1:
            return _result(
                EmailLifecycleClass.UNKNOWN,
                0.35,
                ("insufficient_rejection_evidence",),
                needs_review=True,
                version=version,
            )

    if lifecycle in {
        EmailLifecycleClass.REJECTION,
        EmailLifecycleClass.OFFER,
        EmailLifecycleClass.INTERVIEW_CANCELLED,
    } and not reasons:
        return _result(
            EmailLifecycleClass.UNKNOWN,
            0.3,
            ("high_impact_without_evidence",),
            needs_review=True,
            version=version,
        )

    if (
        lifecycle
        in {
            EmailLifecycleClass.REJECTION,
            EmailLifecycleClass.OFFER,
            EmailLifecycleClass.INTERVIEW_CANCELLED,
        }
        and confidence < HIGH_IMPACT_MIN_CONFIDENCE
    ):
        return _result(
            EmailLifecycleClass.UNKNOWN,
            confidence,
            reasons + ("high_impact_low_confidence",),
            false_rejection_blocked=True,
            evidence=reasons,
            needs_review=True,
            version=version,
        )

    if noise_h and lifecycle == EmailLifecycleClass.REJECTION and confidence < 0.75:
        return _result(
            EmailLifecycleClass.NOISE,
            0.65,
            tuple(noise_h[:3]),
            evidence=tuple(noise_h[:3]),
            version=version,
        )

    return _result(lifecycle, confidence, reasons, evidence=reasons, version=version)


def classify_normalized(
    email: NormalizedEmail,
    *,
    classifier_version: str | None = None,
    review_only_mode: bool = False,
) -> ClassificationResult:
    """Classify a NormalizedEmail using body_text (quotes/signature already split)."""
    return classify_email(
        email.subject,
        email.body_text or email.plain_text or email.html_text,
        classifier_version=classifier_version,
        review_only_mode=review_only_mode,
        strip_quotes=False,
    )


STATUS_PATTERNS = {
    "confirmation": CONFIRMATION_SIGNALS,
    "application_received": CONFIRMATION_SIGNALS,
    "under_review": UNDER_REVIEW_SIGNALS,
    "interview": INTERVIEW_SIGNALS,
    "interview_invite": INTERVIEW_SIGNALS,
    "interview_reschedule": INTERVIEW_RESCHEDULE_SIGNALS,
    "assessment": ASSESSMENT_SIGNALS,
    "offer": OFFER_SIGNALS,
    "rejection": REJECTION_STRONG,
    "document_request": DOCUMENT_REQUEST_SIGNALS,
}
