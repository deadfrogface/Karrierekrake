"""Anschreiben-Guard: Anrede, Geschlecht und Muttersprache (Personaler, 18.10.2026).

Regressionen aus dem 16-Fälle-Lauf ``letters_full_2026-10-18``. Der Guard ließ
dort durch:

- Q4_K_M cl-10: „Meine Muttersprache ist Deutsch“, das Profil nennt nur C2.
- Q2_K_XL cl-10: „ideale Kandidatin“, der Bewerber heißt Nils, das Profil
  nennt kein Geschlecht.
- Q2_K_XL cl-30: „Sehr geehrte Damen und Herren“, die Anzeige nennt
  Frau Quendel.

Regeln:

1. Nennt die Anzeige genau eine Ansprechperson, muss die Anrede genau diese
   Person ansprechen, so wie ``compose_cover_letter`` sie aus der Anzeige baut.
2. Das Geschlecht wird nie aus dem Vornamen geschlossen. Ohne ausdrückliche
   Angabe ist jede gegenderte Selbstbezeichnung (Kandidat/Kandidatin,
   Bewerber/Bewerberin, Fachmann/Fachfrau) ein Fund. Mit Angabe ist nur die
   unpassende Form ein Fund.
3. „Muttersprache“, „muttersprachlich“, „native speaker“ sind nur erlaubt,
   wenn das Profil diese Sprache ausdrücklich als Muttersprache führt.
   C2 oder jede andere Stufe ist keine Muttersprache.

Alle Daten sind synthetisch.
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from core.config import LanguageEntry
from core.cover_guard import prepare_cover_check, screen_prepared_letter
from core.cover_letter import compose_cover_letter
from tests.test_cover_letter_gold import _config_from_case, _job_from_case

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "letter_guard_2026-10-18"
GOLD = ROOT / "tests" / "fixtures" / "anschreiben_gold"

Q4_CL10 = "q4_k_m__cl-10-english-ad"
Q2_CL10 = "q2_k_xl_4b_gsq__cl-10-english-ad"
Q2_CL30 = "q2_k_xl_4b_gsq__cl-30-html-contact"


def _fixture(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def _gold(case_id: str) -> dict:
    return json.loads((GOLD / f"{case_id}.json").read_text(encoding="utf-8"))


def _prepared(case: dict, **kwargs):
    """Profile side exactly as ``rewrite_cover_letter`` builds it."""
    job = _job_from_case(case)
    config = _config_from_case(case)
    seed = compose_cover_letter(job, config)
    assert seed.ok, seed.reason_code
    return prepare_cover_check(
        config, seed.description_used, f"{job.title} {job.company}", **kwargs
    )


def _hits(violations: list[str], needle: str) -> list[str]:
    return [v for v in violations if needle.casefold() in v.casefold()]


# --- fixtures are the recorded run and the Personaler gold -----------------


@pytest.mark.parametrize("name", [Q4_CL10, Q2_CL10, Q2_CL30])
def test_fixture_matches_gold_case(name: str) -> None:
    data = _fixture(name)
    gold = _gold(Path(data["provenance"]["gold_case"]).stem)
    assert data["synthetic"] is True
    assert data["profile"] == gold["profile"]
    assert data["job"] == gold["job"]
    assert data["provenance"]["outcome_in_run"] == "letter_returned"
    assert data["expected_guard"] == "blocked"


# --- regressions: the three letters the guard let through ------------------


def test_q4_cl10_native_german_claim_with_c2_is_blocked() -> None:
    data = _fixture(Q4_CL10)
    assert "Meine Muttersprache ist Deutsch" in data["letter"]
    screened = screen_prepared_letter(data["letter"], _prepared(data))
    assert not screened.ok
    assert _hits(screened.violations, "Muttersprache ist Deutsch")


def test_q2_cl10_ideale_kandidatin_without_profile_gender_is_blocked() -> None:
    data = _fixture(Q2_CL10)
    assert "ideale Kandidatin" in data["letter"]
    screened = screen_prepared_letter(data["letter"], _prepared(data))
    assert not screened.ok
    assert _hits(screened.violations, "ideale Kandidatin")


def test_q2_cl30_generic_salutation_with_named_contact_is_blocked() -> None:
    data = _fixture(Q2_CL30)
    assert data["letter"].startswith("Sehr geehrte Damen und Herren,")
    screened = screen_prepared_letter(data["letter"], _prepared(data))
    assert not screened.ok
    assert _hits(screened.violations, "Sehr geehrte Damen und Herren")


# --- rule 1: named contact --------------------------------------------------


def _with_first_line(letter: str, line: str) -> str:
    rest = letter.split("\n", 1)[1]
    return f"{line}\n{rest}"


def test_cl30_named_salutation_passes() -> None:
    data = _fixture(Q2_CL30)
    letter = _with_first_line(data["letter"], "Sehr geehrte Frau Quendel,")
    screened = screen_prepared_letter(letter, _prepared(data))
    assert screened.ok, screened.violations


@pytest.mark.parametrize(
    "line",
    [
        "Sehr geehrter Herr Quendel,",
        "Sehr geehrte Frau Lotte Quendel,",
        "Sehr geehrte Frau Dr. Quendel,",
        "Sehr geehrte Frau Beispiel,",
        "Guten Tag,",
    ],
)
def test_cl30_wrong_person_or_title_is_blocked(line: str) -> None:
    data = _fixture(Q2_CL30)
    letter = _with_first_line(data["letter"], line)
    screened = screen_prepared_letter(letter, _prepared(data))
    assert not screened.ok
    assert _hits(screened.violations, line.rstrip(","))


def test_cl30_letter_without_salutation_is_blocked() -> None:
    data = _fixture(Q2_CL30)
    letter = data["letter"].split("\n", 2)[2]
    assert not letter.lstrip().casefold().startswith("sehr geehrte")
    screened = screen_prepared_letter(letter, _prepared(data))
    assert not screened.ok
    assert "(keine Anrede)" in screened.violations


def test_cl30_address_header_before_named_salutation_passes() -> None:
    """A custom template may put a sender block above the salutation."""
    data = _fixture(Q2_CL30)
    letter = "Nils Quendel\nMusterhafen\n\n" + _with_first_line(
        data["letter"], "Sehr geehrte Frau Quendel,"
    )
    screened = screen_prepared_letter(letter, _prepared(data))
    assert screened.ok, screened.violations


@pytest.mark.parametrize(
    "case_id",
    ["cl-09-named-contact", "cl-28-titled-contact", "cl-30-html-contact"],
)
def test_expected_salutation_follows_personaler_gold(case_id: str) -> None:
    case = _gold(case_id)
    expected = [m for m in case["must_mention"] if m.startswith("Sehr geehrte")]
    assert len(expected) == 1
    prepared = _prepared(case)
    assert prepared.expected_salutation == expected[0]
    body = "Als Disponent bei Nordkai Spedition GmbH plane ich Touren."
    assert screen_prepared_letter(f"{expected[0]}\n\n{body}\n", prepared).ok
    blocked = screen_prepared_letter(f"Sehr geehrte Damen und Herren,\n\n{body}\n", prepared)
    assert not blocked.ok


def test_dialog_profile_side_with_raw_html_ad_expects_the_same_contact() -> None:
    """The preview dialog passes title plus the raw (HTML) description."""
    case = _gold("cl-30-html-contact")
    config = _config_from_case(case)
    job = _job_from_case(case)
    prepared = prepare_cover_check(
        config, f"{job.title} {job.description}", f"{job.title} {job.company}"
    )
    assert prepared.expected_salutation == "Sehr geehrte Frau Quendel,"


def test_two_contacts_keep_the_general_salutation() -> None:
    case = _gold("cl-29-two-contacts")
    prepared = _prepared(case)
    assert prepared.expected_salutation == ""
    letter = "Sehr geehrte Damen und Herren,\n\nAls Disponent plane ich Touren.\n"
    assert screen_prepared_letter(letter, prepared).ok


def test_ad_without_contact_allows_the_general_salutation() -> None:
    data = _fixture(Q2_CL10)
    assert _prepared(data).expected_salutation == ""


# --- rule 2: gendered self-description -------------------------------------


def test_gender_neutral_letter_passes() -> None:
    data = _fixture(Q2_CL10)
    letter = data["letter"].replace(
        "machen mich eine ideale Kandidatin für diese Position",
        "passen zu den Aufgaben dieser Position",
    )
    assert "Kandidatin" not in letter
    screened = screen_prepared_letter(letter, _prepared(data))
    assert screened.ok, screened.violations


@pytest.mark.parametrize(
    "sentence",
    [
        "Damit bin ich der richtige Kandidat für diese Aufgabe.",
        "Das macht mich zu einem passenden Kandidaten für die Disposition.",
        "Als Bewerberin bringe ich Tourenplanung mit.",
        "Als Bewerber bringe ich Tourenplanung mit.",
        "Ich bin eine erfahrene Fachfrau für Tourenplanung.",
    ],
)
def test_gendered_self_description_without_profile_gender_is_blocked(sentence: str) -> None:
    data = _fixture(Q2_CL10)
    letter = f"Sehr geehrte Damen und Herren,\n\n{sentence}\n"
    screened = screen_prepared_letter(letter, _prepared(data))
    assert not screened.ok
    assert _hits(screened.violations, sentence.rstrip("."))


def test_first_name_never_implies_gender() -> None:
    """Nils is not evidence for a male form."""
    data = _fixture(Q2_CL10)
    assert data["profile"]["application"]["first_name"] == "Nils"
    letter = "Sehr geehrte Damen und Herren,\n\nIch bin der ideale Kandidat für Tourenplanung.\n"
    assert not screen_prepared_letter(letter, _prepared(data)).ok


def test_explicit_profile_gender_allows_only_the_matching_form() -> None:
    data = _fixture(Q2_CL10)
    female = _prepared(data, applicant_gender="w")
    male = _prepared(data, applicant_gender="m")
    she = "Sehr geehrte Damen und Herren,\n\nIch bin eine passende Kandidatin für Tourenplanung.\n"
    he = "Sehr geehrte Damen und Herren,\n\nIch bin ein passender Kandidat für Tourenplanung.\n"
    assert screen_prepared_letter(she, female).ok
    assert not screen_prepared_letter(he, female).ok
    assert screen_prepared_letter(he, male).ok
    assert not screen_prepared_letter(she, male).ok
    # The recorded cl-10 letter stays red for a male or unstated profile.
    assert not screen_prepared_letter(data["letter"], male).ok
    assert not screen_prepared_letter(data["letter"], _prepared(data)).ok


def test_plural_or_third_party_mentions_are_not_self_descriptions() -> None:
    data = _fixture(Q2_CL10)
    letter = (
        "Sehr geehrte Damen und Herren,\n\n"
        "Ich weiß, dass Sie viele Bewerber für Tourenplanung haben.\n"
    )
    assert screen_prepared_letter(letter, _prepared(data)).ok


# --- rule 3: Muttersprache / native ----------------------------------------


def _native_german(case: dict) -> dict:
    out = deepcopy(case)
    for item in out["profile"]["qualifications"]["languages"]:
        if item["language"] == "Deutsch":
            item["level"] = "Muttersprache"
    return out


def test_profile_marking_german_as_native_allows_muttersprache_deutsch() -> None:
    data = _fixture(Q4_CL10)
    screened = screen_prepared_letter(data["letter"], _prepared(_native_german(data)))
    assert screened.ok, screened.violations


def test_c2_blocks_muttersprache_deutsch() -> None:
    data = _fixture(Q4_CL10)
    levels = {i["language"]: i["level"] for i in data["profile"]["qualifications"]["languages"]}
    assert levels["Deutsch"] == "C2"
    letter = "Sehr geehrte Damen und Herren,\n\nMeine Muttersprache ist Deutsch.\n"
    assert not screen_prepared_letter(letter, _prepared(data)).ok


@pytest.mark.parametrize(
    "sentence",
    [
        "Ich spreche muttersprachlich Deutsch.",
        "Ich bin Muttersprachler in Deutsch.",
        "I am a native speaker of German.",
        "Deutsch ist meine Muttersprache.",
        "Ich bin Muttersprachler.",
    ],
)
def test_native_claim_variants_with_c2_are_blocked(sentence: str) -> None:
    data = _fixture(Q4_CL10)
    letter = f"Sehr geehrte Damen und Herren,\n\n{sentence}\n"
    screened = screen_prepared_letter(letter, _prepared(data))
    assert not screened.ok
    assert _hits(screened.violations, sentence.rstrip("."))


def test_native_claim_for_another_language_is_blocked() -> None:
    data = _native_german(_fixture(Q4_CL10))
    prepared = _prepared(data)
    assert screen_prepared_letter(
        "Sehr geehrte Damen und Herren,\n\nDeutsch ist meine Muttersprache.\n", prepared
    ).ok
    assert not screen_prepared_letter(
        "Sehr geehrte Damen und Herren,\n\nEnglisch ist meine Muttersprache.\n", prepared
    ).ok


def test_native_language_from_unconfirmed_cv_extract_does_not_count() -> None:
    """A native mark only counts from the confirmed languages section."""
    from core.config import ExtractReview

    data = _native_german(_fixture(Q4_CL10))
    job = _job_from_case(data)
    config = _config_from_case(data)
    config.profile.qualifications.languages = [
        LanguageEntry(language="Deutsch", level="Muttersprache", source="cv")
    ]
    config.profile.extract_review = ExtractReview(source="cv", confirmed=False)
    prepared = prepare_cover_check(config, job.description, f"{job.title} {job.company}")
    letter = "Sehr geehrte Damen und Herren,\n\nMeine Muttersprache ist Deutsch.\n"
    assert not screen_prepared_letter(letter, prepared).ok


# --- Teamlead #190: narrow technical exclusion, "first language" -----------


@pytest.mark.parametrize(
    "sentence",
    [
        "Ich habe eine Tourenplanungs-App mit React Native gebaut.",
        "Ich habe eine Tourenplanungs-App mit React-Native gebaut.",
        "Ich habe cloud-native Dienste für die Tourenplanung genutzt.",
        "Ich habe Cloud Native Dienste für die Tourenplanung genutzt.",
    ],
)
def test_react_native_and_cloud_native_are_not_language_claims(sentence: str) -> None:
    data = _fixture(Q4_CL10)
    letter = f"Sehr geehrte Damen und Herren,\n\n{sentence}\n"
    prepared = _prepared(data)
    assert prepared.native_languages == frozenset()
    screened = screen_prepared_letter(letter, prepared)
    assert not _hits(screened.violations, sentence.rstrip("."))


@pytest.mark.parametrize(
    "sentence",
    [
        "Ich bin native speaker.",
        "Ich bin Muttersprachler.",
        "Ich bin native speaker für Englisch.",
        "Ich bin Muttersprachler in Englisch.",
        "Ich nutze React Native und bin native speaker.",
        "Ich nutze cloud-native Dienste und bin Muttersprachler in Englisch.",
    ],
)
def test_native_speaker_and_muttersprachler_still_findings(sentence: str) -> None:
    """Profile C2 only, and profile with German (not English) as native."""
    data = _fixture(Q4_CL10)
    letter = f"Sehr geehrte Damen und Herren,\n\n{sentence}\n"
    c2_only = screen_prepared_letter(letter, _prepared(data))
    assert not c2_only.ok
    assert _hits(c2_only.violations, sentence.rstrip("."))
    if "Englisch" in sentence:
        german_native = screen_prepared_letter(letter, _prepared(_native_german(data)))
        assert not german_native.ok
        assert _hits(german_native.violations, sentence.rstrip("."))


def test_first_language_level_counts_as_native() -> None:
    data = deepcopy(_fixture(Q4_CL10))
    for item in data["profile"]["qualifications"]["languages"]:
        if item["language"] == "Englisch":
            item["level"] = "first language"
    prepared = _prepared(data)
    assert prepared.native_languages == frozenset({"englisch"})
    ok = "Sehr geehrte Damen und Herren,\n\nEnglisch ist meine Muttersprache.\n"
    bad = "Sehr geehrte Damen und Herren,\n\nDeutsch ist meine Muttersprache.\n"
    assert screen_prepared_letter(ok, prepared).ok
    assert not screen_prepared_letter(bad, prepared).ok


# --- Kritiker GATE #190: application sentence, unlisted native language ----


def test_application_sentence_does_not_skip_gender_check() -> None:
    data = _fixture(Q2_CL10)
    sentence = "Hiermit bewerbe ich mich als ideale Kandidatin für die ausgeschriebene Position."
    letter = f"Sehr geehrte Damen und Herren,\n\n{sentence}\n"
    prepared = _prepared(data)
    assert prepared.applicant_gender == ""
    screened = screen_prepared_letter(letter, prepared)
    assert not screened.ok
    assert _hits(screened.violations, sentence.rstrip("."))


@pytest.mark.parametrize(
    "sentence",
    [
        "Als Muttersprachler bewerbe ich mich für die ausgeschriebene Position.",
        "Als Muttersprachler bewerbe ich mich bei Northquay Freight GmbH.",
        "Als native speaker freue ich mich auf ein persönlichen Gespräch.",
    ],
)
def test_application_sentence_does_not_skip_native_check(sentence: str) -> None:
    data = _fixture(Q4_CL10)
    letter = f"Sehr geehrte Damen und Herren,\n\n{sentence}\n"
    prepared = _prepared(data)
    assert prepared.native_languages == frozenset()  # Deutsch C2, Englisch B2
    screened = screen_prepared_letter(letter, prepared)
    assert not screened.ok
    assert _hits(screened.violations, sentence.rstrip("."))


@pytest.mark.parametrize(
    "sentence",
    [
        "Meine Muttersprache ist Albanisch.",
        "Albanisch ist meine Muttersprache.",
        "Ich bin Muttersprachler in Tigrinya.",
        "I am a native Tigrinya speaker.",
        "Meine Muttersprache ist Kurmandschi.",
    ],
)
def test_native_claim_for_language_not_in_profile_is_blocked(sentence: str) -> None:
    data = _native_german(_fixture(Q4_CL10))
    prepared = _prepared(data)
    assert prepared.native_languages == frozenset({"deutsch"})
    letter = f"Sehr geehrte Damen und Herren,\n\n{sentence}\n"
    screened = screen_prepared_letter(letter, prepared)
    assert not screened.ok
    assert _hits(screened.violations, sentence.rstrip("."))


@pytest.mark.parametrize(
    "sentence",
    [
        "Meine Muttersprache ist Deutsch.",
        "Deutsch ist meine Muttersprache.",
        "Hiermit bewerbe ich mich als Muttersprachler in Deutsch für die ausgeschriebene Position.",
    ],
)
def test_native_claim_for_profile_native_language_passes(sentence: str) -> None:
    data = _native_german(_fixture(Q4_CL10))
    letter = f"Sehr geehrte Damen und Herren,\n\n{sentence}\n"
    screened = screen_prepared_letter(letter, _prepared(data))
    assert not _hits(screened.violations, sentence.rstrip("."))
