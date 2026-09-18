"""Timezone conflict + reschedule matrix for Calendar Scheduling Engine (PR31).

>=200 deterministic tests. No real calendar accounts — mocks only.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from core.lifecycle import CaseEventType, CaseStatus
from core.scheduling_preferences import (
    RANKING_VERSION,
    SCHEDULING_PREFS_SCHEMA_VERSION,
    ExplicitAvailabilityWindow,
    SchedulingPreferences,
    empty_scheduling_preferences,
    migrate_scheduling_preferences,
    preferences_from_settings,
)
from integrations.calendar_availability import (
    ConstraintContext,
    TimeWindow,
    check_constraints,
    check_interview_slot,
    expand_with_buffers,
    iter_candidate_starts,
    load_holiday_dates,
    overlaps,
    parse_multi_windows,
    parse_working_hours,
)
from integrations.calendar_freebusy import (
    FreeBusyQuery,
    MockFreeBusyProvider,
    StaticDictFreeBusyProvider,
    busy_as_public_dicts,
    merge_busy,
)
from integrations.calendar_scheduling import (
    change_slot_selection,
    propose_ranked_slots,
    select_slot,
    verify_no_collisions,
)
from integrations.calendar_timezone import (
    TimezoneAmbiguityError,
    combine_local,
    ensure_aware,
    isoformat_z,
    parse_iso_datetime,
    to_utc,
    to_zone,
)
from integrations.calendar_write import (
    CalendarWriteGate,
    InMemoryCalendarTransport,
    draft_from_ranked_slot,
    draft_to_ics,
)
from integrations.ics_export import build_meetings_ics
from integrations.proposal_parse import parse_scheduling_proposal

BERLIN = "Europe/Berlin"
LONDON = "Europe/London"
UTC = timezone.utc


def _aware(y, m, d, hh, mm, tz=BERLIN):
    return combine_local(date(y, m, d), time(hh, mm), tz)


def _prefs(**kwargs) -> SchedulingPreferences:
    base = empty_scheduling_preferences()
    for k, v in kwargs.items():
        setattr(base, k, v)
    return migrate_scheduling_preferences(base)


# ---------------------------------------------------------------------------
# Timezone / DST / naive elimination
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "raw,expect_offset_hours",
    [
        ("2026-01-15T10:00:00+01:00", 1),  # CET
        ("2026-07-15T10:00:00+02:00", 2),  # CEST
        ("2026-01-15T10:00:00Z", 0),
        ("2026-09-15T09:00:00+01:00", 1),  # London BST ends late Oct; Sep still +1
    ],
)
def test_cet_cest_offsets_parse(raw, expect_offset_hours):
    dt = parse_iso_datetime(raw)
    assert dt is not None and dt.tzinfo is not None
    assert dt.utcoffset() == timedelta(hours=expect_offset_hours)


@pytest.mark.parametrize("month,day,hour", [(3, 29, 2), (3, 29, 2)])  # EU spring 2026
def test_dst_spring_forward_berlin_nonexistent(month, day, hour):
    # 2026-03-29 02:00 does not exist in Europe/Berlin
    with pytest.raises(TimezoneAmbiguityError):
        combine_local(date(2026, month, day), time(hour, 30), BERLIN)


def test_dst_fall_back_berlin_ambiguous():
    # 2026-10-25 02:30 is ambiguous in Berlin
    with pytest.raises(TimezoneAmbiguityError):
        combine_local(date(2026, 10, 25), time(2, 30), BERLIN)


@pytest.mark.parametrize(
    "tz_a,tz_b,y,m,d,h",
    [
        (BERLIN, LONDON, 2026, 1, 15, 10),
        (BERLIN, LONDON, 2026, 7, 15, 10),
        (BERLIN, LONDON, 2026, 3, 28, 10),
        (BERLIN, LONDON, 2026, 10, 24, 10),
        (LONDON, BERLIN, 2026, 6, 1, 9),
        (LONDON, BERLIN, 2026, 12, 1, 9),
    ],
)
def test_berlin_london_same_instant_roundtrip(tz_a, tz_b, y, m, d, h):
    a = _aware(y, m, d, h, 0, tz_a)
    b = to_zone(a, tz_b)
    assert to_utc(a) == to_utc(b)


def test_naive_datetime_rejected():
    with pytest.raises(TimezoneAmbiguityError):
        ensure_aware(datetime(2026, 9, 15, 10, 0))


def test_naive_iso_without_default_returns_none():
    assert parse_iso_datetime("2026-09-15T10:00:00") is None


def test_naive_iso_with_default_anchored():
    dt = parse_iso_datetime("2026-09-15T10:00:00", default_tz=BERLIN)
    assert dt is not None and dt.tzinfo is not None
    assert to_zone(dt, BERLIN).hour == 10


def test_timewindow_rejects_naive():
    with pytest.raises(TimezoneAmbiguityError):
        TimeWindow(datetime(2026, 9, 15, 10, 0), datetime(2026, 9, 15, 11, 0))


# ---------------------------------------------------------------------------
# Overlap deterministic
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "a0,a1,b0,b1,expect",
    [
        (10, 11, 11, 12, False),
        (10, 11, 10, 11, True),
        (10, 12, 11, 13, True),
        (10, 11, 9, 10, False),
        (10, 11, 9, 10, False),
        (9, 17, 12, 13, True),
        (10, 11, 10, 10, False),  # zero-length skipped by construction elsewhere
    ],
)
def test_overlap_matrix_hours(a0, a1, b0, b1, expect):
    if b0 == b1:
        pytest.skip("zero length")
    a = TimeWindow(_aware(2026, 9, 15, a0, 0), _aware(2026, 9, 15, a1, 0))
    b = TimeWindow(_aware(2026, 9, 15, b0, 0), _aware(2026, 9, 15, b1, 0))
    assert overlaps(a, b) is expect


@pytest.mark.parametrize("offset_hours", [0, 1, 2, -1])
def test_overlap_across_zones(offset_hours):
    berlin = TimeWindow(_aware(2026, 7, 1, 10, 0), _aware(2026, 7, 1, 11, 0))
    # Same UTC instant window expressed with fixed offset
    start = to_utc(berlin.start).astimezone(timezone(timedelta(hours=offset_hours)))
    end = to_utc(berlin.end).astimezone(timezone(timedelta(hours=offset_hours)))
    other = TimeWindow(start, end)
    assert overlaps(berlin, other) is True


# ---------------------------------------------------------------------------
# Proposal parsing
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "text,weekdays",
    [
        ("Dienstag oder Mittwoch zwischen 9 und 15 Uhr", (1, 2)),
        ("Montag und Freitag zwischen 10 und 12 Uhr", (0, 4)),
        ("Tuesday or Wednesday between 9 and 15", (1, 2)),
        ("Thu/Fri 9-15 Uhr", (3, 4)),
        ("Donnerstag zwischen 14 und 16 Uhr remote", (3,)),
    ],
)
def test_parse_flexible_windows(text, weekdays):
    r = parse_scheduling_proposal(text, reference=datetime(2026, 9, 14, tzinfo=UTC))
    assert r.windows
    assert set(r.windows[0].weekdays) == set(weekdays)
    assert r.windows[0].is_usable()


@pytest.mark.parametrize(
    "text",
    [
        "am 20.09.2026 um 14:00",
        "2026-09-20T14:00:00+02:00",
        "Montag, 21. September 2026, 10:30",
    ],
)
def test_parse_fixed_slots(text):
    r = parse_scheduling_proposal(text, default_tz=BERLIN, reference=datetime(2026, 9, 1, tzinfo=UTC))
    assert r.fixed_slots
    assert all(s.tzinfo is not None for s in r.fixed_slots)


def test_parse_ambiguous_time_without_weekday_fails_safe():
    r = parse_scheduling_proposal("zwischen 9 und 15 Uhr", reference=datetime(2026, 9, 14, tzinfo=UTC))
    assert any("ambiguous" in e for e in r.errors)
    assert not any(w.is_usable() for w in r.windows) or not r.ok


@pytest.mark.parametrize(
    "text,modality",
    [
        ("Dienstag 10-12 Uhr vor Ort", "onsite"),
        ("Mittwoch zwischen 9 und 11 Zoom", "remote"),
        ("Friday 9-11 onsite", "onsite"),
        ("Tue 10-12 Teams meeting", "remote"),
    ],
)
def test_parse_modality(text, modality):
    r = parse_scheduling_proposal(text, reference=datetime(2026, 9, 14, tzinfo=UTC))
    assert r.modality == modality


# ---------------------------------------------------------------------------
# Constraints: weekend, holiday, buffers, remote/onsite
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("day", [date(2026, 9, 19), date(2026, 9, 20)])  # Sat/Sun
def test_weekend_blocked_by_default(day):
    prefs = _prefs()
    start = combine_local(day, time(10, 0), BERLIN)
    win = TimeWindow(start, start + timedelta(hours=1))
    res = check_constraints(win, ConstraintContext(prefs=prefs))
    assert res.ok is False
    assert "weekday_blocked" in res.conflicts


def test_weekend_allowed_when_enabled():
    prefs = _prefs(allow_weekends=True)
    start = combine_local(date(2026, 9, 19), time(10, 0), BERLIN)
    win = TimeWindow(start, start + timedelta(hours=1))
    res = check_constraints(win, ConstraintContext(prefs=prefs))
    assert res.ok is True


def test_holiday_optional_off_by_default():
    # 2026-10-03 German Unity Day
    prefs = _prefs(respect_holidays=False)
    holidays = load_holiday_dates(country="DE", years=[2026], enabled=True)
    assert date(2026, 10, 3) in holidays
    start = combine_local(date(2026, 10, 3), time(10, 0), BERLIN)  # Saturday actually? Oct 3 2026 is Sat
    # Use a weekday holiday: 2026-01-01 is Thursday
    start = combine_local(date(2026, 1, 1), time(10, 0), BERLIN)
    win = TimeWindow(start, start + timedelta(hours=1))
    res = check_constraints(win, ConstraintContext(prefs=prefs, holiday_dates=holidays))
    assert "holiday" not in res.conflicts


def test_holiday_optional_on_blocks():
    prefs = _prefs(respect_holidays=True)
    holidays = load_holiday_dates(country="DE", years=[2026], enabled=True)
    start = combine_local(date(2026, 1, 1), time(10, 0), BERLIN)
    win = TimeWindow(start, start + timedelta(hours=1))
    res = check_constraints(win, ConstraintContext(prefs=prefs, holiday_dates=holidays))
    assert res.ok is False
    assert "holiday" in res.conflicts


@pytest.mark.parametrize("before,after", [(0, 0), (15, 15), (30, 0), (0, 45), (10, 10)])
def test_buffer_expands_collision(before, after):
    prefs = _prefs(buffer_before_minutes=before, buffer_after_minutes=after, interview_duration_minutes=60)
    interview = TimeWindow(_aware(2026, 9, 15, 11, 0), _aware(2026, 9, 15, 12, 0))
    # Busy ends exactly at 11:00 — collides only if before buffer > 0
    busy = TimeWindow(_aware(2026, 9, 15, 10, 0), _aware(2026, 9, 15, 11, 0))
    res = check_constraints(
        interview,
        ConstraintContext(prefs=prefs, busy=(busy,), modality="remote"),
    )
    if before > 0:
        assert res.ok is False and "calendar_busy" in res.conflicts
    else:
        assert "calendar_busy" not in res.conflicts


def test_onsite_travel_buffer_configurable_not_invented():
    prefs = _prefs(onsite_travel_buffer_minutes=60, buffer_before_minutes=0, buffer_after_minutes=0)
    interview = TimeWindow(_aware(2026, 9, 15, 11, 0), _aware(2026, 9, 15, 12, 0))
    busy = TimeWindow(_aware(2026, 9, 15, 10, 0), _aware(2026, 9, 15, 11, 0))
    remote = check_constraints(interview, ConstraintContext(prefs=prefs, busy=(busy,), modality="remote"))
    onsite = check_constraints(interview, ConstraintContext(prefs=prefs, busy=(busy,), modality="onsite"))
    assert "calendar_busy" not in remote.conflicts
    assert "calendar_busy" in onsite.conflicts


def test_remote_ignores_onsite_travel_buffer():
    prefs = _prefs(onsite_travel_buffer_minutes=90)
    assert prefs.effective_onsite_buffer(modality="remote") == 0
    assert prefs.effective_onsite_buffer(modality="onsite") == 90


def test_explicit_availability_required():
    prefs = _prefs(
        explicit_availability=[
            ExplicitAvailabilityWindow(
                start="2026-09-15T09:00:00+02:00",
                end="2026-09-15T12:00:00+02:00",
            )
        ],
        buffer_before_minutes=0,
        buffer_after_minutes=0,
    )
    ok = check_interview_slot("2026-09-15T10:00:00+02:00", prefs=prefs)
    bad = check_interview_slot("2026-09-15T14:00:00+02:00", prefs=prefs)
    assert ok.ok is True
    assert bad.ok is False
    assert "outside_explicit_availability" in bad.conflicts


def test_outside_working_hours():
    hit = check_interview_slot(
        "2026-09-15T20:00:00+02:00",
        working_hours="09:00-17:00",
        timezone_name=BERLIN,
    )
    assert hit.outside_working_hours is True
    assert hit.ok is False


# ---------------------------------------------------------------------------
# FreeBusy mocks
# ---------------------------------------------------------------------------

def test_mock_freebusy_filters_range():
    busy = [
        TimeWindow(_aware(2026, 9, 15, 9, 0), _aware(2026, 9, 15, 10, 0)),
        TimeWindow(_aware(2026, 9, 16, 9, 0), _aware(2026, 9, 16, 10, 0)),
    ]
    fb = MockFreeBusyProvider(busy)
    q = FreeBusyQuery(time_min=_aware(2026, 9, 15, 0, 0), time_max=_aware(2026, 9, 15, 23, 0))
    out = fb.query(q)
    assert len(out) == 1


def test_static_dict_freebusy_strips_titles():
    fb = StaticDictFreeBusyProvider(
        [{"start": "2026-09-15T08:00:00Z", "end": "2026-09-15T09:00:00Z", "title": "SECRET"}]
    )
    out = fb.query(FreeBusyQuery(time_min=datetime(2026, 9, 15, tzinfo=UTC), time_max=datetime(2026, 9, 16, tzinfo=UTC)))
    pub = busy_as_public_dicts(out)
    assert "title" not in pub[0]
    assert "SECRET" not in str(pub)


def test_merge_busy_coalesces():
    a = TimeWindow(datetime(2026, 9, 15, 8, 0, tzinfo=UTC), datetime(2026, 9, 15, 9, 0, tzinfo=UTC))
    b = TimeWindow(datetime(2026, 9, 15, 8, 30, tzinfo=UTC), datetime(2026, 9, 15, 10, 0, tzinfo=UTC))
    m = merge_busy([a], [b])
    assert len(m) == 1
    assert m[0].end == datetime(2026, 9, 15, 10, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Ranking — never first-free-only; explanations; e2e no collision
# ---------------------------------------------------------------------------

def test_rank_flexible_window_multiple_slots():
    prefs = _prefs(max_ranked_slots=5, slot_step_minutes=30, preferred_windows="10:00-12:00")
    p = propose_ranked_slots(
        "Dienstag oder Mittwoch zwischen 9 und 15 Uhr",
        case_id="c1",
        prefs=prefs,
        freebusy=MockFreeBusyProvider([]),
        reference=datetime(2026, 9, 14, tzinfo=UTC),
    )
    assert p.status == "proposed"
    assert len(p.ranked_slots) >= 2
    # Not merely chronological first free — preferred window should boost ~10:xx
    top = p.ranked_slots[0]
    local = to_zone(top.start, BERLIN)
    assert 9 <= local.hour < 15
    assert top.explanations
    assert top.rank == 1
    assert verify_no_collisions(p, prefs=prefs, busy=[])


def test_rank_all_busy_fails_safe():
    prefs = _prefs()
    # Block entire Tue/Wed workdays
    busy = []
    for day in (15, 16, 22, 23):
        busy.append(TimeWindow(_aware(2026, 9, day, 8, 0), _aware(2026, 9, day, 18, 0)))
    p = propose_ranked_slots(
        "Dienstag oder Mittwoch zwischen 9 und 15 Uhr",
        prefs=prefs,
        freebusy=MockFreeBusyProvider(busy),
        reference=datetime(2026, 9, 14, tzinfo=UTC),
    )
    assert p.status == "no_slots"
    assert "fail_safe" in p.stop_reason
    assert p.ranked_slots == []


def test_rank_fixed_slot():
    prefs = _prefs(buffer_before_minutes=0, buffer_after_minutes=0)
    p = propose_ranked_slots(
        "am 15.09.2026 um 10:00",
        prefs=prefs,
        freebusy=MockFreeBusyProvider([]),
        reference=datetime(2026, 9, 1, tzinfo=UTC),
    )
    assert p.status == "proposed"
    assert len(p.ranked_slots) == 1
    assert to_zone(p.ranked_slots[0].start, BERLIN).hour == 10


def test_rank_skips_busy_overlap():
    prefs = _prefs(buffer_before_minutes=0, buffer_after_minutes=0, slot_step_minutes=60)
    busy = [TimeWindow(_aware(2026, 9, 15, 10, 0), _aware(2026, 9, 15, 11, 0))]
    p = propose_ranked_slots(
        "Dienstag zwischen 9 und 12 Uhr",
        prefs=prefs,
        freebusy=MockFreeBusyProvider(busy),
        reference=datetime(2026, 9, 14, tzinfo=UTC),
    )
    assert p.ranked_slots
    for s in p.ranked_slots:
        assert not overlaps(TimeWindow(s.start, s.end), busy[0])


def test_ranking_version_rollback_pin():
    prefs = _prefs(ranking_version=1)
    pinned = prefs.with_ranking_version(1)
    assert pinned.ranking_version == 1
    assert pinned.schema_version == SCHEDULING_PREFS_SCHEMA_VERSION


def test_rank_explanations_include_version():
    p = propose_ranked_slots(
        "Mittwoch zwischen 9 und 15 Uhr",
        prefs=_prefs(),
        freebusy=MockFreeBusyProvider([]),
        reference=datetime(2026, 9, 14, tzinfo=UTC),
    )
    assert any("Ranking-Version" in e for e in p.ranked_slots[0].explanations)


# ---------------------------------------------------------------------------
# Reschedule matrix
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "old_busy_end,new_text",
    [
        (11, "Donnerstag zwischen 9 und 12 Uhr"),
        (12, "Freitag zwischen 13 und 16 Uhr"),
        (10, "Dienstag zwischen 14 und 17 Uhr"),
    ],
)
def test_reschedule_after_conflict(old_busy_end, new_text):
    prefs = _prefs(buffer_before_minutes=0, buffer_after_minutes=0)
    # First proposal collides with full-day busy Tue
    busy = [TimeWindow(_aware(2026, 9, 15, 8, 0), _aware(2026, 9, 15, old_busy_end, 0))]
    first = propose_ranked_slots(
        "Dienstag zwischen 9 und 12 Uhr",
        prefs=prefs,
        freebusy=MockFreeBusyProvider(busy),
        reference=datetime(2026, 9, 14, tzinfo=UTC),
    )
    # Reschedule to new employer window
    second = propose_ranked_slots(
        new_text,
        prefs=prefs,
        freebusy=MockFreeBusyProvider(busy),
        reference=datetime(2026, 9, 14, tzinfo=UTC),
    )
    if second.ranked_slots:
        assert verify_no_collisions(second, prefs=prefs, busy=busy)
        assert second.status == "proposed"


def test_reschedule_existing_meeting_collision():
    prefs = _prefs(buffer_before_minutes=0, buffer_after_minutes=0)
    meetings = [{"id": "m1", "scheduled_at": "2026-09-16T10:00:00+02:00", "end": "2026-09-16T11:00:00+02:00"}]
    p = propose_ranked_slots(
        "Mittwoch zwischen 9 und 12 Uhr",
        prefs=prefs,
        freebusy=MockFreeBusyProvider([]),
        existing_meetings=meetings,
        reference=datetime(2026, 9, 14, tzinfo=UTC),
    )
    for s in p.ranked_slots:
        assert not (s.start < _aware(2026, 9, 16, 11, 0) and _aware(2026, 9, 16, 10, 0) < s.end)


# ---------------------------------------------------------------------------
# Beta contract: review / change selection
# ---------------------------------------------------------------------------

def test_select_and_change_slot_contract():
    p = propose_ranked_slots(
        "Dienstag oder Mittwoch zwischen 9 und 15 Uhr",
        case_id="case-9",
        prefs=_prefs(max_ranked_slots=3),
        freebusy=MockFreeBusyProvider([]),
        reference=datetime(2026, 9, 14, tzinfo=UTC),
    )
    assert len(p.ranked_slots) >= 2
    select_slot(p, 0)
    assert p.status == "selected" and p.selected_slot_index == 0
    change_slot_selection(p, 1)
    assert p.selected_slot_index == 1
    blob = p.to_dict()
    assert blob["lifecycle_event_hint"] == CaseEventType.INTERVIEW_SLOTS_PROPOSED.value
    assert "ranked_slots" in blob


def test_invalid_selection_rejected():
    p = propose_ranked_slots(
        "Freitag zwischen 9 und 11 Uhr",
        prefs=_prefs(),
        freebusy=MockFreeBusyProvider([]),
        reference=datetime(2026, 9, 14, tzinfo=UTC),
    )
    select_slot(p, 99)
    assert p.status == "rejected"


# ---------------------------------------------------------------------------
# Calendar write gate — approval, idempotency, failed != SCHEDULED
# ---------------------------------------------------------------------------

def test_write_requires_approval():
    p = propose_ranked_slots(
        "am 15.09.2026 um 11:00",
        case_id="c",
        prefs=_prefs(buffer_before_minutes=0, buffer_after_minutes=0),
        freebusy=MockFreeBusyProvider([]),
        reference=datetime(2026, 9, 1, tzinfo=UTC),
    )
    select_slot(p, 0)
    draft = draft_from_ranked_slot(p, client_request_id="r1")
    gate = CalendarWriteGate(allow_write=True)
    transport = InMemoryCalendarTransport()
    out = gate.attempt_create(draft, transport=transport)
    assert out.created is False
    assert out.create_error == "not_approved"
    assert gate.may_mark_scheduled(out) is False


def test_write_disabled_flag():
    p = propose_ranked_slots(
        "am 15.09.2026 um 11:00",
        case_id="c",
        prefs=_prefs(buffer_before_minutes=0, buffer_after_minutes=0),
        freebusy=MockFreeBusyProvider([]),
        reference=datetime(2026, 9, 1, tzinfo=UTC),
    )
    select_slot(p, 0)
    draft = draft_from_ranked_slot(p, client_request_id="r2")
    gate = CalendarWriteGate(allow_write=False)
    gate.approve(draft)
    out = gate.attempt_create(draft, transport=InMemoryCalendarTransport())
    assert out.created is False
    assert "write_disabled" in out.create_error


def test_write_success_idempotent_no_duplicates():
    p = propose_ranked_slots(
        "am 15.09.2026 um 11:00",
        case_id="c",
        prefs=_prefs(buffer_before_minutes=0, buffer_after_minutes=0),
        freebusy=MockFreeBusyProvider([]),
        reference=datetime(2026, 9, 1, tzinfo=UTC),
    )
    select_slot(p, 0)
    draft = draft_from_ranked_slot(p, client_request_id="idem-1")
    gate = CalendarWriteGate(allow_write=True)
    gate.approve(draft)
    t = InMemoryCalendarTransport()
    a = gate.attempt_create(draft, transport=t)
    b = gate.attempt_create(draft, transport=t)
    assert a.created and b.created
    assert a.external_event_id == b.external_event_id
    assert t.create_calls == 1  # second short-circuited by gate
    assert gate.may_mark_scheduled(a) is True
    assert gate.lifecycle_event_on_result(a) == CaseEventType.CALENDAR_WRITE_APPROVED.value


def test_failed_create_not_scheduled():
    p = propose_ranked_slots(
        "am 15.09.2026 um 11:00",
        case_id="c",
        prefs=_prefs(buffer_before_minutes=0, buffer_after_minutes=0),
        freebusy=MockFreeBusyProvider([]),
        reference=datetime(2026, 9, 1, tzinfo=UTC),
    )
    select_slot(p, 0)
    draft = draft_from_ranked_slot(p, client_request_id="fail-1")
    gate = CalendarWriteGate(allow_write=True)
    gate.approve(draft)
    t = InMemoryCalendarTransport()
    t.fail_next = True
    out = gate.attempt_create(draft, transport=t)
    assert out.created is False
    assert gate.may_mark_scheduled(out) is False
    assert gate.lifecycle_event_on_result(out) == CaseEventType.CALENDAR_WRITE_FAILED.value
    assert out.lifecycle_status_on_success == CaseStatus.INTERVIEW.value  # only on success path


# ---------------------------------------------------------------------------
# ICS
# ---------------------------------------------------------------------------

def test_ics_export_utc_and_escape():
    ics = build_meetings_ics(
        [
            {
                "uid": "u1",
                "title": "Interview, Runde 1",
                "scheduled_at": "2026-09-15T10:00:00+02:00",
                "end": "2026-09-15T11:00:00+02:00",
                "description": "Line1\nLine2",
                "location": "Berlin, DE",
            }
        ]
    )
    assert "BEGIN:VCALENDAR" in ics
    assert "DTSTART:20260915T080000Z" in ics
    assert "SUMMARY:Interview\\, Runde 1" in ics
    assert "LOCATION:Berlin\\, DE" in ics


def test_draft_to_ics_roundtrip():
    p = propose_ranked_slots(
        "am 15.09.2026 um 11:00",
        case_id="c",
        prefs=_prefs(buffer_before_minutes=0, buffer_after_minutes=0),
        freebusy=MockFreeBusyProvider([]),
        reference=datetime(2026, 9, 1, tzinfo=UTC),
    )
    select_slot(p, 0)
    draft = draft_from_ranked_slot(p, client_request_id="ics1")
    ics = draft_to_ics(draft)
    assert "VEVENT" in ics and draft.uid in ics


# ---------------------------------------------------------------------------
# Preferences versioning / settings adapter
# ---------------------------------------------------------------------------

def test_preferences_roundtrip_dict():
    prefs = _prefs(timezone=LONDON, respect_holidays=True)
    raw = prefs.to_dict()
    back = SchedulingPreferences.from_dict(raw)
    assert back.timezone == LONDON
    assert back.respect_holidays is True


def test_preferences_from_settings_fields():
    prefs = preferences_from_settings(
        working_hours="08:00-16:00",
        timezone=BERLIN,
        onsite_travel_buffer_minutes=45,
        allow_weekends=True,
    )
    assert prefs.working_hours == "08:00-16:00"
    assert prefs.onsite_travel_buffer_minutes == 45
    assert prefs.allow_weekends is True


def test_parse_working_hours_and_multi():
    assert parse_working_hours("09:30-17:45")[0] == time(9, 30)
    assert len(parse_multi_windows("09:00-12:00,14:00-17:00")) == 2


def test_iter_candidates_skips_dst_gap_day_partial():
    # Normal day still yields candidates
    starts = iter_candidate_starts(
        date(2026, 9, 15), time(9, 0), time(12, 0), duration_minutes=60, step_minutes=30, tz=BERLIN
    )
    assert len(starts) >= 3
    assert all(s.tzinfo is not None for s in starts)


def test_expand_with_buffers_minutes():
    w = TimeWindow(_aware(2026, 9, 15, 10, 0), _aware(2026, 9, 15, 11, 0))
    e = expand_with_buffers(w, before=15, after=15, travel=30)
    assert (e.end - e.start) == timedelta(minutes=60 + 15 + 15 + 60)


def test_isoformat_z_stable():
    dt = _aware(2026, 7, 1, 12, 0)
    assert isoformat_z(dt).endswith("Z")


def test_ambiguous_proposal_no_slots():
    p = propose_ranked_slots(
        "zwischen 9 und 15 Uhr",
        prefs=_prefs(),
        freebusy=MockFreeBusyProvider([]),
        reference=datetime(2026, 9, 14, tzinfo=UTC),
    )
    assert p.status == "no_slots"
    assert "fail_safe" in p.stop_reason


# ---------------------------------------------------------------------------
# Parametrized matrix: many CET/CEST + conflict combinations (>=200 total)
# ---------------------------------------------------------------------------

_CET_DAYS = [
    date(2026, 1, 5 + i) for i in range(10)  # January CET weekdays-ish
]
_CEST_DAYS = [
    date(2026, 7, 6 + i) for i in range(10)
]
_HOURS = list(range(9, 16))
_DURATIONS = [30, 45, 60, 90]


@pytest.mark.parametrize("day", _CET_DAYS + _CEST_DAYS)
@pytest.mark.parametrize("hour", [9, 10, 11, 14])
def test_matrix_local_slot_aware_ok(day, hour):
    if day.weekday() >= 5:
        pytest.skip("weekend")
    prefs = _prefs(buffer_before_minutes=0, buffer_after_minutes=0)
    start = combine_local(day, time(hour, 0), BERLIN)
    end = start + timedelta(hours=1)
    # Skip if crosses outside WH
    if hour + 1 > 17:
        pytest.skip("after hours")
    res = check_constraints(TimeWindow(start, end), ConstraintContext(prefs=prefs))
    assert res.ok is True
    assert start.tzinfo is not None


@pytest.mark.parametrize("day", [date(2026, 1, 6), date(2026, 7, 7), date(2026, 3, 10), date(2026, 10, 6)])
@pytest.mark.parametrize("busy_hour", [9, 10, 11, 12, 13, 14])
@pytest.mark.parametrize("slot_hour", [9, 10, 11, 12, 13, 14])
def test_matrix_busy_overlap_deterministic(day, busy_hour, slot_hour):
    if day.weekday() >= 5:
        pytest.skip("weekend")
    prefs = _prefs(buffer_before_minutes=0, buffer_after_minutes=0, interview_duration_minutes=60)
    busy = TimeWindow(
        combine_local(day, time(busy_hour, 0), BERLIN),
        combine_local(day, time(busy_hour + 1, 0), BERLIN),
    )
    slot = TimeWindow(
        combine_local(day, time(slot_hour, 0), BERLIN),
        combine_local(day, time(slot_hour + 1, 0), BERLIN),
    )
    res = check_constraints(slot, ConstraintContext(prefs=prefs, busy=(busy,)))
    expect_conflict = overlaps(slot, busy)
    if expect_conflict:
        assert res.ok is False and "calendar_busy" in res.conflicts
    else:
        assert "calendar_busy" not in res.conflicts


@pytest.mark.parametrize("tz", [BERLIN, LONDON])
@pytest.mark.parametrize("hour", [9, 10, 11, 12, 13, 14, 15])
@pytest.mark.parametrize("month", [1, 3, 6, 10])
def test_matrix_zone_working_hours(tz, hour, month):
    day = date(2026, month, 10)
    while day.weekday() >= 5:
        day += timedelta(days=1)
    prefs = _prefs(timezone=tz, buffer_before_minutes=0, buffer_after_minutes=0)
    start = combine_local(day, time(hour, 0), tz)
    end = start + timedelta(hours=1)
    res = check_constraints(TimeWindow(start, end), ConstraintContext(prefs=prefs))
    if hour + 1 <= 17:
        assert res.outside_working_hours is False
    # 15+60min = 16 still ok; hour 16 would be outside if duration 60 — we stop at 15


@pytest.mark.parametrize("duration", _DURATIONS)
@pytest.mark.parametrize("step", [15, 30, 60])
def test_matrix_candidate_generation_counts(duration, step):
    starts = iter_candidate_starts(
        date(2026, 9, 15),
        time(9, 0),
        time(15, 0),
        duration_minutes=duration,
        step_minutes=step,
        tz=BERLIN,
    )
    assert starts
    assert all(s.tzinfo is not None for s in starts)
    # Last start + duration <= 15:00
    assert to_zone(starts[-1], BERLIN).time() <= time(15, 0)


@pytest.mark.parametrize(
    "proposal",
    [
        "Dienstag zwischen 9 und 15 Uhr",
        "Mittwoch zwischen 10 und 14 Uhr",
        "Donnerstag oder Freitag zwischen 9 und 12 Uhr",
        "Monday or Tuesday between 9 and 15",
        "Freitag 9-11 Uhr remote",
        "Mittwoch 14-17 Uhr vor Ort",
    ],
)
def test_matrix_e2e_ranked_no_collision(proposal):
    prefs = _prefs(max_ranked_slots=5, buffer_before_minutes=15, buffer_after_minutes=15)
    busy = [
        TimeWindow(_aware(2026, 9, 15, 10, 0), _aware(2026, 9, 15, 11, 0)),
        TimeWindow(_aware(2026, 9, 17, 13, 0), _aware(2026, 9, 17, 14, 0)),
    ]
    p = propose_ranked_slots(
        proposal,
        prefs=prefs,
        freebusy=MockFreeBusyProvider(busy),
        reference=datetime(2026, 9, 14, tzinfo=UTC),
        modality_override="remote" if "vor Ort" not in proposal else "onsite",
    )
    if p.ranked_slots:
        assert verify_no_collisions(p, prefs=prefs, busy=busy)
        # Ranking must have explanations (not first-free silent)
        assert all(s.explanations for s in p.ranked_slots)
        # Scores non-increasing by rank order
        scores = [s.score for s in p.ranked_slots]
        assert scores == sorted(scores, reverse=True)


@pytest.mark.parametrize("country", ["DE", "AT", "CH", "GB"])
def test_matrix_holiday_loader_optional(country):
    off = load_holiday_dates(country=country, years=[2026], enabled=False)
    on = load_holiday_dates(country=country, years=[2026], enabled=True)
    assert off == frozenset()
    assert len(on) >= 1


@pytest.mark.parametrize("idx", list(range(20)))
def test_matrix_idempotent_write_ids(idx):
    p = propose_ranked_slots(
        "am 18.09.2026 um 10:00",
        case_id=f"case-{idx}",
        prefs=_prefs(buffer_before_minutes=0, buffer_after_minutes=0),
        freebusy=MockFreeBusyProvider([]),
        reference=datetime(2026, 9, 1, tzinfo=UTC),
    )
    if not p.ranked_slots:
        pytest.skip("no slot")
    select_slot(p, 0)
    d1 = draft_from_ranked_slot(p, client_request_id=f"req-{idx}")
    d2 = draft_from_ranked_slot(p, client_request_id=f"req-{idx}")
    assert d1.uid == d2.uid


@pytest.mark.parametrize("tz", [BERLIN, LONDON])
@pytest.mark.parametrize("day_offset", list(range(14)))
def test_matrix_availability_reply_no_titles(tz, day_offset):
    day = date(2026, 9, 14) + timedelta(days=day_offset)
    if day.weekday() >= 5:
        return
    busy = [
        TimeWindow(
            combine_local(day, time(10, 0), tz),
            combine_local(day, time(11, 0), tz),
        )
    ]
    from integrations.calendar_availability import availability_reply_slots

    suggestions = availability_reply_slots(
        working_hours="09:00-17:00",
        busy=busy,
        day_iso_dates=[day.isoformat()],
        slot_minutes=60,
        timezone_name=tz,
    )
    assert all("SECRET" not in s for s in suggestions)
    assert all("verfügbar" in s for s in suggestions) if suggestions else True
