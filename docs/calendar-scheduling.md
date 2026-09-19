"""Calendar Scheduling Engine (PR31) — overview.

## Goal

Turn employer proposals such as *"Dienstag oder Mittwoch zwischen 9 und 15 Uhr"*
into ranked, conflict-free interview slots (not first-free-only).

## Pipeline

1. **Parse** (`integrations/proposal_parse.py`) — DE/EN NL + dateparser fallback
2. **Constraints** (`calendar_availability.py` + `SchedulingPreferences`) —
   timezone-aware windows, weekdays, duration, before/after buffers, optional
   onsite travel buffer (user-configured only), weekend/holiday flags
3. **FreeBusy** (`calendar_freebusy.py`) — mock in CI; Google FreeBusy optional
4. **Rank** (`calendar_scheduling.py`) — score + explanations; versioned
5. **Review** — `SchedulingProposal` contract: select / change slot
6. **Write** (`calendar_write.py`) — separate `CalendarWriteGate` (approval required)

## Fail-safe STOP

- Timezone ambiguity → no slots (`fail_safe:…`)
- No conflict-free candidates → `no_slots` (never invent)

## Privacy

Busy intervals never include private event titles. Employer-facing drafts use
generic titles (`Interview (Karrierekrake)`).

## Versioning / rollback

- `SCHEDULING_PREFS_SCHEMA_VERSION` — preference shape
- `RANKING_VERSION` / `prefs.ranking_version` — pin older ranking independently
- Calendar writes idempotent via `client_request_id` / `uid`
- Failed create ≠ `SCHEDULED` (`CalendarWriteGate.may_mark_scheduled`)

## Out of scope

Auto-accept interviews, auto calendar write without approval, maps/routing APIs,
invented travel times.
