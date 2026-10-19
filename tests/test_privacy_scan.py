"""Regression: privacy_scan must allow fictional RFC domains used in fixtures."""

from __future__ import annotations

import json

import pytest

from scripts.privacy_scan import EMAIL_RE, ROOT, _email_domain_allowed, scan_text


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


# --- JSON-escaped / forward-slash Windows user paths -------------------------
# All paths are assembled at runtime (synthetic user name) so this tracked test
# file itself never contains a literal Windows user path for privacy_scan.

_BS = chr(92)  # backslash
_FAKE = ROOT / "tests" / "fixtures" / "synthetic_privacy_scan_input.json"


def _win_path(sep: str) -> str:
    return sep.join(("C:", "Users", "Lenovo", "AppData", "Local", "Karrierekrake", "x.log"))


def _windows_hits(text: str) -> list[str]:
    return [h for h in scan_text(_FAKE, text) if "windows_user_path" in h]


@pytest.mark.parametrize(
    "label,text",
    [
        ("single_backslash", _win_path(_BS)),
        ("json_escaped_double_backslash", _win_path(_BS * 2)),
        # raw JSON text of a JSON-encoded JSON string (escaped twice)
        ("json_double_encoded_quadruple_backslash", _win_path(_BS * 4)),
        ("forward_slash", _win_path("/")),
        ("lowercase_drive_double_backslash", _win_path(_BS * 2).replace("C:", "d:")),
        ("json_dumps_roundtrip", json.dumps({"log": _win_path(_BS)})),
        ("json_dumps_twice", json.dumps(json.dumps({"log": _win_path(_BS)}))),
    ],
)
def test_windows_user_path_detected_in_escaped_forms(label: str, text: str) -> None:
    assert _windows_hits(text), f"{label}: not flagged: {text!r}"


@pytest.mark.parametrize(
    "text",
    [
        "%USERPROFILE%" + _BS * 2 + "AppData" + _BS * 2 + "Local",
        "%USERPROFILE%" + _BS + "AppData",
        "%USERPROFILE%/AppData/Local",
        "<ThinkPad-Host>",
        json.dumps({"host": "<ThinkPad-Host>", "dir": "%USERPROFILE%" + _BS + "x"}),
        "C:" + _BS * 2 + "Program Files" + _BS * 2 + "Karrierekrake",
    ],
)
def test_placeholders_not_flagged(text: str) -> None:
    assert _windows_hits(text) == []
