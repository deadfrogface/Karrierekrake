import pytest
from integrations.provider_setup_guides import PROVIDERS, guide_html
from integrations.provider_verified_settings import CLICK_PATHS, MAIL_ENDPOINTS


@pytest.mark.parametrize("provider", list(PROVIDERS))
def test_every_guide_has_provider_path_and_schematic(provider):
    html = guide_html(provider)
    assert CLICK_PATHS[provider] in html
    assert "kein echter Screenshot" in html
    assert "Häufige Probleme" in html


@pytest.mark.parametrize("provider", list(MAIL_ENDPOINTS))
def test_verified_endpoints_are_visible_in_mail_guide(provider):
    incoming, in_port, outgoing, out_port, source = MAIL_ENDPOINTS[provider]
    html = guide_html(provider, "mail")
    assert incoming in html and outgoing in html
    assert str(in_port) in html and str(out_port) in html
    assert source in html


def test_calendar_only_does_not_display_mail_endpoints():
    assert "imap.gmx.net" not in guide_html("gmx", "calendar")
