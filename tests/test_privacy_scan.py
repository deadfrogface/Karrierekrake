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


# Encoded separators: JSON unicode escape for backslash and URL percent-encoding.
_U5C = _BS + "u005c"
_U5C_UPPER = _BS + "U005C"
_PCT5C = "%" + "5C"
_PCT5C_LOWER = "%" + "5c"
_PCT2F = "%" + "2F"


@pytest.mark.parametrize(
    "label,text",
    [
        ("unicode_escape_lower", _win_path(_U5C)),
        ("unicode_escape_upper", _win_path(_U5C_UPPER)),
        ("unicode_escape_mixed_case", _win_path(_BS + "u005C")),
        ("url_encoded_upper", _win_path(_PCT5C)),
        ("url_encoded_lower", _win_path(_PCT5C_LOWER)),
        ("url_encoded_slash", _win_path(_PCT2F)),
        (
            "mixed_unicode_url_backslash",
            "C:" + _U5C + "Users" + _PCT5C + "Lenovo" + _BS + "AppData",
        ),
        ("json_quoted_unicode_escape", '{"log": "' + _win_path(_U5C) + '"}'),
        ("unc_escaped", _BS * 4 + "Users" + _BS * 2 + "Lenovo" + _BS * 2 + "AppData"),
        ("unc_unicode_escape", _U5C * 2 + "Users" + _U5C + "Lenovo" + _U5C + "AppData"),
        ("unc_url_encoded", _PCT5C * 2 + "Users" + _PCT5C + "Lenovo" + _PCT5C + "AppData"),
    ],
)
def test_windows_user_path_detected_with_encoded_separators(label: str, text: str) -> None:
    assert _windows_hits(text), f"{label}: not flagged: {text!r}"


@pytest.mark.parametrize(
    "text",
    [
        "%USERPROFILE%" + _U5C + "AppData" + _U5C + "Local",
        "%USERPROFILE%" + _PCT5C + "AppData",
        "%USERPROFILE%" + _PCT2F + "AppData",
        "C:" + _PCT5C + "Temp" + _PCT5C + "Karrierekrake",
        "https://example.com/search?q=a" + _PCT5C + "b" + _PCT2F + "c",
        "C:" + _U5C + "Program Files" + _U5C + "Karrierekrake",
        "C:" + _PCT5C + "Program Files" + _PCT5C + "Karrierekrake",
    ],
)
def test_encoded_placeholders_not_flagged(text: str) -> None:
    assert _windows_hits(text) == []


def test_original_text_hits_preserved_after_normalization() -> None:
    # A literal path next to an encoded one: both forms must still be flagged.
    text = _win_path(_BS * 2) + " " + "%" + "41"
    assert _windows_hits(text)


# Profile names with spaces / umlauts (synthetic names only).
_UMLAUT_NAME = "Max M" + chr(0xFC) + "ller"
_SPACE_NAME = "Anna Maria"
_SZ_NAME = "J" + chr(0xF6) + "rg Stra" + chr(0xDF) + "e " + chr(0xE4) + "ber"


def _win_path_named(name: str, sep: str) -> str:
    return sep.join(("C:", "Users", name, "AppData", "x.log"))


@pytest.mark.parametrize("name", [_UMLAUT_NAME, _SPACE_NAME, _SZ_NAME])
@pytest.mark.parametrize(
    "sep",
    [_BS, _BS * 2, _BS * 4, "/", _U5C, _U5C_UPPER, _PCT5C, _PCT5C_LOWER, _PCT2F],
    ids=["bs", "bs2", "bs4", "slash", "u005c", "U005C", "pct5C", "pct5c", "pct2F"],
)
def test_windows_user_path_with_spaces_and_umlauts(name: str, sep: str) -> None:
    assert _windows_hits(_win_path_named(name, sep))


@pytest.mark.parametrize(
    "text",
    [
        _win_path_named(_SPACE_NAME.replace(" ", "%" + "20"), _PCT5C),
        _win_path_named(_UMLAUT_NAME.replace(" ", "%" + "20"), _PCT2F),
        json.dumps({"log": _win_path_named(_UMLAUT_NAME, _BS)}),
        json.dumps({"log": _win_path_named(_UMLAUT_NAME, _BS)}, ensure_ascii=False),
    ],
)
def test_windows_user_path_url_space_and_json_umlaut(text: str) -> None:
    assert _windows_hits(text)


def test_user_segment_regex_no_catastrophic_backtracking() -> None:
    import time

    evil = "C:" + _BS + "Users" + _BS + ("a " * 20000)  # no trailing separator
    start = time.perf_counter()
    assert _windows_hits(evil) == []
    assert time.perf_counter() - start < 1.0


# JSON unicode escape for forward slash (any case), built at runtime.
_U2F = _BS + "u002f"
_U2F_UPPER = _BS + "u002F"
_U2F_ALLCAPS = _BS + "U002F"


@pytest.mark.parametrize(
    "name", ["Lenovo", _UMLAUT_NAME, _SPACE_NAME, _SZ_NAME], ids=["plain", "umlaut", "space", "sz"]
)
@pytest.mark.parametrize(
    "sep", [_U2F, _U2F_UPPER, _U2F_ALLCAPS], ids=["u002f", "u002F", "U002F"]
)
def test_windows_user_path_with_unicode_escaped_slash(name: str, sep: str) -> None:
    assert _windows_hits(_win_path_named(name, sep))


def test_windows_user_path_unicode_slash_mixed_and_json() -> None:
    text = "C:" + _U2F + "Users" + _U5C + _SPACE_NAME.replace(" ", "%" + "20") + _U2F_UPPER + "AppData"
    assert _windows_hits(text)
    assert _windows_hits('{"log": "' + _win_path_named(_UMLAUT_NAME, _U2F) + '"}')


@pytest.mark.parametrize("sep", [_U2F, _U2F_UPPER], ids=["u002f", "u002F"])
def test_unicode_slash_placeholder_not_flagged(sep: str) -> None:
    assert _windows_hits("%USERPROFILE%" + sep + "AppData" + sep + "Local") == []


# --- Placeholders and prose must not be flagged (follow-up d8daf167) ---------
# The widened user segment must not treat env-var / template placeholders or
# Markdown/prose text after a bare "C:\Users\" as a real profile name.
_PH_PERCENT = "%" + "USERNAME" + "%"
_PH_BRACE = "{" + "user" + "}"
_PH_DOLLAR_BRACE = "${" + "user" + "}"
_TICK = chr(96)  # backtick


def _users(sep: str) -> str:
    return "C:" + sep + "Users" + sep


@pytest.mark.parametrize(
    "label,text",
    [
        ("percent_username_bs", _users(_BS) + _PH_PERCENT + _BS + "AppData"),
        ("percent_username_bs2", _users(_BS * 2) + _PH_PERCENT + _BS * 2 + "AppData"),
        ("percent_username_slash", _users("/") + _PH_PERCENT + "/AppData"),
        ("percent_username_u005c", _users(_U5C) + _PH_PERCENT + _U5C + "AppData"),
        ("percent_username_pct5c", _users(_PCT5C) + _PH_PERCENT + _PCT5C + "AppData"),
        ("percent_username_json", json.dumps({"dir": _users(_BS) + _PH_PERCENT + _BS + "AppData"})),
        ("brace_user_bs", _users(_BS) + _PH_BRACE + _BS + "Documents"),
        ("brace_user_bs2", _users(_BS * 2) + _PH_BRACE + _BS * 2 + "Documents"),
        ("brace_user_slash", _users("/") + _PH_BRACE + "/Documents"),
        ("dollar_brace_user", _users(_BS) + _PH_DOLLAR_BRACE + _BS + "Documents"),
        (
            "prose_backtick_double_bs",
            "Pfade wie " + _TICK + _users(_BS * 2) + _TICK + " werden nie geloggt.",
        ),
        (
            "prose_backtick_followed_by_path",
            "Pfade wie " + _TICK + _users(_BS) + _TICK + " werden nie geloggt, nur "
            + _TICK + "%APPDATA%" + _BS + "Karrierekrake" + _TICK + ".",
        ),
        ("prose_sentence_end", "unter " + _users(_BS) + "."),
        (
            "prose_sentence_end_followed_by_path",
            "unter " + _users(_BS) + ". Logs liegen in %APPDATA%" + _BS + "Karrierekrake" + _BS + "logs",
        ),
        (
            "prose_word_end_followed_by_slash",
            "Ordner unter " + _users(_BS) + " werden ignoriert, siehe docs/privacy.md",
        ),
    ],
)
def test_placeholders_and_prose_not_flagged(label: str, text: str) -> None:
    assert _windows_hits(text) == [], f"{label}: false positive: {text!r}"


@pytest.mark.parametrize(
    "label,text",
    [
        # Real-looking names next to the placeholder forms must still be flagged.
        ("percent_inside_name_url_encoded_umlaut", _win_path_named("M%C3%BCller", _BS)),
        ("name_with_dot", _win_path_named("max.mustermann", _BS)),
        ("name_with_trailing_digits", _win_path_named("Lenovo2", _BS * 2)),
        ("prose_with_real_name", "Log unter " + _TICK + _win_path_named(_SPACE_NAME, _BS) + _TICK + "."),
    ],
)
def test_real_user_paths_still_flagged_next_to_placeholder_rules(label: str, text: str) -> None:
    assert _windows_hits(text), f"{label}: not flagged: {text!r}"


# --- Names starting with "!", "," or ";" are valid Win32 profile names ------
# Only whitespace / "." starts may stay excluded (prose after bare "C:\Users\").
@pytest.mark.parametrize(
    "label,text",
    [
        ("bang_documents", _BS.join(("C:", "Users", "!max", "Documents"))),
        ("comma_x", _BS.join(("C:", "Users", ",max", "x"))),
        ("semicolon_x", _BS.join(("C:", "Users", ";max", "x"))),
        ("bang_slash", _users("/") + "!max/Documents"),
        ("comma_bs2", (_BS * 2).join(("C:", "Users", ",max", "x"))),
    ],
)
def test_user_names_starting_with_bang_comma_semicolon_flagged(label: str, text: str) -> None:
    assert _windows_hits(text), f"{label}: not flagged: {text!r}"
