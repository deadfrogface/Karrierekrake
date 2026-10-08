"""Regression tests for free private ICS subscriptions."""
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
import pytest
from integrations.calendar.local_ics import refresh_private_ics


def test_private_ics_rejects_http_and_private_addresses(tmp_path):
    target = tmp_path / "calendar.ics"
    with pytest.raises(ValueError):
        refresh_private_ics("http://example.com/calendar.ics", target)
    with pytest.raises(ValueError):
        refresh_private_ics("https://127.0.0.1/calendar.ics", target)
    assert not target.exists()


