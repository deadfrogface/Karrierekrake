"""Recruiting contact discovery + verification (PR25/PR26).

Pipeline: Discovery → Verification → Usage Policy → Writer.
Discovered ContactCandidates are never used automatically.
"""

from __future__ import annotations

from core.contacts.discovery import (
    ContactDiscoveryService,
    DiscoveryContext,
    discover_contacts,
)
from core.contacts.models import (
    CONTACT_SCHEMA_VERSION,
    DEFAULT_VERIFICATION_STATUS,
    ContactCandidate,
    ContactEvidence,
    ContactKind,
    DiscoveryResult,
    DiscoveryStatus,
    SourceType,
    SOURCE_PRIORITY,
)
from core.contacts.writer_contract import (
    NEUTRAL_SALUTATION,
    WriterContactClaims,
    build_writer_claims,
    claims_from_discovery,
    writer_invented_contact_violations,
)
from core.contacts.verification import (
    VERIFICATION_SCHEMA_VERSION,
    ConflictRecord,
    EvidenceStrength,
    VerificationResult,
    VerificationStatus,
    annotate_candidate_verification,
    evidence_strength_for_source,
    has_explicit_salutation_evidence,
    verify_candidate,
    verify_discovery,
)

__all__ = [
    "CONTACT_SCHEMA_VERSION",
    "DEFAULT_VERIFICATION_STATUS",
    "NEUTRAL_SALUTATION",
    "VERIFICATION_SCHEMA_VERSION",
    "ConflictRecord",
    "ContactCandidate",
    "ContactDiscoveryService",
    "ContactEvidence",
    "ContactKind",
    "DiscoveryContext",
    "DiscoveryResult",
    "DiscoveryStatus",
    "EvidenceStrength",
    "SOURCE_PRIORITY",
    "SourceType",
    "VerificationResult",
    "VerificationStatus",
    "WriterContactClaims",
    "build_writer_claims",
    "claims_from_discovery",
    "annotate_candidate_verification",
    "discover_contacts",
    "evidence_strength_for_source",
    "has_explicit_salutation_evidence",
    "verify_candidate",
    "verify_discovery",
    "writer_invented_contact_violations",
]
