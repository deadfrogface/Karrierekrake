"""Regression: privacy_scan must allow fictional RFC domains used in fixtures."""

from __future__ import annotations

from scripts.privacy_scan import EMAIL_RE, _email_domain_allowed


def test_allow_example_com_and_subdomains():
    assert _email_domain_allowed("example.com")
    assert _email_domain_allowed("corp.example.com")
    assert _email_domain_allowed("mail.example.org")
    assert _email_domain_allowed("example.net")
    assert _email_domain_allowed("localhost")


def test_allow_rfc6761_special_use_tlds():
    """corp.example / foo.test must not fail CI (common fixture pattern)."""
    assert _email_domain_allowed("corp.example")
    assert _email_domain_allowed("fixture.example")
    assert _email_domain_allowed("mail.test")
    assert _email_domain_allowed("user.invalid")
    assert _email_domain_allowed("dev.localhost")


def test_reject_real_looking_domains():
    assert not _email_domain_allowed("gmail.com")
    assert not _email_domain_allowed("firma.de")
    assert not _email_domain_allowed("corp.example.co.uk")


def test_fixture_style_addresses_pass_email_re():
    text = "hr@corp.example.com a@fixture.example person@mail.test"
    domains = [m.group(1).lower() for m in EMAIL_RE.finditer(text)]
    assert domains
    assert all(_email_domain_allowed(d) for d in domains)
