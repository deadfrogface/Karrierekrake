"""Zero-tolerance gates for real Windows black-box acceptance (NEXT-06)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class BlackboxZeroGates:
    false_rejection: int = 0
    false_offer: int = 0
    false_confident_association: int = 0
    cross_case_mutation: int = 0
    duplicate_calendar_event: int = 0
    duplicate_paid_maps_request: int = 0
    real_employer_mail: int = 0
    real_application_submission: int = 0
    pii_committed: int = 0
    details: list[str] = field(default_factory=list)

    def bump(self, gate: str, detail: str) -> None:
        if not hasattr(self, gate):
            raise KeyError(gate)
        setattr(self, gate, int(getattr(self, gate)) + 1)
        self.details.append(f"{gate}: {detail}")

    def as_dict(self) -> dict[str, Any]:
        keys = (
            "false_rejection",
            "false_offer",
            "false_confident_association",
            "cross_case_mutation",
            "duplicate_calendar_event",
            "duplicate_paid_maps_request",
            "real_employer_mail",
            "real_application_submission",
            "pii_committed",
        )
        return {k: getattr(self, k) for k in keys} | {"details": list(self.details)}

    def assert_all_zero(self) -> None:
        bad = {k: v for k, v in self.as_dict().items() if k != "details" and v}
        if bad:
            raise AssertionError(f"BLACKBOX ZERO GATE FAILED: {bad}; {self.details[:40]}")
