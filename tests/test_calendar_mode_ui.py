"""UI contract: Google Calendar Mode A/B selection before OAuth."""

from __future__ import annotations

from core.config import SettingsConfig
from desktop.i18n import tr


def test_calendar_mode_settings_default_a():
    s = SettingsConfig()
    assert getattr(s, "calendar_google_mode", "A") == "A"


def test_calendar_mode_i18n_keys_present():
    for key in (
        "integrations.calendar.mode_label",
        "integrations.calendar.mode_a",
        "integrations.calendar.mode_b",
        "integrations.calendar.mode_a_rights",
        "integrations.calendar.mode_b_rights",
        "integrations.calendar.mode_a_confirm",
        "integrations.calendar.mode_b_confirm",
    ):
        text = tr(key)
        assert text and text != key
        # End-user copy must not dump raw scope URIs
        assert "googleapis.com" not in text
        assert "client_id" not in text.lower()


def test_settings_connect_uses_authorize_calendar_mode():
    import inspect
    from desktop.pages import settings as settings_mod

    src = inspect.getsource(settings_mod.SettingsPage._privacy_connect_calendar)
    assert "authorize_calendar_mode" in src
    assert "calendar_google_mode" in src
