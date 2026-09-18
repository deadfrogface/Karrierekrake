"""Recruiting contact discovery (PR25) — provenance-backed ContactCandidate.

Public API: discover contacts for a job with source priority, evidence for every
field, NOT_FOUND as a successful outcome, feature toggle, and cache/rate limits.
"""

from __future__ import annotations

from core.contacts.discovery import (
    ContactDiscoveryService,
    DiscoveryContext,
    discover_contacts,
)
from core.contacts.models import (
    CONTACT_SCHEMA_VERSION,
    ContactCandidate,
    ContactEvidence,
    ContactKind,
    DiscoveryResult,
    DiscoveryStatus,
    SourceType,
    SOURCE_PRIORITY,
)

__all__ = [
    "CONTACT_SCHEMA_VERSION",
    "ContactCandidate",
    "ContactDiscoveryService",
    "ContactEvidence",
    "ContactKind",
    "DiscoveryContext",
    "DiscoveryResult",
    "DiscoveryStatus",
    "SOURCE_PRIORITY",
    "SourceType",
    "discover_contacts",
]
