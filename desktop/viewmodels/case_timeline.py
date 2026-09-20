"""Application case timeline view-model from canonical LifecycleEvents.

Maps only ``LifecycleEventType`` values — never invents status labels.
Widgets must not append events; pages call Database services explicitly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from core.lifecycle import (
    CANONICAL_CASE_STATUSES,
    CaseStatus,
    LifecycleEvent,
    LifecycleEventType,
    ReduceResult,
    reduce_lifecycle_events,
)


# User-facing stage keys for the briefed path. Values are i18n keys / stable ids.
# Source of truth remains LifecycleEventType — UI never invents new event types.
TIMELINE_STAGE_ORDER: tuple[str, ...] = (
    LifecycleEventType.APPLICATION_CREATED.value,
    LifecycleEventType.APPLICATION_SENT.value,
    LifecycleEventType.APPLICATION_RECEIVED.value,
    LifecycleEventType.UNDER_REVIEW.value,
    LifecycleEventType.INTERVIEW_REQUESTED.value,
    LifecycleEventType.INTERVIEW_SCHEDULED.value,
    LifecycleEventType.INTERVIEW_COMPLETED.value,
    LifecycleEventType.OFFER_RECEIVED.value,
    LifecycleEventType.REJECTION_RECEIVED.value,
)

# Short stage labels (i18n keys under timeline.stage.*)
STAGE_I18N: dict[str, str] = {
    LifecycleEventType.APPLICATION_CREATED.value: "timeline.stage.created",
    LifecycleEventType.APPLICATION_SENT.value: "timeline.stage.sent",
    LifecycleEventType.APPLICATION_RECEIVED.value: "timeline.stage.received",
    LifecycleEventType.UNDER_REVIEW.value: "timeline.stage.review",
    LifecycleEventType.INTERVIEW_REQUESTED.value: "timeline.stage.interview",
    LifecycleEventType.INTERVIEW_SCHEDULED.value: "timeline.stage.scheduled",
    LifecycleEventType.INTERVIEW_COMPLETED.value: "timeline.stage.completed",
    LifecycleEventType.OFFER_RECEIVED.value: "timeline.stage.offer",
    LifecycleEventType.REJECTION_RECEIVED.value: "timeline.stage.rejected",
    LifecycleEventType.MANUAL_OVERRIDE.value: "timeline.stage.manual_override",
    LifecycleEventType.DOCUMENT_REQUESTED.value: "timeline.stage.document",
    LifecycleEventType.ASSESSMENT_RECEIVED.value: "timeline.stage.assessment",
    LifecycleEventType.INTERVIEW_RESCHEDULED.value: "timeline.stage.rescheduled",
    LifecycleEventType.INTERVIEW_CANCELLED.value: "timeline.stage.cancelled",
    LifecycleEventType.FOLLOWUP_SENT.value: "timeline.stage.followup",
    LifecycleEventType.WITHDRAWN.value: "timeline.stage.withdrawn",
    LifecycleEventType.GHOSTED.value: "timeline.stage.ghosted",
    LifecycleEventType.ARCHIVED.value: "timeline.stage.archived",
}

CASE_STATUS_I18N: dict[str, str] = {
    CaseStatus.TO_APPLY.value: "case_status.to_apply",
    CaseStatus.APPLIED.value: "case_status.applied",
    CaseStatus.CONFIRMATION.value: "case_status.confirmation",
    CaseStatus.ASSESSMENT.value: "case_status.assessment",
    CaseStatus.INTERVIEW.value: "case_status.interview",
    CaseStatus.OFFER.value: "case_status.offer",
    CaseStatus.REJECTED.value: "case_status.rejected",
    CaseStatus.WITHDRAWN.value: "case_status.withdrawn",
    CaseStatus.GHOSTED.value: "case_status.ghosted",
    CaseStatus.CLOSED.value: "case_status.closed",
}


@dataclass(frozen=True)
class TimelineEntryView:
    event_type: str
    stage_key: str
    occurred_at: str
    recorded_at: str
    source: str
    confidence: float
    is_correction: bool
    summary: str
    event_id: str = ""


@dataclass(frozen=True)
class CaseTimelineViewModel:
    case_id: str
    status: str
    status_key: str
    entries: tuple[TimelineEntryView, ...]
    stage_reached: tuple[str, ...]  # subset of TIMELINE_STAGE_ORDER in order
    reduce: ReduceResult | None = None

    @property
    def has_auditable_correction(self) -> bool:
        return any(e.is_correction for e in self.entries)


def case_status_i18n_key(status: str) -> str:
    key = (status or "").strip().lower()
    if key not in CANONICAL_CASE_STATUSES:
        return "case_status.unknown"
    return CASE_STATUS_I18N.get(key, "case_status.unknown")


def _entry_summary(ev: LifecycleEvent) -> str:
    payload = ev.payload or {}
    bits: list[str] = []
    if payload.get("note"):
        bits.append(str(payload["note"]))
    if payload.get("to") or payload.get("status") or payload.get("target_status"):
        target = payload.get("to") or payload.get("status") or payload.get("target_status")
        bits.append(f"→ {target}")
    if payload.get("email_id"):
        bits.append(f"email:{payload['email_id']}")
    if payload.get("seed") or payload.get("backfill"):
        bits.append("seed")
    return " · ".join(bits)


def build_case_timeline_viewmodel(
    case_id: str,
    events: Sequence[LifecycleEvent],
    *,
    current_status: str = "",
) -> CaseTimelineViewModel:
    """Pure projection — does not write to the database."""
    reduce = reduce_lifecycle_events(events) if events else None
    status = (reduce.status if reduce else current_status) or CaseStatus.TO_APPLY.value
    entries: list[TimelineEntryView] = []
    reached: list[str] = []
    for ev in events:
        et = (ev.event_type or "").strip()
        is_correction = et == LifecycleEventType.MANUAL_OVERRIDE.value
        stage_key = STAGE_I18N.get(et, "timeline.stage.other")
        entries.append(
            TimelineEntryView(
                event_type=et,
                stage_key=stage_key,
                occurred_at=ev.occurred_at or "",
                recorded_at=ev.recorded_at or "",
                source=ev.source or "",
                confidence=float(ev.confidence or 0),
                is_correction=is_correction,
                summary=_entry_summary(ev),
                event_id=ev.id or "",
            )
        )
        if et in TIMELINE_STAGE_ORDER and et not in reached:
            # Keep primary path order: only append if not past a terminal fork.
            reached.append(et)

    # Order reached stages by canonical path order.
    reached_ordered = tuple(s for s in TIMELINE_STAGE_ORDER if s in set(reached))
    return CaseTimelineViewModel(
        case_id=case_id,
        status=status,
        status_key=case_status_i18n_key(status),
        entries=tuple(entries),
        stage_reached=reached_ordered,
        reduce=reduce,
    )


def primary_path_progress(reached: Iterable[str]) -> list[tuple[str, bool]]:
    """(event_type, reached?) for the canonical Created→…→Offer/Rejected path."""
    hit = set(reached)
    return [(stage, stage in hit) for stage in TIMELINE_STAGE_ORDER]
