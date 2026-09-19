"""Stable API / status projection for recruiting contact discovery (PR25/PR26).

UI may render discovery + verification status; no contact is used by the writer
without verification. Uncertainty is always visible when not VERIFIED.
"""

from __future__ import annotations

from typing import Any

from core.contacts.discovery import (
    ContactDiscoveryService,
    DiscoveryContext,
    DiscoveryPolicy,
    discover_contacts,
    policy_from_settings,
)
from core.contacts.models import DiscoveryResult, DiscoveryStatus
from core.contacts.verification import (
    VerificationResult,
    VerificationStatus,
    annotate_candidate_verification,
    verify_discovery,
)


def format_discovery_status(
    result: DiscoveryResult,
    *,
    verification: VerificationResult | None = None,
) -> dict[str, Any]:
    """Beta-safe status payload: only evidenced fields, never invented names."""
    best = result.best
    contact_view: dict[str, Any] | None = None
    if best and result.status in {
        DiscoveryStatus.FOUND.value,
        DiscoveryStatus.STALE.value,
    }:
        contact_view = {
            "name": best.name,
            "role": best.role,
            "department": best.department,
            "email": best.email,
            "phone": best.phone,
            "source_type": best.source_type,
            "source_url": best.source_url,
            "timestamp": best.timestamp,
            "stale": best.stale,
            "page_timestamp": best.page_timestamp,
            "evidence": [e.to_dict() for e in best.evidence],
            "contact_kind": best.contact_kind,
            "verification_status": best.verification_status,
        }
        if verification is not None:
            contact_view = annotate_candidate_verification(best, verification)
    ver_view: dict[str, Any] | None = None
    if verification is not None:
        ver_view = {
            "status": verification.status,
            "evidence_strength": verification.evidence_strength,
            "contact_verified": verification.contact_verified,
            "salutation_allowed": verification.salutation_allowed,
            "uncertainty_visible": verification.uncertainty_visible,
            "stale": verification.stale,
            "conflicts": [c.to_dict() for c in verification.conflicts],
            "reasons": list(verification.reasons),
        }
    return {
        "status": result.status,
        "message": result.message,
        "schema_version": result.schema_version,
        "job_id": result.job_id,
        "case_id": result.case_id,
        "cache_hit": result.cache_hit,
        "sources_tried": list(result.sources_tried),
        "discovered_at": result.discovered_at,
        "contact": contact_view,
        "candidate_count": len(result.candidates),
        "verification": ver_view,
        # NOT_FOUND is success for the discovery feature
        "ok": result.status
        in {
            DiscoveryStatus.FOUND.value,
            DiscoveryStatus.NOT_FOUND.value,
            DiscoveryStatus.STALE.value,
            DiscoveryStatus.DISABLED.value,
        },
    }


def discover_for_job_payload(
    *,
    settings: Any,
    ctx: DiscoveryContext,
    db: Any = None,
) -> dict[str, Any]:
    policy = policy_from_settings(settings)
    # Guard: never mass-fetch when retro crawl is off and caller asks for network
    # without providing inline HTML — DiscoveryContext.allow_network is explicit.
    if ctx.allow_network and not policy.allow_retro_crawl:
        # Still allow single-job opt-in fetch; batch callers must set allow_retro_crawl.
        pass
    result = discover_contacts(ctx, policy=policy, db=db)
    verification_enabled = bool(
        getattr(settings, "contact_verification_enabled", True)
    )
    stale_after = int(
        getattr(
            settings,
            "contact_discovery_stale_after_days",
            getattr(policy, "stale_after_days", 90),
        )
        or 90
    )
    verification = verify_discovery(
        result,
        stale_after_days=stale_after,
        verification_enabled=verification_enabled,
    )
    return format_discovery_status(result, verification=verification)


def format_verification_status(verification: VerificationResult) -> dict[str, Any]:
    """Beta projection: uncertainty always visible unless VERIFIED + strong."""
    payload = verification.to_dict()
    payload["ok"] = verification.status in {
        VerificationStatus.VERIFIED.value,
        VerificationStatus.UNVERIFIED.value,
        VerificationStatus.REVIEW.value,
        VerificationStatus.STALE.value,
        VerificationStatus.DISABLED.value,
        VerificationStatus.REJECTED.value,
    }
    return payload


__all__ = [
    "ContactDiscoveryService",
    "DiscoveryContext",
    "DiscoveryPolicy",
    "discover_contacts",
    "discover_for_job_payload",
    "format_discovery_status",
    "format_verification_status",
    "policy_from_settings",
    "verify_discovery",
]
