"""Writer contact claims — only verified contacts may enter cover letters (PR26).

Contract fields (always present):
  CONTACT_VERIFIED, CONTACT_NAME, CONTACT_ROLE, CONTACT_SOURCE, SALUTATION_ALLOWED

When CONTACT_VERIFIED is false the writer must not add a person. Neutral
salutation falls back to the existing product style.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from core.contacts.models import DiscoveryResult
from core.contacts.verification import (
    EvidenceStrength,
    VerificationResult,
    VerificationStatus,
    verify_discovery,
)
from core.text_normalize import clean_text

# Existing product-style neutral opening (templates/cover_letter.txt).
NEUTRAL_SALUTATION = "Sehr geehrte Damen und Herren"
NEUTRAL_TEAM_PHRASE = "das Recruiting-Team"

_PERSONAL_SALUTATION_RE = re.compile(
    r"(?i)\bsehr\s+geehrte[rn]?\s+(frau|herr)\s+([A-ZÄÖÜ][\w\-']+(?:\s+[A-ZÄÖÜ][\w\-']+)*)"
)
_FRAU_HERR_NAME_RE = re.compile(
    r"(?i)\b(frau|herr)\s+([A-ZÄÖÜ][\w\-']+(?:\s+[A-ZÄÖÜ][\w\-']+)*)"
)


@dataclass
class WriterContactClaims:
    """Deterministic claims injected into plan/draft trusted context."""

    CONTACT_VERIFIED: bool = False
    CONTACT_NAME: str = ""
    CONTACT_ROLE: str = ""
    CONTACT_SOURCE: str = ""
    SALUTATION_ALLOWED: bool = False
    verification_status: str = VerificationStatus.UNVERIFIED.value
    evidence_strength: str = EvidenceStrength.NONE.value
    uncertainty_visible: bool = True
    neutral_salutation: str = NEUTRAL_SALUTATION
    reasons: list[str] = field(default_factory=list)
    writer_binding_enabled: bool = True

    def opening_line(self) -> str:
        """Salutation line for template / seed body — never invents gender."""
        if (
            self.writer_binding_enabled
            and self.CONTACT_VERIFIED
            and self.SALUTATION_ALLOWED
            and self.CONTACT_NAME
        ):
            name = self.CONTACT_NAME
            low = name.lower()
            if low.startswith("frau ") or low.startswith("herr "):
                titled = name[0].upper() + name[1:]
                return (
                    f"Sehr geehrter {titled},"
                    if titled.lower().startswith("herr")
                    else f"Sehr geehrte {titled},"
                )
            # Explicit salutation evidence without title on name → still neutral
            return f"{self.neutral_salutation},"
        return f"{self.neutral_salutation},"

    def to_trusted_block(self) -> str:
        """Key=value block for Günther TRUSTED context."""
        lines = [
            f"CONTACT_VERIFIED={'true' if self.CONTACT_VERIFIED else 'false'}",
            f"CONTACT_NAME={self.CONTACT_NAME if self.CONTACT_VERIFIED else ''}",
            f"CONTACT_ROLE={self.CONTACT_ROLE if self.CONTACT_VERIFIED else ''}",
            f"CONTACT_SOURCE={self.CONTACT_SOURCE if self.CONTACT_VERIFIED else ''}",
            f"SALUTATION_ALLOWED={'true' if self.SALUTATION_ALLOWED and self.CONTACT_VERIFIED else 'false'}",
            f"VERIFICATION_STATUS={self.verification_status}",
            f"EVIDENCE_STRENGTH={self.evidence_strength}",
            f"UNCERTAINTY_VISIBLE={'true' if self.uncertainty_visible else 'false'}",
            f"NEUTRAL_SALUTATION={self.neutral_salutation}",
            "RULE: If CONTACT_VERIFIED is false you MUST NOT invent or add any person name.",
            "RULE: If SALUTATION_ALLOWED is false use NEUTRAL_SALUTATION only.",
            "RULE: Never guess gender from first names.",
        ]
        if self.reasons:
            lines.append("CONTACT_REASONS=" + "; ".join(self.reasons[:5]))
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["opening_line"] = self.opening_line()
        return d

    @classmethod
    def empty(cls, *, writer_binding_enabled: bool = True) -> "WriterContactClaims":
        return cls(
            CONTACT_VERIFIED=False,
            uncertainty_visible=True,
            writer_binding_enabled=writer_binding_enabled,
            reasons=["no verified contact"],
        )


def build_writer_claims(
    verification: VerificationResult | None,
    *,
    writer_binding_enabled: bool = True,
) -> WriterContactClaims:
    """Map VerificationResult → writer contract. Binding off → always unverified claims."""
    if not writer_binding_enabled:
        return WriterContactClaims(
            CONTACT_VERIFIED=False,
            verification_status=(
                verification.status if verification else VerificationStatus.DISABLED.value
            ),
            evidence_strength=(
                verification.evidence_strength
                if verification
                else EvidenceStrength.NONE.value
            ),
            uncertainty_visible=True,
            reasons=["writer binding disabled (rollback); provenance preserved"],
            writer_binding_enabled=False,
        )
    if verification is None:
        return WriterContactClaims.empty()

    verified = verification.contact_verified
    cand = verification.candidate if verified else None
    return WriterContactClaims(
        CONTACT_VERIFIED=bool(verified),
        CONTACT_NAME=clean_text(cand.name) if cand and verified else "",
        CONTACT_ROLE=clean_text(cand.role) if cand and verified else "",
        CONTACT_SOURCE=clean_text(cand.source_type) if cand and verified else "",
        SALUTATION_ALLOWED=bool(verified and verification.salutation_allowed),
        verification_status=verification.status,
        evidence_strength=verification.evidence_strength,
        uncertainty_visible=bool(verification.uncertainty_visible or not verified),
        reasons=list(verification.reasons),
        writer_binding_enabled=True,
    )


def claims_from_discovery(
    result: DiscoveryResult | None,
    *,
    settings: Any = None,
    stale_after_days: int = 90,
    verification_enabled: bool = True,
    writer_binding_enabled: bool = True,
) -> WriterContactClaims:
    if settings is not None:
        verification_enabled = bool(
            getattr(settings, "contact_verification_enabled", verification_enabled)
        )
        writer_binding_enabled = bool(
            getattr(settings, "contact_writer_binding_enabled", writer_binding_enabled)
        )
        stale_after_days = int(
            getattr(settings, "contact_discovery_stale_after_days", stale_after_days)
            or stale_after_days
        )
    verification = verify_discovery(
        result,
        stale_after_days=stale_after_days,
        verification_enabled=verification_enabled,
    )
    return build_writer_claims(
        verification, writer_binding_enabled=writer_binding_enabled
    )


def extract_personal_salutations(text: str) -> list[tuple[str, str]]:
    """Return list of (title, name) personal salutations found in text."""
    out: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for m in _PERSONAL_SALUTATION_RE.finditer(text or ""):
        item = (m.group(1).lower(), m.group(2).strip())
        if item not in seen:
            seen.add(item)
            out.append(item)
    for m in _FRAU_HERR_NAME_RE.finditer(text or ""):
        item = (m.group(1).lower(), m.group(2).strip())
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def writer_invented_contact_violations(
    body: str,
    claims: WriterContactClaims,
    *,
    applicant_name: str = "",
) -> list[str]:
    """Detect adversarial / accidental person injection against the contract."""
    violations: list[str] = []
    text = body or ""
    if not text.strip():
        return violations

    applicant = clean_text(applicant_name).lower()
    personal = extract_personal_salutations(text)

    if not claims.CONTACT_VERIFIED:
        for title, name in personal:
            if applicant and name.lower() == applicant:
                continue
            violations.append(f"UNVERIFIED_PERSON_SALUTATION:{title} {name}")
        if re.search(
            r"(?i)\b(ansprechpartner(?:in)?|kontaktperson)\s*:\s*[A-ZÄÖÜ]", text
        ):
            violations.append("UNVERIFIED_CONTACT_LABEL")
        return violations

    if not claims.SALUTATION_ALLOWED:
        for title, name in personal:
            violations.append(f"SALUTATION_NOT_ALLOWED:{title} {name}")
        return violations

    allowed = clean_text(claims.CONTACT_NAME).lower()
    for title, name in personal:
        if allowed and (name.lower() == allowed or allowed in name.lower()):
            continue
        violations.append(f"WRONG_PERSON_SALUTATION:{title} {name}")
    return violations


def sanitize_cover_body_for_claims(
    body: str,
    claims: WriterContactClaims,
    *,
    applicant_name: str = "",
) -> str:
    """Fail-closed rewrite: strip invented personal salutations to neutral."""
    text = body or ""
    viol = writer_invented_contact_violations(
        text, claims, applicant_name=applicant_name
    )
    if not viol:
        return text
    text = _PERSONAL_SALUTATION_RE.sub(claims.neutral_salutation, text)
    stripped = text.lstrip()
    if not stripped.lower().startswith("sehr geehrte"):
        text = f"{claims.neutral_salutation},\n\n{stripped}"
    return text


def apply_claims_to_template_mapping(
    mapping: dict[str, str],
    claims: WriterContactClaims,
) -> dict[str, str]:
    """Extend cover-letter template mapping with contact fields."""
    out = dict(mapping)
    out["salutation"] = claims.opening_line().rstrip(",")
    out["contact_name"] = claims.CONTACT_NAME if claims.CONTACT_VERIFIED else ""
    out["contact_role"] = claims.CONTACT_ROLE if claims.CONTACT_VERIFIED else ""
    out["contact_verified"] = "true" if claims.CONTACT_VERIFIED else "false"
    return out


__all__ = [
    "NEUTRAL_SALUTATION",
    "NEUTRAL_TEAM_PHRASE",
    "WriterContactClaims",
    "build_writer_claims",
    "claims_from_discovery",
    "extract_personal_salutations",
    "writer_invented_contact_violations",
    "sanitize_cover_body_for_claims",
    "apply_claims_to_template_mapping",
]
