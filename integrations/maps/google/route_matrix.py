"""Compute Route Matrix Essentials constants (NEXT-05).

No accidental TRAFFIC_AWARE_OPTIMAL / Pro / Enterprise features.
"""

from __future__ import annotations

ROUTING_PREFERENCE_ESSENTIALS = "TRAFFIC_UNAWARE"
TRAVEL_MODE = "DRIVE"
DATA_SOURCE = "google_route_matrix"
DATA_VERSION = "routes-matrix-essentials-v1"

# Forbidden without explicit cost approval.
FORBIDDEN_ROUTING_PREFERENCES = frozenset(
    {
        "TRAFFIC_AWARE",
        "TRAFFIC_AWARE_OPTIMAL",
    }
)
