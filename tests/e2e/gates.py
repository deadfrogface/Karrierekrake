"""Critical zero-tolerance gates for full-product E2E (never soften)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ProductGates:
    false_rejection: int = 0
    false_offer: int = 0
    false_confident_association: int = 0
    cross_case_mutation: int = 0
    duplicate_calendar_event: int = 0
    duplicate_external_action: int = 0
    fake_application_submission: int = 0
    real_email_sent: int = 0
    profile_deletion_resurrection: int = 0
    silent_data_loss: int = 0
    unrecoverable_db_corruption: int = 0
    production_secret_leak: int = 0
    real_pii_fixture: int = 0
    prompt_injection_system_action: int = 0
    details: list[str] = field(default_factory=list)

    def note(self, gate: str, detail: str) -> None:
        if not hasattr(self, gate):
            raise KeyError(gate)
        setattr(self, gate, getattr(self, gate) + 1)
        self.details.append(f"{gate}: {detail}")

    def as_dict(self) -> dict[str, Any]:
        return {
            k: getattr(self, k)
            for k in (
                "false_rejection",
                "false_offer",
                "false_confident_association",
                "cross_case_mutation",
                "duplicate_calendar_event",
                "duplicate_external_action",
                "fake_application_submission",
                "real_email_sent",
                "profile_deletion_resurrection",
                "silent_data_loss",
                "unrecoverable_db_corruption",
                "production_secret_leak",
                "real_pii_fixture",
                "prompt_injection_system_action",
            )
        } | {"details": list(self.details)}

    def assert_all_zero(self) -> None:
        bad = {k: v for k, v in self.as_dict().items() if k != "details" and v}
        if bad:
            raise AssertionError(
                f"CRITICAL ZERO GATE FAILED: {bad}; {self.details[:30]}"
            )


BANNED_PII_FRAGMENTS = (
    "@gmail.com",
    "@googlemail.com",
    "@outlook.com",
    "@yahoo.com",
    "@rheinoffice.de",
    "@acme-recruiting.de",
)


def assert_no_real_pii(text: str, *, context: str = "") -> None:
    lower = (text or "").lower()
    for frag in BANNED_PII_FRAGMENTS:
        if frag in lower:
            raise AssertionError(f"real_pii_fixture in {context}: contains {frag}")
