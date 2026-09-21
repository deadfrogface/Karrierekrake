"""Dev / owner entitlements — unlock paid features without purchase (NEXT-07).

Development and test builds only.
Production packaged artifacts MUST reject Dev entitlement.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from enum import Enum


class Entitlement(str, Enum):
    FREE = "free"
    PAID = "paid"
    DEV = "dev"  # owner/dev unlock — never from production EXE purchase path


def is_production_artifact() -> bool:
    """True for frozen/packaged EXE that is not explicitly a labeled test build."""
    frozen = bool(getattr(sys, "frozen", False))
    # Allow explicit test/signed-dev channel marker in non-store test EXEs only.
    labeled_test = os.environ.get("KARRIEREKRAKE_BUILD_CHANNEL", "").strip().lower() in {
        "dev",
        "test",
        "ci",
    }
    if frozen and not labeled_test:
        return True
    if os.environ.get("KARRIEREKRAKE_FORCE_PRODUCTION_ENTITLEMENT", "").strip() in {
        "1",
        "true",
        "yes",
    }:
        return True
    return False


def is_dev_entitlement_allowed() -> bool:
    """Dev unlock only when not a production artifact AND flag set."""
    if is_production_artifact():
        return False
    return os.environ.get("KARRIEREKRAKE_DEV_ENTITLEMENT", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


@dataclass(frozen=True)
class EntitlementDecision:
    entitlement: Entitlement
    paid_features_unlocked: bool
    reason: str


def entitlement_for_runtime(*, has_paid_license: bool = False) -> EntitlementDecision:
    """Resolve entitlement. Production never accepts Dev."""
    if has_paid_license:
        return EntitlementDecision(Entitlement.PAID, True, "paid_license")
    if is_dev_entitlement_allowed():
        return EntitlementDecision(Entitlement.DEV, True, "dev_entitlement")
    if os.environ.get("KARRIEREKRAKE_DEV_ENTITLEMENT", "").strip() and is_production_artifact():
        return EntitlementDecision(
            Entitlement.FREE,
            False,
            "dev_entitlement_rejected_in_production",
        )
    return EntitlementDecision(Entitlement.FREE, False, "free")
