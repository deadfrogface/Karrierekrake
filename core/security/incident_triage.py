"""Offline incident triage with minimal non-sensitive fields."""
from __future__ import annotations

from datetime import datetime, timezone

SEVERITIES = frozenset(("critical", "high", "medium", "low"))
COMPONENTS = frozenset(("updater", "model", "browser", "data", "desktop", "dependency", "other"))


def incident_record(*, severity: str, component: str, release: str) -> dict:
    if severity not in SEVERITIES or component not in COMPONENTS:
        raise ValueError("invalid_incident_classification")
    if not isinstance(release, str) or not release or len(release) > 80 or any(c in release for c in "\r\n/@\\") or any(ord(c) < 32 or ord(c) == 127 for c in release):
        raise ValueError("invalid_release_identifier")
    return {"schema": "karrierekrake.incident.v1", "severity": severity,
            "component": component, "release": release,
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "status": "open"}
