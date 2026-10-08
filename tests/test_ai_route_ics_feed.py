from unittest.mock import patch
import pytest

from guenther.ai_route import AIRoute, available_provider_choices
from integrations.calendar.ics_feed import validate_feed_url


def test_local_ai_is_default_without_key_or_network_consent():
    AIRoute().validate()
    assert not available_provider_choices()["local"]["cloud"]


@pytest.mark.parametrize("provider", ["openai", "anthropic", "gemini", "moonshot"])
def test_external_ai_requires_explicit_consent_and_user_key(provider):
    with pytest.raises(ValueError, match="cloud_consent_required"):
        AIRoute(provider=provider, key_present=True).validate()
    with pytest.raises(ValueError, match="user_api_key_required"):
        AIRoute(provider=provider, consent_to_cloud=True).validate()
    AIRoute(provider=provider, consent_to_cloud=True, key_present=True).validate()


@pytest.mark.parametrize("url", [
    "http://calendar.google.com/private.ics",
    "https://localhost/private.ics",
    "https://127.0.0.1/private.ics",
    "https://user:pass@calendar.google.com/private.ics",
    "https://calendar.google.com:8080/private.ics",
])
def test_feed_rejects_unsafe_url(url):
    with pytest.raises(ValueError):
        validate_feed_url(url)


def test_feed_accepts_public_https_google_host():
    with patch("integrations.calendar.ics_feed.socket.getaddrinfo", return_value=[
        (2, 1, 6, "", ("142.250.1.1", 443))
    ]):
        assert validate_feed_url("https://calendar.google.com/calendar/ical/secret/basic.ics").startswith("https://")
