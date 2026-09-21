"""Calendar OAuth modes A/B — scopes only; no live Google in CI."""

from __future__ import annotations

from integrations import google_oauth as goa


def test_mode_a_scopes_freebusy_only():
    decision = goa.scopes_for_features({goa.Feature.CALENDAR_SLOT_FINDING})
    scopes = decision.scopes
    assert goa.CALENDAR_FREEBUSY in scopes
    assert goa.CALENDAR_EVENTS_OWNED not in scopes
    assert "https://www.googleapis.com/auth/calendar" not in scopes


def test_mode_b_scopes_include_owned_events():
    decision = goa.scopes_for_features(
        {goa.Feature.CALENDAR_SLOT_FINDING, goa.Feature.CALENDAR_EVENT_WRITE}
    )
    scopes = decision.scopes
    assert goa.CALENDAR_FREEBUSY in scopes
    assert goa.CALENDAR_EVENTS_OWNED in scopes
    assert goa.CALENDAR_EVENTS_LEGACY not in scopes  # new consent prefers owned


def test_feature_available_accepts_legacy_events_grant():
    assert goa.feature_available(
        goa.Feature.CALENDAR_EVENT_WRITE,
        [goa.CALENDAR_EVENTS_LEGACY],
    )
    assert goa.feature_available(
        goa.Feature.CALENDAR_EVENT_WRITE,
        [goa.CALENDAR_EVENTS_OWNED],
    )
    assert not goa.feature_available(
        goa.Feature.CALENDAR_EVENT_WRITE,
        [goa.CALENDAR_FREEBUSY],
    )


def test_full_calendar_scope_forbidden():
    assert "https://www.googleapis.com/auth/calendar" in goa.FORBIDDEN_SCOPES
