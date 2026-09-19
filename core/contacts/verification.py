"""Deterministic contact verification policy (PR26).

Pipeline: Discovery → Verification → Usage Policy → Writer.

Discovered ContactCandidates are NEVER used automatically. Strong evidence
(same job posting / ATS) may become VERIFIED. Weaker company-page contacts may
be shown but are not job-specific writer contacts. Conflicts → REVIEW / neutral.
No gender guessing. Existing rows default to UNVERIFIED.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from core.contacts.classify import is_generic_mailbox
from core.contacts.models import (
    ContactCandidate,
    ContactEvidence,
    ContactKind,
    DiscoveryResult,
    SourceType,
)
from core.models import utc_now_iso
from core.text_normalize import clean_text

VERIFICATION_SCHEMA_VERSION = 1

# Explicit salutation tokens in evidence quotes — never inferred from first names.
_EXPLICIT_SALUTATION_RE = re.compile(
    r"(?i)\b("
    r"frau|herr|"
    r"mr\.?|mrs\.?|ms\.?|miss|"
    r"madame|monsieur|"
    r"signora|signore|"
    r"sehr\s+geehrte[rn]?\s+(?:frau|herr)"
    r")\b"
)

# Patterns that look like gender/name inference (forbidden).
_INFERRED_GENDER_HINTS = (
    "klingt weiblich",
    "klingt männlich",
    "sounds female",
    "sounds male",
    "first name gender",
    "vorname geschlecht",
    "gender guess",
    "geschlechtsguess",
)


class VerificationStatus(str, Enum):
    """Verification outcome for a candidate or discovery set."""

    VERIFIED = "VERIFIED"
    UNVERIFIED = "UNVERIFIED"  # migration default / incomplete
    REVIEW = "REVIEW"  # conflicts, ambiguity, homonyms
    REJECTED = "REJECTED"  # generic mailbox, invented, gender guess
    STALE = "STALE"
    DISABLED = "DISABLED"


class EvidenceStrength(str, Enum):
    """How strong the provenance is for job-specific contact usage."""

    STRONG = "STRONG"  # same job posting / ATS record
    WEAK = "WEAK"  # company career/contact page or signature
    NONE = "NONE"


STRONG_SOURCE_TYPES: frozenset[str] = frozenset(
    {
        SourceType.JOB_POSTING_TEXT.value,
        SourceType.JOB_POSTING_JSONLD.value,
        SourceType.ATS_METADATA.value,
    }
)

WEAK_SOURCE_TYPES: frozenset[str] = frozenset(
    {
        SourceType.COMPANY_CAREER_PAGE.value,
        SourceType.COMPANY_CONTACT_PAGE.value,
        SourceType.RECRUITER_SIGNATURE.value,
    }
)


def evidence_strength_for_source(source_type: str) -> EvidenceStrength:
    st = clean_text(source_type)
    if st in STRONG_SOURCE_TYPES:
        return EvidenceStrength.STRONG
    if st in WEAK_SOURCE_TYPES:
        return EvidenceStrength.WEAK
    return EvidenceStrength.NONE


def _norm_name(name: str) -> str:
    return re.sub(r"\s+", " ", clean_text(name).lower())


def _parse_iso_date(value: str) -> datetime | None:
    raw = (value or "").strip()
    if not raw:
        return None
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        # Allow YYYY-MM-DD
        try:
            return datetime.fromisoformat(raw[:10]).replace(tzinfo=timezone.utc)
        except ValueError:
            return None


def is_stale_candidate(
    candidate: ContactCandidate,
    *,
    stale_after_days: int = 90,
    now: datetime | None = None,
) -> bool:
    if candidate.stale:
        return True
    ref = _parse_iso_date(candidate.page_timestamp) or _parse_iso_date(candidate.timestamp)
    if ref is None:
        return False
    current = now or datetime.now(timezone.utc)
    age = (current - ref).days
    return age > max(0, int(stale_after_days))


def has_explicit_salutation_evidence(candidate: ContactCandidate) -> bool:
    """True only when a quote explicitly contains Herr/Frau/… near the contact."""
    name = _norm_name(candidate.name)
    for ev in candidate.evidence:
        quote = (ev.quote or "").strip()
        if not quote:
            continue
        if not _EXPLICIT_SALUTATION_RE.search(quote):
            continue
        # Require the quote to mention the person or be a name-field salutation
        if ev.field == "name" or (name and name in _norm_name(quote)):
            return True
        # Short quotes that are just "Frau Müller"-style on name field
        if ev.field in {"name", "role", "salutation"} and _EXPLICIT_SALUTATION_RE.search(quote):
            return True
    return False


def detects_gender_inference(notes: str | list[str] | None = None) -> bool:
    blob = ""
    if isinstance(notes, list):
        blob = " ".join(str(n) for n in notes).lower()
    elif notes:
        blob = str(notes).lower()
    return any(h in blob for h in _INFERRED_GENDER_HINTS)


@dataclass
class ConflictRecord:
    kind: str
    detail: str
    candidate_names: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class VerificationResult:
    """Outcome of verifying one or more ContactCandidates for a job."""

    status: str = VerificationStatus.UNVERIFIED.value
    evidence_strength: str = EvidenceStrength.NONE.value
    candidate: ContactCandidate | None = None
    candidates: list[ContactCandidate] = field(default_factory=list)
    conflicts: list[ConflictRecord] = field(default_factory=list)
    stale: bool = False
    salutation_allowed: bool = False
    salutation_evidence: bool = False
    uncertainty_visible: bool = True
    reasons: list[str] = field(default_factory=list)
    schema_version: int = VERIFICATION_SCHEMA_VERSION
    verified_at: str = field(default_factory=utc_now_iso)
    job_id: str = ""
    case_id: str = ""
    # Display-only company-page contact (not writer-usable as job contact)
    display_candidate: ContactCandidate | None = None
    verification_enabled: bool = True

    def __post_init__(self) -> None:
        if isinstance(self.candidates, list):
            self.candidates = [
                c if isinstance(c, ContactCandidate) else ContactCandidate.from_dict(c)
                for c in self.candidates
            ]
        if self.candidate is not None and not isinstance(self.candidate, ContactCandidate):
            self.candidate = ContactCandidate.from_dict(self.candidate)
        if self.display_candidate is not None and not isinstance(
            self.display_candidate, ContactCandidate
        ):
            self.display_candidate = ContactCandidate.from_dict(self.display_candidate)
        if isinstance(self.conflicts, list):
            self.conflicts = [
                c if isinstance(c, ConflictRecord) else ConflictRecord(**c)
                for c in self.conflicts
                if isinstance(c, (ConflictRecord, dict))
            ]

    @property
    def contact_verified(self) -> bool:
        return (
            self.verification_enabled
            and self.status == VerificationStatus.VERIFIED.value
            and self.evidence_strength == EvidenceStrength.STRONG.value
            and self.candidate is not None
            and not self.stale
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "evidence_strength": self.evidence_strength,
            "candidate": self.candidate.to_dict() if self.candidate else None,
            "candidates": [c.to_dict() for c in self.candidates],
            "conflicts": [c.to_dict() for c in self.conflicts],
            "stale": self.stale,
            "salutation_allowed": self.salutation_allowed,
            "salutation_evidence": self.salutation_evidence,
            "uncertainty_visible": self.uncertainty_visible,
            "reasons": list(self.reasons),
            "schema_version": self.schema_version,
            "verified_at": self.verified_at,
            "job_id": self.job_id,
            "case_id": self.case_id,
            "display_candidate": (
                self.display_candidate.to_dict() if self.display_candidate else None
            ),
            "verification_enabled": self.verification_enabled,
            "contact_verified": self.contact_verified,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "VerificationResult":
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)

    @classmethod
    def disabled(
        cls, *, job_id: str = "", case_id: str = "", message: str = "verification disabled"
    ) -> "VerificationResult":
        return cls(
            status=VerificationStatus.DISABLED.value,
            evidence_strength=EvidenceStrength.NONE.value,
            reasons=[message],
            uncertainty_visible=True,
            job_id=job_id,
            case_id=case_id,
            verification_enabled=False,
        )

    @classmethod
    def unverified_default(
        cls,
        *,
        candidate: ContactCandidate | None = None,
        job_id: str = "",
        case_id: str = "",
        reason: str = "legacy or unverified contact (migration default)",
    ) -> "VerificationResult":
        return cls(
            status=VerificationStatus.UNVERIFIED.value,
            evidence_strength=(
                evidence_strength_for_source(candidate.source_type).value
                if candidate
                else EvidenceStrength.NONE.value
            ),
            candidate=None,  # not writer-usable until verified
            display_candidate=candidate,
            candidates=[candidate] if candidate else [],
            reasons=[reason],
            uncertainty_visible=True,
            job_id=job_id,
            case_id=case_id,
        )


def _reject(
    *,
    reason: str,
    candidates: list[ContactCandidate],
    job_id: str,
    case_id: str,
    strength: EvidenceStrength = EvidenceStrength.NONE,
) -> VerificationResult:
    return VerificationResult(
        status=VerificationStatus.REJECTED.value,
        evidence_strength=strength.value,
        candidates=candidates,
        reasons=[reason],
        uncertainty_visible=True,
        job_id=job_id,
        case_id=case_id,
    )


def _review(
    *,
    reason: str,
    candidates: list[ContactCandidate],
    conflicts: list[ConflictRecord],
    job_id: str,
    case_id: str,
    strength: EvidenceStrength = EvidenceStrength.NONE,
    display: ContactCandidate | None = None,
) -> VerificationResult:
    return VerificationResult(
        status=VerificationStatus.REVIEW.value,
        evidence_strength=strength.value,
        candidates=candidates,
        conflicts=conflicts,
        display_candidate=display,
        reasons=[reason],
        uncertainty_visible=True,
        job_id=job_id,
        case_id=case_id,
    )


def verify_candidate(
    candidate: ContactCandidate,
    *,
    stale_after_days: int = 90,
    job_id: str = "",
    case_id: str = "",
    allow_inferred_salutation: bool = False,
    inference_notes: str | list[str] | None = None,
) -> VerificationResult:
    """Verify a single ContactCandidate. Defaults to UNVERIFIED when incomplete."""
    if allow_inferred_salutation or detects_gender_inference(inference_notes):
        return _reject(
            reason="gender/salutation inference is forbidden",
            candidates=[candidate],
            job_id=job_id,
            case_id=case_id,
        )

    if candidate.contact_kind == ContactKind.GENERIC_MAILBOX.value or (
        candidate.email and is_generic_mailbox(candidate.email)
    ):
        return _reject(
            reason="generic mailbox is not a person contact",
            candidates=[candidate],
            job_id=job_id,
            case_id=case_id,
        )

    missing = candidate.validate_evidence()
    if missing:
        return VerificationResult.unverified_default(
            candidate=candidate,
            job_id=job_id,
            case_id=case_id,
            reason=f"missing evidence for fields: {', '.join(missing)}",
        )

    if not candidate.name:
        # Never derive a person from email alone
        return _reject(
            reason="contact name missing; email alone cannot invent a person",
            candidates=[candidate],
            job_id=job_id,
            case_id=case_id,
            strength=evidence_strength_for_source(candidate.source_type),
        )

    strength = evidence_strength_for_source(candidate.source_type)
    stale = is_stale_candidate(candidate, stale_after_days=stale_after_days)
    sal_ev = has_explicit_salutation_evidence(candidate)

    if stale:
        return VerificationResult(
            status=VerificationStatus.STALE.value,
            evidence_strength=strength.value,
            candidate=None,
            display_candidate=candidate,
            candidates=[candidate],
            stale=True,
            salutation_allowed=False,
            salutation_evidence=sal_ev,
            reasons=["contact evidence is stale"],
            uncertainty_visible=True,
            job_id=job_id,
            case_id=case_id,
        )

    if strength == EvidenceStrength.WEAK:
        # May be displayed as company recruiting contact, not job-specific writer use
        return VerificationResult(
            status=VerificationStatus.UNVERIFIED.value,
            evidence_strength=EvidenceStrength.WEAK.value,
            candidate=None,
            display_candidate=candidate,
            candidates=[candidate],
            salutation_allowed=False,
            salutation_evidence=sal_ev,
            reasons=[
                "company-page / signature contact is display-only; "
                "not automatically a job-specific contact"
            ],
            uncertainty_visible=True,
            job_id=job_id,
            case_id=case_id,
        )

    if strength != EvidenceStrength.STRONG:
        return VerificationResult.unverified_default(
            candidate=candidate,
            job_id=job_id,
            case_id=case_id,
            reason="no strong job/ATS provenance",
        )

    # Strong + evidenced + named + not stale → VERIFIED for writer person usage
    return VerificationResult(
        status=VerificationStatus.VERIFIED.value,
        evidence_strength=EvidenceStrength.STRONG.value,
        candidate=candidate,
        display_candidate=candidate,
        candidates=[candidate],
        stale=False,
        salutation_allowed=bool(sal_ev),
        salutation_evidence=sal_ev,
        reasons=["strong job/ATS evidence; no conflict in single-candidate check"],
        uncertainty_visible=not sal_ev,  # missing salutation → visible uncertainty
        job_id=job_id,
        case_id=case_id,
    )


def _find_homonyms(candidates: list[ContactCandidate]) -> list[ConflictRecord]:
    by_name: dict[str, list[ContactCandidate]] = {}
    for c in candidates:
        key = _norm_name(c.name)
        if not key:
            continue
        by_name.setdefault(key, []).append(c)
    out: list[ConflictRecord] = []
    for name, group in by_name.items():
        if len(group) < 2:
            continue
        emails = {clean_text(c.email).lower() for c in group if c.email}
        roles = {clean_text(c.role).lower() for c in group if c.role}
        sources = {c.source_type for c in group}
        if len(emails) > 1 or len(roles) > 1 or len(sources) > 1:
            out.append(
                ConflictRecord(
                    kind="homonym",
                    detail=f"same name '{name}' with differing email/role/source",
                    candidate_names=[c.name for c in group],
                )
            )
    return out


def _find_source_conflicts(candidates: list[ContactCandidate]) -> list[ConflictRecord]:
    strong = [c for c in candidates if evidence_strength_for_source(c.source_type) == EvidenceStrength.STRONG]
    weak = [c for c in candidates if evidence_strength_for_source(c.source_type) == EvidenceStrength.WEAK]
    conflicts: list[ConflictRecord] = []
    strong_names = {_norm_name(c.name) for c in strong if c.name}
    weak_names = {_norm_name(c.name) for c in weak if c.name}
    if strong_names and weak_names and strong_names != weak_names:
        if not strong_names.issubset(weak_names) and not weak_names.issubset(strong_names):
            conflicts.append(
                ConflictRecord(
                    kind="job_vs_company",
                    detail="job-page contact differs from company-page contact",
                    candidate_names=sorted(
                        {c.name for c in strong + weak if c.name}
                    ),
                )
            )
    # Multiple distinct strong persons → ambiguous
    if len(strong_names) > 1:
        conflicts.append(
            ConflictRecord(
                kind="ambiguous_strong",
                detail="multiple distinct persons with strong job/ATS evidence",
                candidate_names=sorted({c.name for c in strong if c.name}),
            )
        )
    return conflicts


def verify_discovery(
    result: DiscoveryResult | None,
    *,
    stale_after_days: int = 90,
    verification_enabled: bool = True,
    candidates: list[ContactCandidate] | None = None,
) -> VerificationResult:
    """Verify a DiscoveryResult (or raw candidate list) for writer usage."""
    job_id = result.job_id if result else ""
    case_id = result.case_id if result else ""
    if not verification_enabled:
        return VerificationResult.disabled(job_id=job_id, case_id=case_id)

    pool: list[ContactCandidate] = list(candidates or [])
    if result is not None and not pool:
        pool = list(result.candidates or [])

    # Migration: empty / not found → UNVERIFIED (not an error)
    if not pool:
        return VerificationResult(
            status=VerificationStatus.UNVERIFIED.value,
            evidence_strength=EvidenceStrength.NONE.value,
            reasons=["no candidates; default UNVERIFIED"],
            uncertainty_visible=True,
            job_id=job_id,
            case_id=case_id,
        )

    # Filter invented / incomplete early
    usable: list[ContactCandidate] = []
    for c in pool:
        if c.contact_kind == ContactKind.GENERIC_MAILBOX.value:
            continue
        if c.email and is_generic_mailbox(c.email) and not c.name:
            continue
        if c.validate_evidence():
            continue
        if not c.name:
            continue
        usable.append(c)

    if not usable:
        # Keep display of generic-only as rejected
        if any(
            c.contact_kind == ContactKind.GENERIC_MAILBOX.value
            or (c.email and is_generic_mailbox(c.email))
            for c in pool
        ):
            return _reject(
                reason="only generic mailboxes found",
                candidates=pool,
                job_id=job_id,
                case_id=case_id,
            )
        return VerificationResult.unverified_default(
            job_id=job_id,
            case_id=case_id,
            reason="candidates lack usable person evidence",
        )

    conflicts = _find_homonyms(usable) + _find_source_conflicts(usable)
    if conflicts:
        # Prefer showing a strong candidate for UI uncertainty, but no writer use
        strong = [
            c
            for c in usable
            if evidence_strength_for_source(c.source_type) == EvidenceStrength.STRONG
        ]
        display = strong[0] if strong else usable[0]
        return _review(
            reason="conflict or ambiguity requires human review; neutral fallback",
            candidates=usable,
            conflicts=conflicts,
            job_id=job_id,
            case_id=case_id,
            strength=evidence_strength_for_source(display.source_type),
            display=display,
        )

    # Single unambiguous path: verify best by strength then source priority
    strong = [
        c
        for c in usable
        if evidence_strength_for_source(c.source_type) == EvidenceStrength.STRONG
    ]
    if len(strong) == 1:
        return verify_candidate(
            strong[0],
            stale_after_days=stale_after_days,
            job_id=job_id,
            case_id=case_id,
        )
    if len(strong) > 1:
        # Same name (no conflict above) — pick first; still check stale/salutation
        return verify_candidate(
            strong[0],
            stale_after_days=stale_after_days,
            job_id=job_id,
            case_id=case_id,
        )

    # Only weak candidates
    if usable:
        return verify_candidate(
            usable[0],
            stale_after_days=stale_after_days,
            job_id=job_id,
            case_id=case_id,
        )

    return VerificationResult.unverified_default(job_id=job_id, case_id=case_id)


def apply_migration_default(candidate: ContactCandidate | dict[str, Any]) -> ContactCandidate:
    """Existing contacts without verification → UNVERIFIED (display only)."""
    if isinstance(candidate, dict):
        c = ContactCandidate.from_dict(candidate)
    else:
        c = candidate
    # Soft field on dict round-trip via meta in evidence is avoided; callers
    # should run verify_* which defaults to UNVERIFIED.
    return c


def annotate_candidate_verification(
    candidate: ContactCandidate,
    verification: VerificationResult,
) -> dict[str, Any]:
    """Attach verification projection for API/UI without mutating provenance."""
    payload = candidate.to_dict()
    payload["verification_status"] = verification.status
    payload["evidence_strength"] = verification.evidence_strength
    payload["contact_verified"] = verification.contact_verified
    payload["salutation_allowed"] = verification.salutation_allowed
    payload["uncertainty_visible"] = verification.uncertainty_visible
    return payload


__all__ = [
    "VERIFICATION_SCHEMA_VERSION",
    "VerificationStatus",
    "EvidenceStrength",
    "STRONG_SOURCE_TYPES",
    "WEAK_SOURCE_TYPES",
    "ConflictRecord",
    "VerificationResult",
    "evidence_strength_for_source",
    "is_stale_candidate",
    "has_explicit_salutation_evidence",
    "detects_gender_inference",
    "verify_candidate",
    "verify_discovery",
    "apply_migration_default",
    "annotate_candidate_verification",
]
