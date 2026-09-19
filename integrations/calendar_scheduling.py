"""Conflict-free interview slot ranking engine (PR31).

Generates candidate slots from employer proposals, filters via FreeBusy +
constraints, ranks multiple good options (never \"first free only\"), and
returns human-readable explanations.

Fail-safe: timezone ambiguity or zero conflict-free slots → empty ranked list
with documented stop reason (no invented slots).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from core.lifecycle import CaseEventType
from core.models import utc_now_iso
from core.scheduling_preferences import (
    RANKING_VERSION,
    SchedulingPreferences,
    empty_scheduling_preferences,
)
from integrations.calendar_availability import (
    ConstraintContext,
    TimeWindow,
    check_constraints,
    iter_candidate_starts,
    load_holiday_dates,
    parse_multi_windows,
    parse_working_hours,
)
from integrations.calendar_freebusy import FreeBusyProvider, FreeBusyQuery, MockFreeBusyProvider, merge_busy
from integrations.calendar_timezone import (
    TimezoneAmbiguityError,
    isoformat_offset,
    to_utc,
    to_zone,
)
from integrations.proposal_parse import ParseResult, parse_scheduling_proposal, parse_result_to_dict


@dataclass(frozen=True)
class RankedSlot:
    start: datetime
    end: datetime
    score: float
    rank: int
    explanations: tuple[str, ...]
    modality: str
    timezone: str
    ranking_version: int = RANKING_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "start": isoformat_offset(self.start),
            "end": isoformat_offset(self.end),
            "start_utc": to_utc(self.start).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "end_utc": to_utc(self.end).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "score": round(self.score, 4),
            "rank": self.rank,
            "explanations": list(self.explanations),
            "modality": self.modality,
            "timezone": self.timezone,
            "ranking_version": self.ranking_version,
        }


@dataclass
class SchedulingProposal:
    """API/contract object: user can review and change before calendar write."""

    case_id: str
    proposal_text: str
    modality: str
    timezone: str
    ranking_version: int
    prefs_schema_version: int
    ranked_slots: list[RankedSlot] = field(default_factory=list)
    selected_slot_index: int | None = None
    stop_reason: str = ""
    parse_errors: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now_iso)
    status: str = "proposed"  # proposed | selected | rejected | no_slots

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "proposal_text": self.proposal_text,
            "modality": self.modality,
            "timezone": self.timezone,
            "ranking_version": self.ranking_version,
            "prefs_schema_version": self.prefs_schema_version,
            "ranked_slots": [s.to_dict() for s in self.ranked_slots],
            "selected_slot_index": self.selected_slot_index,
            "stop_reason": self.stop_reason,
            "parse_errors": list(self.parse_errors),
            "created_at": self.created_at,
            "status": self.status,
            "lifecycle_event_hint": CaseEventType.INTERVIEW_SLOTS_PROPOSED.value,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SchedulingProposal":
        slots: list[RankedSlot] = []
        for raw in data.get("ranked_slots") or []:
            start = datetime.fromisoformat(str(raw["start"]))
            end = datetime.fromisoformat(str(raw["end"]))
            slots.append(
                RankedSlot(
                    start=start,
                    end=end,
                    score=float(raw.get("score") or 0),
                    rank=int(raw.get("rank") or 0),
                    explanations=tuple(raw.get("explanations") or ()),
                    modality=str(raw.get("modality") or "remote"),
                    timezone=str(raw.get("timezone") or "Europe/Berlin"),
                    ranking_version=int(raw.get("ranking_version") or RANKING_VERSION),
                )
            )
        return cls(
            case_id=str(data.get("case_id") or ""),
            proposal_text=str(data.get("proposal_text") or ""),
            modality=str(data.get("modality") or "unknown"),
            timezone=str(data.get("timezone") or "Europe/Berlin"),
            ranking_version=int(data.get("ranking_version") or RANKING_VERSION),
            prefs_schema_version=int(data.get("prefs_schema_version") or 1),
            ranked_slots=slots,
            selected_slot_index=data.get("selected_slot_index"),
            stop_reason=str(data.get("stop_reason") or ""),
            parse_errors=list(data.get("parse_errors") or []),
            created_at=str(data.get("created_at") or utc_now_iso()),
            status=str(data.get("status") or "proposed"),
        )


def select_slot(proposal: SchedulingProposal, index: int) -> SchedulingProposal:
    """Beta contract: user reviews and selects (or changes) a ranked slot."""
    if index < 0 or index >= len(proposal.ranked_slots):
        proposal.status = "rejected"
        proposal.selected_slot_index = None
        proposal.stop_reason = "invalid_selection"
        return proposal
    proposal.selected_slot_index = int(index)
    proposal.status = "selected"
    proposal.stop_reason = ""
    return proposal


def change_slot_selection(proposal: SchedulingProposal, index: int) -> SchedulingProposal:
    """Allow changing a previous selection before calendar write approval."""
    return select_slot(proposal, index)


def _preferred_bonus(local_start: datetime, prefs: SchedulingPreferences) -> tuple[float, list[str]]:
    windows = parse_multi_windows(prefs.preferred_windows)
    if not windows:
        return 0.0, []
    t = local_start.timetz().replace(tzinfo=None)
    for start, end in windows:
        if start <= t < end:
            return 25.0, [f"Liegt im bevorzugten Fenster {start.strftime('%H:%M')}–{end.strftime('%H:%M')}"]
    return 0.0, ["Außerhalb bevorzugter Teilfenster"]


def _midday_bonus(local_start: datetime) -> tuple[float, list[str]]:
    """Prefer late morning / early afternoon over edge-of-day."""
    hour = local_start.hour + local_start.minute / 60.0
    # Peak around 10:30
    dist = abs(hour - 10.5)
    score = max(0.0, 20.0 - dist * 4.0)
    if score >= 12:
        return score, ["Gute Tageszeit (Vormittag/früher Nachmittag)"]
    if score >= 5:
        return score, ["Akzeptable Tageszeit"]
    return score, ["Randzeit — niedriger priorisiert"]


def _earliness_bonus(local_start: datetime, earliest: datetime) -> tuple[float, list[str]]:
    days = max(0.0, (to_utc(local_start) - to_utc(earliest)).total_seconds() / 86400.0)
    score = max(0.0, 15.0 - days * 3.0)
    if days < 1:
        return score, ["Baldmöglichster konfliktfreier Termin"]
    return score, [f"In ca. {int(days)} Tag(en)"]


def _buffer_headroom_bonus(
    window: TimeWindow,
    busy: list[TimeWindow],
    prefs: SchedulingPreferences,
    modality: str,
) -> tuple[float, list[str]]:
    travel = prefs.effective_onsite_buffer(modality=modality)
    pad = timedelta(
        minutes=prefs.buffer_before_minutes + prefs.buffer_after_minutes + travel + 30
    )
    stretched = TimeWindow(window.start - pad, window.end + pad)
    tight = False
    for b in busy:
        if stretched.start < to_utc(b.end) and to_utc(b.start) < stretched.end:
            # Already conflict-free at required buffer; extra stretch means tight packing
            req = timedelta(minutes=prefs.buffer_before_minutes + travel)
            if window.start - req < to_utc(b.end) + timedelta(minutes=5):
                tight = True
                break
    if tight:
        return 0.0, ["Enger Puffer zum Nachbartermin"]
    return 10.0, ["Ausreichend Puffer zu anderen Terminen"]


def score_slot(
    window: TimeWindow,
    *,
    prefs: SchedulingPreferences,
    modality: str,
    busy: list[TimeWindow],
    earliest: datetime,
) -> tuple[float, tuple[str, ...]]:
    """Rank a conflict-free slot. Higher is better. Versioned via prefs.ranking_version."""
    version = int(prefs.ranking_version or RANKING_VERSION)
    local = to_zone(window.start, prefs.timezone)
    explanations: list[str] = []
    score = 50.0  # base for being conflict-free

    if version >= 1:
        b, e = _preferred_bonus(local, prefs)
        score += b
        explanations.extend(e)
        b, e = _midday_bonus(local)
        score += b
        explanations.extend(e)
        b, e = _earliness_bonus(local, earliest)
        score += b
        explanations.extend(e)
        b, e = _buffer_headroom_bonus(window, busy, prefs, modality)
        score += b
        explanations.extend(e)
        if modality == "onsite" and prefs.onsite_travel_buffer_minutes:
            explanations.append(
                f"Onsite-Reise-Puffer {prefs.onsite_travel_buffer_minutes} Min. (konfiguriert)"
            )
        elif modality == "remote":
            explanations.append("Remote — kein Reise-Puffer")

    explanations.append(f"Ranking-Version {version}")
    return score, tuple(explanations)


def _collect_candidates(
    parsed: ParseResult,
    prefs: SchedulingPreferences,
) -> tuple[list[TimeWindow], str]:
    """Build candidate interview windows; return stop_reason on failure."""
    modality = parsed.modality if parsed.modality != "unknown" else "remote"
    duration = timedelta(minutes=prefs.interview_duration_minutes)
    candidates: list[TimeWindow] = []

    for err in parsed.errors:
        if err.startswith("ambiguous") or err.startswith("timezone"):
            return [], f"fail_safe:{err}"

    for w in parsed.windows:
        if w.ambiguous or not w.is_usable():
            continue
        for d in w.fixed_dates:
            # Intersect employer window with working hours
            wh_start, wh_end = parse_working_hours(prefs.working_hours)
            start_t = max(w.start_time, wh_start)
            end_t = min(w.end_time, wh_end)
            if start_t >= end_t:
                continue
            for start in iter_candidate_starts(
                d,
                start_t,
                end_t,
                duration_minutes=prefs.interview_duration_minutes,
                step_minutes=prefs.slot_step_minutes,
                tz=prefs.timezone,
            ):
                candidates.append(TimeWindow(start, start + duration))

    for fixed in parsed.fixed_slots:
        try:
            start = fixed if fixed.tzinfo else None
            if start is None:
                return [], "fail_safe:naive_fixed_slot"
            candidates.append(TimeWindow(start, start + duration))
        except Exception:
            return [], "fail_safe:invalid_fixed_slot"

    if not candidates:
        return [], "fail_safe:no_candidates"
    return candidates, ""


def propose_ranked_slots(
    proposal_text: str,
    *,
    case_id: str = "",
    prefs: SchedulingPreferences | None = None,
    freebusy: FreeBusyProvider | None = None,
    existing_meetings: list[dict[str, Any]] | None = None,
    reference: datetime | None = None,
    modality_override: str | None = None,
) -> SchedulingProposal:
    """End-to-end: parse → FreeBusy → constrain → rank. Never auto-writes calendar."""
    prefs = prefs or empty_scheduling_preferences()
    provider = freebusy or MockFreeBusyProvider()
    parsed = parse_scheduling_proposal(
        proposal_text,
        default_tz=prefs.timezone,
        reference=reference,
    )
    modality = modality_override or (
        parsed.modality if parsed.modality != "unknown" else "remote"
    )

    proposal = SchedulingProposal(
        case_id=case_id,
        proposal_text=proposal_text,
        modality=modality,
        timezone=prefs.timezone,
        ranking_version=prefs.ranking_version,
        prefs_schema_version=prefs.schema_version,
        parse_errors=list(parsed.errors),
    )

    try:
        candidates, stop = _collect_candidates(parsed, prefs)
    except TimezoneAmbiguityError as exc:
        proposal.stop_reason = f"fail_safe:{exc}"
        proposal.status = "no_slots"
        return proposal

    if stop:
        proposal.stop_reason = stop
        proposal.status = "no_slots"
        return proposal

    tmin = min(c.start for c in candidates) - timedelta(hours=1)
    tmax = max(c.end for c in candidates) + timedelta(hours=1)
    busy = merge_busy(provider.query(FreeBusyQuery(time_min=tmin, time_max=tmax)))

    years = {to_zone(c.start, prefs.timezone).year for c in candidates}
    holidays = load_holiday_dates(
        country=prefs.holiday_country,
        years=years,
        enabled=prefs.respect_holidays,
    )
    ctx = ConstraintContext(
        prefs=prefs,
        modality=modality,
        busy=tuple(busy),
        existing_meetings=tuple(existing_meetings or ()),
        holiday_dates=holidays,
    )

    scored: list[tuple[float, TimeWindow, tuple[str, ...]]] = []
    earliest = min(c.start for c in candidates)
    for cand in candidates:
        result = check_constraints(cand, ctx)
        if not result.ok:
            continue
        score, expl = score_slot(
            cand, prefs=prefs, modality=modality, busy=busy, earliest=earliest
        )
        scored.append((score, cand, expl))

    if not scored:
        proposal.stop_reason = "fail_safe:no_conflict_free_slots"
        proposal.status = "no_slots"
        return proposal

    scored.sort(key=lambda x: (-x[0], to_utc(x[1].start)))
    ranked: list[RankedSlot] = []
    for i, (score, win, expl) in enumerate(scored[: prefs.max_ranked_slots], start=1):
        ranked.append(
            RankedSlot(
                start=win.start,
                end=win.end,
                score=score,
                rank=i,
                explanations=expl,
                modality=modality,
                timezone=prefs.timezone,
                ranking_version=prefs.ranking_version,
            )
        )
    proposal.ranked_slots = ranked
    proposal.status = "proposed"
    proposal.stop_reason = ""
    return proposal


def verify_no_collisions(
    proposal: SchedulingProposal,
    *,
    prefs: SchedulingPreferences,
    busy: list[TimeWindow],
    existing_meetings: list[dict[str, Any]] | None = None,
) -> bool:
    """E2E acceptance helper: every ranked slot must remain conflict-free."""
    holidays = load_holiday_dates(
        country=prefs.holiday_country,
        years={to_zone(s.start, prefs.timezone).year for s in proposal.ranked_slots} or {date.today().year},
        enabled=prefs.respect_holidays,
    )
    ctx = ConstraintContext(
        prefs=prefs,
        modality=proposal.modality,
        busy=tuple(busy),
        existing_meetings=tuple(existing_meetings or ()),
        holiday_dates=holidays,
    )
    for slot in proposal.ranked_slots:
        if not check_constraints(TimeWindow(slot.start, slot.end), ctx).ok:
            return False
    return True


def proposal_debug_bundle(proposal: SchedulingProposal, parsed: ParseResult | None = None) -> dict[str, Any]:
    """Diagnostics without private calendar titles."""
    data = proposal.to_dict()
    if parsed is not None:
        data["parse"] = parse_result_to_dict(parsed)
    return data
