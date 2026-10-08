import pytest
from integrations.provider_setup_guides import PROVIDERS, guide_html


@pytest.mark.parametrize("provider", list(PROVIDERS))
def test_every_provider_has_offline_html_guide(provider):
    page = guide_html(provider)
    assert "<!doctype html>" in page
    assert "<ol>" in page
    assert "Legende" in page
    assert "KarriereKrake" in page
    assert "keinen bestätigten Live-Test" in page


def test_invalid_provider_and_service_rejected():
    with pytest.raises(ValueError):
        guide_html("https://example.com")
    with pytest.raises(ValueError):
        guide_html("gmx", "unsupported")


def test_service_specific_information():
    page = guide_html("gmx", "mail")
    assert "<b>E-Mail:</b>" in page
    assert "<b>Kalender:</b>" not in page
