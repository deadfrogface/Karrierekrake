"""Critical zero-gates for lifecycle E2E (hard fail, never soften)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class GateCounters:
    false_rejection: int = 0
    cross_case_mutation: int = 0
    duplicate_calendar_event: int = 0
    ambiguous_auto_association: int = 0
    failed_send_marked_sent: int = 0
    failed_calendar_marked_scheduled: int = 0
    details: list[str] = field(default_factory=list)

    def note(self, gate: str, detail: str) -> None:
        self.details.append(f"{gate}: {detail}")
        attr = {
            "false_rejection": "false_rejection",
            "cross_case_mutation": "cross_case_mutation",
            "duplicate_calendar_event": "duplicate_calendar_event",
            "ambiguous_auto_association": "ambiguous_auto_association",
            "failed_send_marked_sent": "failed_send_marked_sent",
            "failed_calendar_marked_scheduled": "failed_calendar_marked_scheduled",
        }[gate]
        setattr(self, attr, getattr(self, attr) + 1)

    def as_dict(self) -> dict[str, Any]:
        return {
            "false_rejection": self.false_rejection,
            "cross_case_mutation": self.cross_case_mutation,
            "duplicate_calendar_event": self.duplicate_calendar_event,
            "ambiguous_auto_association": self.ambiguous_auto_association,
            "failed_send_marked_sent": self.failed_send_marked_sent,
            "failed_calendar_marked_scheduled": self.failed_calendar_marked_scheduled,
            "details": list(self.details),
        }

    def assert_all_zero(self) -> None:
        bad = {k: v for k, v in self.as_dict().items() if k != "details" and v}
        if bad:
            raise AssertionError(f"CRITICAL ZERO GATE FAILED: {bad}; {self.details[:20]}")


def record_false_rejection(
    gates: GateCounters,
    *,
    fixture_id: str,
    expect_class: str,
    got_class: str,
) -> None:
    """Count only when a non-rejection fixture is classified as rejection."""
    if expect_class != "rejection" and got_class == "rejection":
        gates.note("false_rejection", f"{fixture_id}: expect={expect_class} got={got_class}")


def record_ambiguous_autolink(
    gates: GateCounters,
    *,
    fixture_id: str,
    association_status: str,
    wrote_case_id: str | None,
) -> None:
    if association_status in {"ambiguous", "review_required", "review"} and wrote_case_id:
        gates.note(
            "ambiguous_auto_association",
            f"{fixture_id}: status={association_status} wrote={wrote_case_id}",
        )


def record_cross_case(
    gates: GateCounters,
    *,
    fixture_id: str,
    expected_case_id: str,
    actual_case_id: str,
) -> None:
    if expected_case_id and actual_case_id and expected_case_id != actual_case_id:
        gates.note(
            "cross_case_mutation",
            f"{fixture_id}: expected={expected_case_id} actual={actual_case_id}",
        )
