"""Fake provider boundary tests (registry — not widget injection)."""

from __future__ import annotations

import pytest

from integrations.calendar.registry import resolve_calendar_adapter
from integrations.mail.registry import resolve_mail_adapter
from integrations.providers.enums import CalendarProvider, MailProvider, ProviderError


def test_fake_mail_requires_allow_env(monkeypatch):
    monkeypatch.delenv("KARRIEREKRAKE_ALLOW_FAKE_PROVIDERS", raising=False)
    with pytest.raises(ProviderError):
        resolve_mail_adapter(MailProvider.FAKE_INPROCESS)


def test_fake_mail_resolves_at_registry_boundary(monkeypatch, tmp_path):
    monkeypatch.setenv("KARRIEREKRAKE_ALLOW_FAKE_PROVIDERS", "1")
    adapter = resolve_mail_adapter(MailProvider.FAKE_INPROCESS, token_dir=tmp_path)
    assert adapter is not None
    assert adapter.provider is MailProvider.FAKE_INPROCESS
    assert adapter.is_connected()
    result = adapter.sync()
    assert result.fetched == 0


def test_fake_calendar_idempotent_create(monkeypatch, tmp_path):
    monkeypatch.setenv("KARRIEREKRAKE_ALLOW_FAKE_PROVIDERS", "1")
    cal = resolve_calendar_adapter(CalendarProvider.FAKE_INPROCESS, token_dir=tmp_path)
    assert cal is not None
    from integrations.calendar_write import CalendarEventDraft

    draft = CalendarEventDraft(
        case_id="c1",
        title="Interview",
        start="2026-09-22T10:00:00+02:00",
        end="2026-09-22T11:00:00+02:00",
        client_request_id="req-1",
        uid="kk-test",
    )
    r1 = cal.create_event(draft)
    r2 = cal.create_event(draft)
    assert "dup" in r2.external_event_id or r1.external_event_id != ""
    # Second create with same client_request_id must not invent a second paid/real event
    assert r2.external_event_id.startswith("fake-dup") or r2.external_event_id == r1.external_event_id


def test_no_auto_fallback_still_holds():
    from integrations.mail.registry import forbid_auto_fallback
    from integrations.providers.enums import AutoFallbackForbidden

    with pytest.raises(AutoFallbackForbidden):
        forbid_auto_fallback(attempted=["google_gmail", "microsoft_graph"])
