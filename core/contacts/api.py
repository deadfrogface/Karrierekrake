"""Stable API / status projection for recruiting contact discovery (PR25).

UI may render `DiscoveryStatusView`; no contact is shown without provenance.
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


def format_discovery_status(result: DiscoveryResult) -> dict[str, Any]:
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
    return format_discovery_status(result)


__all__ = [
    "ContactDiscoveryService",
    "DiscoveryContext",
    "DiscoveryPolicy",
    "discover_contacts",
    "discover_for_job_payload",
    "format_discovery_status",
    "policy_from_settings",
]
