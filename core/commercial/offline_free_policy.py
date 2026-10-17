"""Conservative, network-free product feature policy.

This is an explicit policy contract for integration by the UI and services.
"""
from __future__ import annotations

FREE_OFFLINE = frozenset({"profile_edit", "local_cv_import", "local_search_filters", "dry_run", "data_export", "data_delete"})
PAID_OPTIONAL = frozenset({"premium_assistance", "premium_integrations"})


def feature_allowed(feature: str, *, paid: bool = False, online: bool = False) -> bool:
    if feature in FREE_OFFLINE:
        return True
    if feature in PAID_OPTIONAL:
        return bool(paid)
    return False


def requires_network(feature: str) -> bool:
    return feature in {"premium_integrations"}
