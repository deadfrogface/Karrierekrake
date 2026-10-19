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
from core.cover_guard import (
    _gender_violation,
    _native_violation,
    prepare_cover_check,
    screen_prepared_letter,
)
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
    data = _native_german(_fixture(Q4_CL10))
    letter = "Sehr geehrte Damen und Herren,\n\nMeine Muttersprache ist Deutsch.\n"
    screened = screen_prepared_letter(letter, _prepared(data))
    assert screened.ok, screened.violations


def test_cl10_letter_with_native_german_profile_is_blocked_by_sentence_rule() -> None:
    """Teamlead #190 (per language) reverses the earlier sentence rule: in
    „Meine Muttersprache ist Deutsch, und ich verfüge über Englischkenntnisse
    auf B2-Niveau …“ only Deutsch is claimed as native; with Deutsch native in
    the profile that sentence is no native finding. The same letter with
    Deutsch C2 stays a finding (test_q4_cl10_native_german_claim_with_c2_is_blocked)."""
    data = _fixture(Q4_CL10)
    prepared = _prepared(_native_german(data))
    sentence = next(s for s in data["letter"].split("\n") if "Muttersprache" in s)
    native_sentence = sentence[: sentence.index("unterstützt.") + len("unterstützt.")]
    native_sentence = native_sentence[native_sentence.index("Meine Muttersprache"):]
    assert not _native_violation(
        native_sentence, prepared.native_languages, prepared.profile_languages, prepared.level_languages
    )
    assert not _hits(screen_prepared_letter(data["letter"], prepared).violations, "Meine Muttersprache ist Deutsch")


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
    ],
)
def test_native_claim_for_profile_native_language_passes(sentence: str) -> None:
    data = _native_german(_fixture(Q4_CL10))
    letter = f"Sehr geehrte Damen und Herren,\n\n{sentence}\n"
    screened = screen_prepared_letter(letter, _prepared(data))
    assert not _hits(screened.violations, sentence.rstrip("."))


# --- Kritiker #190 (3ec2d1f): German/English language names are one id -----


def _with_levels(case: dict, **levels: str) -> dict:
    out = deepcopy(case)
    out["profile"]["qualifications"]["languages"] = [
        {"language": name, "level": level, "source": "cv"} for name, level in levels.items()
    ]
    return out


@pytest.mark.parametrize(
    "sentence",
    ["I am a native German speaker.", "My native language is German."],
)
def test_english_native_claim_for_profile_native_deutsch_passes(sentence: str) -> None:
    data = _native_german(_fixture(Q4_CL10))
    letter = f"Sehr geehrte Damen und Herren,\n\n{sentence}\n"
    screened = screen_prepared_letter(letter, _prepared(data))
    assert screened.ok, screened.violations


def test_english_level_claim_with_profile_englisch_passes() -> None:
    data = _with_levels(_fixture(Q4_CL10), Deutsch="Muttersprache", Englisch="C1")
    letter = "Sehr geehrte Damen und Herren,\n\nI speak fluent English.\n"
    screened = screen_prepared_letter(letter, _prepared(data))
    assert screened.ok, screened.violations


@pytest.mark.parametrize(
    "sentence",
    ["Meine Muttersprache ist Albanisch.", "I am a native Albanian speaker."],
)
def test_native_albanian_with_profile_native_deutsch_stays_finding(sentence: str) -> None:
    data = _native_german(_fixture(Q4_CL10))
    letter = f"Sehr geehrte Damen und Herren,\n\n{sentence}\n"
    screened = screen_prepared_letter(letter, _prepared(data))
    assert not screened.ok
    assert _hits(screened.violations, sentence.rstrip("."))


def test_native_english_with_profile_englisch_b2_stays_finding() -> None:
    data = _with_levels(_fixture(Q4_CL10), Deutsch="Muttersprache", Englisch="B2")
    sentence = "I am a native English speaker."
    letter = f"Sehr geehrte Damen und Herren,\n\n{sentence}\n"
    screened = screen_prepared_letter(letter, _prepared(data))
    assert not screened.ok
    assert _hits(screened.violations, sentence.rstrip("."))


def test_language_alias_counts_only_for_a_profile_language() -> None:
    """'German' is a posting term; without Deutsch in the profile it stays unconfirmed."""
    data = _with_levels(_fixture(Q4_CL10), Englisch="C1")
    letter = "Sehr geehrte Damen und Herren,\n\nI speak fluent German.\n"
    screened = screen_prepared_letter(letter, _prepared(data))
    assert not screened.ok
    assert _hits(screened.violations, "I speak fluent German")


# --- Personaler #190: Muttersprachler/Muttersprachlerin are gendered -------
# Stricter: „Hiermit bewerbe ich mich als Muttersprachler in Deutsch …“ was a
# positive control (native Deutsch, no profile gender) and is now a finding.

_APPLY_NATIVE_M = (
    "Hiermit bewerbe ich mich als Muttersprachler in Deutsch für die ausgeschriebene Position."
)
_APPLY_NATIVE_W = (
    "Hiermit bewerbe ich mich als Muttersprachlerin in Deutsch für die ausgeschriebene Position."
)


@pytest.mark.parametrize("sentence", [_APPLY_NATIVE_M, _APPLY_NATIVE_W])
def test_muttersprachler_without_profile_gender_is_a_finding(sentence: str) -> None:
    data = _native_german(_fixture(Q4_CL10))
    prepared = _prepared(data)
    assert prepared.native_languages == frozenset({"deutsch"})
    assert prepared.applicant_gender == ""
    letter = f"Sehr geehrte Damen und Herren,\n\n{sentence}\n"
    screened = screen_prepared_letter(letter, prepared)
    assert not screened.ok
    assert _hits(screened.violations, sentence.rstrip("."))


def test_muttersprachler_green_only_with_gender_m() -> None:
    data = _native_german(_fixture(Q4_CL10))
    letter = f"Sehr geehrte Damen und Herren,\n\n{_APPLY_NATIVE_M}\n"
    assert screen_prepared_letter(letter, _prepared(data, applicant_gender="m")).ok
    assert not screen_prepared_letter(letter, _prepared(data, applicant_gender="w")).ok
    assert not screen_prepared_letter(letter, _prepared(data)).ok


def test_muttersprachlerin_green_only_with_gender_w() -> None:
    data = _native_german(_fixture(Q4_CL10))
    letter = f"Sehr geehrte Damen und Herren,\n\n{_APPLY_NATIVE_W}\n"
    assert screen_prepared_letter(letter, _prepared(data, applicant_gender="w")).ok
    assert not screen_prepared_letter(letter, _prepared(data, applicant_gender="m")).ok
    assert not screen_prepared_letter(letter, _prepared(data)).ok


@pytest.mark.parametrize("gender", ["", "m", "w"])
def test_muttersprache_deutsch_stays_gender_neutral(gender: str) -> None:
    data = _native_german(_fixture(Q4_CL10))
    prepared = _prepared(data, applicant_gender=gender)
    for sentence in ("Meine Muttersprache ist Deutsch.", "Deutsch ist meine Muttersprache."):
        letter = f"Sehr geehrte Damen und Herren,\n\n{sentence}\n"
        assert screen_prepared_letter(letter, prepared).ok, sentence


@pytest.mark.parametrize("gender", ["", "m"])
def test_als_muttersprachler_bewerbe_ich_mich_stays_finding_without_native_profile(
    gender: str,
) -> None:
    """C2 profile: the native check fires even when the gender matches."""
    data = _fixture(Q4_CL10)
    sentence = "Als Muttersprachler bewerbe ich mich für die ausgeschriebene Position."
    letter = f"Sehr geehrte Damen und Herren,\n\n{sentence}\n"
    screened = screen_prepared_letter(letter, _prepared(data, applicant_gender=gender))
    assert not screened.ok
    assert _hits(screened.violations, sentence.rstrip("."))


# --- Final rule set (Teamlead, Kritiker, Personaler) -----------------------
# 1) Sentence level, fail-closed. 2) Level exception only for
# „auf muttersprachlichem Niveau“ / „muttersprachliche (Deutsch)kenntnisse“
# with exactly that language at C2 or native. 3) Counter-tests. 4) Profile
# side: near-native is C2, never native; negations are never native.


def _sentence_letter(sentence: str) -> str:
    return f"Sehr geehrte Damen und Herren,\n\n{sentence}\n"


_LEVEL_DE = (
    "Ich spreche Deutsch auf muttersprachlichem Niveau.",
    "Ich verfüge über muttersprachliche Deutschkenntnisse.",
)
# Teamlead 19.10.2026 (spec change, stricter): „muttersprachliche
# …kenntnisse“ is a native claim; only „auf muttersprachlichem Niveau“ stays a
# level phrase that C2 may carry.
_LEVEL_NIVEAU_DE = ("Ich spreche Deutsch auf muttersprachlichem Niveau.",)
_NATIVE_KENNTNISSE_DE = (
    "Ich verfüge über muttersprachliche Deutschkenntnisse.",
    "Meine muttersprachlichen Deutschkenntnisse (C2) helfen mir im Kundenservice.",
)


@pytest.mark.parametrize("sentence", _LEVEL_NIVEAU_DE)
@pytest.mark.parametrize("level", ["C2", "Muttersprache"])
def test_level_phrase_passes_with_deutsch_c2_or_native(sentence: str, level: str) -> None:
    data = _with_levels(_fixture(Q4_CL10), Deutsch=level, Englisch="B2")
    screened = screen_prepared_letter(_sentence_letter(sentence), _prepared(data))
    assert screened.ok, screened.violations


@pytest.mark.parametrize("sentence", _NATIVE_KENNTNISSE_DE)
def test_muttersprachliche_kenntnisse_passes_only_with_native_deutsch(sentence: str) -> None:
    data = _with_levels(_fixture(Q4_CL10), Deutsch="Muttersprache", Englisch="B2")
    screened = screen_prepared_letter(_sentence_letter(sentence), _prepared(data))
    assert screened.ok, screened.violations


@pytest.mark.parametrize("sentence", _NATIVE_KENNTNISSE_DE)
def test_muttersprachliche_kenntnisse_is_finding_with_deutsch_c2_only(sentence: str) -> None:
    data = _with_levels(_fixture(Q4_CL10), Deutsch="C2", Englisch="B2")
    screened = screen_prepared_letter(_sentence_letter(sentence), _prepared(data))
    assert not screened.ok
    assert _hits(screened.violations, sentence.rstrip("."))


@pytest.mark.parametrize("sentence", _LEVEL_DE)
def test_level_phrase_is_finding_with_deutsch_b2(sentence: str) -> None:
    data = _with_levels(_fixture(Q4_CL10), Deutsch="B2", Englisch="B2")
    screened = screen_prepared_letter(_sentence_letter(sentence), _prepared(data))
    assert not screened.ok
    assert _hits(screened.violations, sentence.rstrip("."))


@pytest.mark.parametrize(
    "sentence",
    [
        "Ich spreche Englisch auf muttersprachlichem Niveau.",
        "Ich spreche Polnisch auf muttersprachlichem Niveau.",
        "Ich verfüge über muttersprachliche Kenntnisse.",
        "Ich verfüge über muttersprachliche Englischkenntnisse.",
    ],
)
def test_level_phrase_for_wrong_missing_or_unnamed_language_is_finding(sentence: str) -> None:
    data = _with_levels(_fixture(Q4_CL10), Deutsch="C2", Englisch="B2")
    screened = screen_prepared_letter(_sentence_letter(sentence), _prepared(data))
    assert not screened.ok
    assert _hits(screened.violations, sentence.rstrip("."))


@pytest.mark.parametrize(
    ("sentence", "gender"),
    [
        ("Meine Muttersprache ist Deutsch.", ""),
        ("Als Muttersprachlerin bewerbe ich mich für die ausgeschriebene Position.", "w"),
        ("I am a native German speaker.", ""),
    ],
)
def test_counter_native_claims_with_deutsch_c2_only_are_findings(sentence: str, gender: str) -> None:
    """Must go red if anyone widens the level exception to native claims."""
    data = _with_levels(_fixture(Q4_CL10), Deutsch="C2")
    prepared = _prepared(data, applicant_gender=gender)
    assert prepared.native_languages == frozenset()
    screened = screen_prepared_letter(_sentence_letter(sentence), prepared)
    assert not screened.ok
    assert _hits(screened.violations, sentence.rstrip("."))


@pytest.mark.parametrize(
    "level", ["C2 (nahezu muttersprachlich)", "C2 near native", "near-native"]
)
def test_near_native_profile_is_c2_not_native(level: str) -> None:
    data = _with_levels(_fixture(Q4_CL10), Deutsch="C2", Englisch=level)
    prepared = _prepared(data)
    assert prepared.native_languages == frozenset()
    assert "englisch" in prepared.level_languages
    assert not screen_prepared_letter(
        _sentence_letter("Englisch ist meine Muttersprache."), prepared
    ).ok
    assert screen_prepared_letter(
        _sentence_letter("Ich spreche Englisch auf muttersprachlichem Niveau."), prepared
    ).ok


@pytest.mark.parametrize(
    "level", ["non-native", "keine Muttersprache", "nicht muttersprachlich", "B2 (not native)"]
)
def test_negated_native_level_is_never_native(level: str) -> None:
    data = _with_levels(_fixture(Q4_CL10), Deutsch="C2", Englisch=level)
    prepared = _prepared(data)
    assert prepared.native_languages == frozenset()
    screened = screen_prepared_letter(_sentence_letter("Englisch ist meine Muttersprache."), prepared)
    assert not screened.ok


def test_native_signal_without_named_language_is_finding_even_with_native_profile() -> None:
    """Fail-closed: no identifiable language means the mapping is unclear."""
    data = _native_german(_fixture(Q4_CL10))
    prepared = _prepared(data, applicant_gender="m")
    assert prepared.native_languages == frozenset({"deutsch"})
    assert not screen_prepared_letter(_sentence_letter("Ich bin Muttersprachler."), prepared).ok
    assert not screen_prepared_letter(_sentence_letter("I am a native speaker."), prepared).ok


def test_every_language_in_a_native_sentence_must_be_native() -> None:
    """Teamlead #190 (per language): every language *claimed* as native must be
    native. „Englisch“ in the same native claim is a finding; a separate
    statement with its own level is not (see the per-language tests below)."""
    data = _with_levels(_fixture(Q4_CL10), Deutsch="Muttersprache", Englisch="B2")
    sentence = "Meine Muttersprache ist Deutsch und Englisch."
    screened = screen_prepared_letter(_sentence_letter(sentence), _prepared(data))
    assert not screened.ok
    assert _hits(screened.violations, sentence.rstrip("."))


# --- apply/manager.py: the automatic apply path runs the same rules --------


def _apply_setup(tmp_path, monkeypatch, *, description: str | None = None):
    from core.models import OperatingMode
    from tests.test_cover_approval_apply import _job, _mgr, _ready

    cfg = _ready(
        tmp_path,
        mode=OperatingMode.REVIEW_BEFORE_SUBMIT.value,
        dry_run=True,
        auto_submit=False,
    )
    job = _job("job-guard-apply")
    if description is not None:
        job.description = description
    mgr, captured = _mgr(cfg, monkeypatch)
    return cfg, job, mgr, captured


def _approve_text(cfg, job, edit):
    from apply.preview import build_application_preview
    from core.cover_letter import approve_cover_letter

    preview = build_application_preview(job, cfg)
    assert preview.cover_refusal_code == ""
    text = edit(preview.cover_letter_preview)
    approve_cover_letter(
        job,
        cfg,
        text,
        generated_sha256=preview.cover_letter_sha256,
        profile_fingerprint=preview.cover_profile_fingerprint,
    )
    return preview.cover_letter_preview, text


@pytest.mark.parametrize(
    "sentence",
    [
        "Hiermit bewerbe ich mich als ideale Kandidatin für die ausgeschriebene Position.",
        "Meine Muttersprache ist Deutsch.",
    ],
)
def test_apply_path_blocks_gender_and_native_findings(tmp_path, monkeypatch, sentence) -> None:
    cfg, job, mgr, captured = _apply_setup(tmp_path, monkeypatch)
    _approve_text(cfg, job, lambda text: text.rstrip("\n") + f"\n\n{sentence}\n")
    result = mgr.prepare_and_apply(job)
    assert result.needs_review is True
    assert result.submitted is False
    assert "unsubstantiated_claims" in (result.error_message or "")
    assert captured["calls"] == 0


_CONTACT_AD = (
    "Buchhaltung und Monatsabschlüsse für den Mandantenstamm.\n\n"
    "Ansprechpartnerin: Frau Lotte Quendel."
)


def test_apply_path_blocks_generic_salutation_for_named_contact(tmp_path, monkeypatch) -> None:
    cfg, job, mgr, captured = _apply_setup(tmp_path, monkeypatch, description=_CONTACT_AD)

    def _generic(text: str) -> str:
        assert text.startswith("Sehr geehrte Frau Quendel,")
        return text.replace("Sehr geehrte Frau Quendel,", "Sehr geehrte Damen und Herren,", 1)

    _approve_text(cfg, job, _generic)
    result = mgr.prepare_and_apply(job)
    assert result.needs_review is True
    assert "unsubstantiated_claims" in (result.error_message or "")
    assert captured["calls"] == 0


def test_apply_path_named_contact_letter_reaches_applier(tmp_path, monkeypatch) -> None:
    """Control: the composed letter with the ad's salutation still goes through."""
    cfg, job, mgr, captured = _apply_setup(tmp_path, monkeypatch, description=_CONTACT_AD)
    _original, approved = _approve_text(cfg, job, lambda text: text)
    assert approved.startswith("Sehr geehrte Frau Quendel,")
    stored = Path(cfg.root) / "cover_letters" / f"{job.id}.txt"
    result = mgr.prepare_and_apply(job)
    assert captured["calls"] == 1
    # Like test_cover_approval_apply: the applier gets the stored bytes. On
    # Windows the text-mode save writes \r\n; content stays exactly equal.
    assert captured["cover"].encode("utf-8") == stored.read_bytes()
    assert captured["cover"].replace("\r\n", "\n") == approved
    assert "unsubstantiated_claims" not in (result.error_message or "")


# --- Kritiker gate points 1 and 3 on c511b8b: exact sentences --------------

_KRITIKER_NATIVE_DE = (
    "Meine Muttersprache: Kurmandschi.",
    "Meine Muttersprache ist eigentlich Kurmandschi.",
    "meine muttersprache ist kurmandschi.",
    "Ich spreche Kurmandschi als Muttersprache.",
    "Kurmandschi spreche ich muttersprachlich.",
    "I am a Kurmanji native speaker.",
    "Meine Muttersprache ist Deutsch, Kurmandschi spreche ich ebenfalls muttersprachlich.",
)


@pytest.mark.parametrize("sentence", _KRITIKER_NATIVE_DE)
def test_kritiker_unlisted_native_language_with_native_deutsch_is_finding(sentence: str) -> None:
    data = _native_german(_fixture(Q4_CL10))
    prepared = _prepared(data)
    assert prepared.native_languages == frozenset({"deutsch"})
    screened = screen_prepared_letter(_sentence_letter(sentence), prepared)
    assert not screened.ok
    assert _hits(screened.violations, sentence.rstrip("."))


_KRITIKER_TECH_NATIVE_SPEAKER = (
    "Als cloud native speaker für Englisch bringe ich Erfahrung mit.",
    "Als React-Native speaker of English bringe ich Erfahrung mit.",
)


@pytest.mark.parametrize("sentence", _KRITIKER_TECH_NATIVE_SPEAKER)
def test_kritiker_tech_compound_before_speaker_is_native_claim(sentence: str) -> None:
    data = _with_levels(_fixture(Q4_CL10), Deutsch="C2", Englisch="B2")
    screened = screen_prepared_letter(_sentence_letter(sentence), _prepared(data))
    assert not screened.ok
    assert _hits(screened.violations, sentence.rstrip("."))


@pytest.mark.parametrize(
    "sentence",
    ["Ich entwickle mit React Native.", "Ich plane cloud-native Architekturen."],
)
def test_plain_tech_mentions_stay_ok(sentence: str) -> None:
    data = _with_levels(_fixture(Q4_CL10), Deutsch="C2", Englisch="B2")
    screened = screen_prepared_letter(_sentence_letter(sentence), _prepared(data))
    assert not _hits(screened.violations, sentence.rstrip("."))


@pytest.mark.parametrize(
    ("sentence", "levels"),
    [
        ("Meine Muttersprache ist Deutsch.", {"Deutsch": "Muttersprache"}),
        ("I am a native German speaker.", {"Deutsch": "Muttersprache"}),
        ("Ich spreche Deutsch auf muttersprachlichem Niveau.", {"Deutsch": "C2"}),
        ("Ich verfüge über muttersprachliche Deutschkenntnisse.", {"Deutsch": "Muttersprache"}),
    ],
)
def test_positive_controls_stay_green_after_clause_rule(sentence: str, levels: dict) -> None:
    data = _with_levels(_fixture(Q4_CL10), **levels)
    screened = screen_prepared_letter(_sentence_letter(sentence), _prepared(data))
    assert screened.ok, screened.violations


# --- Kritiker findings on #190 (merge with cd4bb8d0) ------------------------
# Profile for every example: native language Deutsch.


def _native_deutsch_prepared(**kwargs):
    data = _native_german(_fixture(Q4_CL10))
    prepared = _prepared(data, **kwargs)
    assert prepared.native_languages == frozenset({"deutsch"})
    return prepared


def _assert_finding(sentence: str, prepared) -> None:
    screened = screen_prepared_letter(_sentence_letter(sentence), prepared)
    assert not screened.ok, sentence
    assert _hits(screened.violations, sentence.rstrip(".")), screened.violations


# Finding 1: every language in an enumeration, not only the marker's neighbour.
_FINDING1_ENUMERATION = (
    "Meine Muttersprache ist Deutsch und auch Kurmandschi.",
    "Meine Muttersprachen sind Deutsch und Zazaki.",
    "I am a native speaker of German and Kurmanji.",
    "Mother tongue: German and Kurmanji.",
)


@pytest.mark.parametrize("sentence", _FINDING1_ENUMERATION)
def test_finding1_enumerated_unlisted_language_is_finding(sentence: str) -> None:
    _assert_finding(sentence, _native_deutsch_prepared())


@pytest.mark.parametrize(
    "sentence",
    [
        "muttersprachliche Kenntnisse in Deutsch und Kurmandschi.",
        "Ich verfüge über muttersprachliche Kenntnisse in Deutsch und Kurmandschi.",
    ],
)
def test_finding1_level_phrase_enumeration_needs_every_language_at_c2(sentence: str) -> None:
    """Profile: Deutsch C2, not native. Kurmandschi is not in the profile."""
    data = _with_levels(_fixture(Q4_CL10), Deutsch="C2")
    prepared = _prepared(data)
    assert prepared.native_languages == frozenset()
    assert prepared.level_languages == frozenset({"deutsch"})
    _assert_finding(sentence, prepared)



# Finding 2: a stop word next to the marker must not end the check.
_FINDING2_STOP_WORDS = (
    "Meine Muttersprache ist das Kurmandschi und ich spreche Deutsch.",
    "Meine Muttersprache ist nicht Deutsch sondern Kurmandschi.",
)


@pytest.mark.parametrize("sentence", _FINDING2_STOP_WORDS)
def test_finding2_stop_word_does_not_end_native_check(sentence: str) -> None:
    _assert_finding(sentence, _native_deutsch_prepared())


# Finding 3: more native signals. Teamlead: „zweisprachig“/„bilingual“ claim
# two native languages, so both must be native in the profile.


def test_finding3_erstsprache_is_native_signal() -> None:
    prepared = _native_deutsch_prepared()
    _assert_finding("Meine Erstsprache ist Kurmandschi.", prepared)
    assert screen_prepared_letter(_sentence_letter("Meine Erstsprache ist Deutsch."), prepared).ok


def test_finding3_natively_is_native_signal() -> None:
    prepared = _native_deutsch_prepared()
    _assert_finding("I speak Kurmanji natively.", prepared)
    assert screen_prepared_letter(_sentence_letter("I speak German natively."), prepared).ok


def test_finding3_zweisprachig_needs_both_languages_native() -> None:
    sentence = "Ich bin zweisprachig mit Deutsch und Kurmandschi aufgewachsen."
    _assert_finding(sentence, _native_deutsch_prepared())
    _assert_finding("Ich bin zweisprachig mit Deutsch aufgewachsen.", _native_deutsch_prepared())
    both = _prepared(
        _with_levels(_fixture(Q4_CL10), Deutsch="Muttersprache", Kurmandschi="Muttersprache")
    )
    assert both.native_languages == frozenset({"deutsch", "kurmandschi"})
    screened = screen_prepared_letter(_sentence_letter(sentence), both)
    assert screened.ok, screened.violations


def test_finding3_bilingual_needs_both_languages_native() -> None:
    sentence = "I am bilingual in German and Kurmanji."
    _assert_finding(sentence, _native_deutsch_prepared())
    both = _prepared(
        _with_levels(_fixture(Q4_CL10), Deutsch="Muttersprache", Türkisch="Muttersprache")
    )
    assert both.native_languages == frozenset({"deutsch", "türkisch"})
    ok = "I am bilingual in German and Turkish."
    screened = screen_prepared_letter(_sentence_letter(ok), both)
    assert screened.ok, screened.violations


# Finding 4: profile side. Approximations are C2, negations are nothing;
# none of them is native.
_FINDING4_APPROXIMATIONS = (
    "fast wie Muttersprache",
    "muttersprachenah",
    "Muttersprachniveau",
    "almost native",
    "native-like",
)
_FINDING4_NEGATIONS = ("kein native speaker", "Muttersprache: nein")


@pytest.mark.parametrize("level", _FINDING4_APPROXIMATIONS)
def test_finding4_approximation_in_profile_is_c2_not_native(level: str) -> None:
    prepared = _prepared(_with_levels(_fixture(Q4_CL10), Deutsch=level))
    assert prepared.native_languages == frozenset()
    assert prepared.level_languages == frozenset({"deutsch"})
    _assert_finding("Meine Muttersprache ist Deutsch.", prepared)


@pytest.mark.parametrize("level", _FINDING4_NEGATIONS)
def test_finding4_negation_in_profile_is_neither_native_nor_c2(level: str) -> None:
    prepared = _prepared(_with_levels(_fixture(Q4_CL10), Deutsch=level))
    assert prepared.native_languages == frozenset()
    assert prepared.level_languages == frozenset()
    _assert_finding("Meine Muttersprache ist Deutsch.", prepared)


# Finding 5: the apply path takes native languages (and gender) from the
# profile in both scans. Profile: Deutsch Muttersprache.


def _apply_setup_native_deutsch(tmp_path, monkeypatch):
    cfg, job, mgr, captured = _apply_setup(tmp_path, monkeypatch)
    cfg.profile.qualifications.languages = [
        LanguageEntry(language="Deutsch", level="Muttersprache", source="manual")
    ]
    return cfg, job, mgr, captured


def test_finding5_apply_path_lets_profile_native_language_through(tmp_path, monkeypatch) -> None:
    cfg, job, mgr, captured = _apply_setup_native_deutsch(tmp_path, monkeypatch)
    sentence = "Deutsch ist meine Muttersprache."
    _original, approved = _approve_text(cfg, job, lambda text: text.rstrip("\n") + f"\n\n{sentence}\n")
    result = mgr.prepare_and_apply(job)
    assert "unsubstantiated_claims" not in (result.error_message or ""), result.error_message
    assert captured["calls"] == 1
    assert sentence in captured["cover"]


def test_finding5_apply_path_blocks_unlisted_native_language(tmp_path, monkeypatch) -> None:
    cfg, job, mgr, captured = _apply_setup_native_deutsch(tmp_path, monkeypatch)
    sentence = "Meine Muttersprache ist Kurmandschi."
    _approve_text(cfg, job, lambda text: text.rstrip("\n") + f"\n\n{sentence}\n")
    result = mgr.prepare_and_apply(job)
    assert result.needs_review is True
    assert result.submitted is False
    assert "unsubstantiated_claims" in (result.error_message or "")
    assert captured["calls"] == 0


# Note A (Teamlead #190): „deutscher Muttersprachler“ is a gendered
# self-description AND a native claim for Deutsch (adjective → language).
_DEUTSCHER_MUTTERSPRACHLER = "Ich bin deutscher Muttersprachler."


@pytest.mark.parametrize("gender", ["w", "d", ""])
def test_note_deutscher_muttersprachler_is_gendered_for_female_nonbinary_unstated(gender: str) -> None:
    _assert_finding(_DEUTSCHER_MUTTERSPRACHLER, _native_deutsch_prepared(applicant_gender=gender))


def test_note_deutscher_muttersprachler_passes_with_male_native_deutsch() -> None:
    prepared = _native_deutsch_prepared(applicant_gender="m")
    screened = screen_prepared_letter(_sentence_letter(_DEUTSCHER_MUTTERSPRACHLER), prepared)
    assert screened.ok, screened.violations


@pytest.mark.parametrize(
    "levels",
    [{"Deutsch": "C2"}, {"Deutsch": "B2", "Kurmandschi": "Muttersprache"}],
)
def test_note_deutscher_muttersprachler_is_native_claim_for_deutsch(levels: dict) -> None:
    prepared = _prepared(_with_levels(_fixture(Q4_CL10), **levels), applicant_gender="m")
    assert "deutsch" not in prepared.native_languages
    _assert_finding(_DEUTSCHER_MUTTERSPRACHLER, prepared)


# Note B (Teamlead correction): the language field „Deutsch (Muttersprache)“
# is normalised to deutsch and counts as native.


def test_note_language_field_with_native_parenthesis_is_native_deutsch() -> None:
    prepared = _prepared(_with_levels(_fixture(Q4_CL10), **{"Deutsch (Muttersprache)": ""}))
    assert prepared.native_languages == frozenset({"deutsch"})
    assert prepared.profile_languages == frozenset({"deutsch"})
    screened = screen_prepared_letter(_sentence_letter("Meine Muttersprache ist Deutsch."), prepared)
    assert screened.ok, screened.violations
    _assert_finding("Meine Muttersprache ist Kurmandschi.", prepared)


@pytest.mark.parametrize("name", ["Deutsch (C2)", "Deutsch (fast wie Muttersprache)"])
def test_note_language_field_with_level_parenthesis_is_not_native(name: str) -> None:
    prepared = _prepared(_with_levels(_fixture(Q4_CL10), **{name: ""}))
    assert prepared.native_languages == frozenset()
    assert prepared.level_languages == frozenset({"deutsch"})
    _assert_finding("Meine Muttersprache ist Deutsch.", prepared)


# Accepted false positives stay findings (fail-closed).
@pytest.mark.parametrize(
    "sentence",
    [
        "Meine Muttersprache ist natürlich Deutsch.",
        "Deutsch, meine Muttersprache, setze ich täglich ein.",
    ],
)
def test_note_accepted_false_positives_stay_findings(sentence: str) -> None:
    _assert_finding(sentence, _native_deutsch_prepared())


# --- Teamlead #190 (head b59ae738): findings end in needs_confirmation ----
# Empty profile gender: the guard guesses nothing. Every gendered
# self-description of the existing rule and every native finding ends in
# needs_confirmation on the apply path; the approved letter stays unchanged.


@pytest.mark.parametrize(
    "sentence",
    [
        "Hiermit bewerbe ich mich als Muttersprachler in Deutsch für die ausgeschriebene Position.",
        "Hiermit bewerbe ich mich als Muttersprachlerin in Deutsch für die ausgeschriebene Position.",
        "Ich bin deutscher Muttersprachler.",
        "Meine Muttersprache ist Kurmandschi.",
    ],
)
def test_teamlead_finding_ends_in_needs_confirmation_letter_unchanged(
    tmp_path, monkeypatch, sentence
) -> None:
    from core.models import JobStatus

    cfg, job, mgr, captured = _apply_setup_native_deutsch(tmp_path, monkeypatch)
    assert prepare_cover_check(cfg, job.description).applicant_gender == ""
    _original, approved = _approve_text(cfg, job, lambda text: text.rstrip("\n") + f"\n\n{sentence}\n")
    stored = Path(cfg.root) / "cover_letters" / f"{job.id}.txt"
    before = stored.read_bytes()
    result = mgr.prepare_and_apply(job)
    assert result.needs_review is True
    assert result.submitted is False
    assert result.error_message == "needs_confirmation: unsubstantiated_claims"
    assert captured["calls"] == 0
    assert mgr.db.get_job(job.id).status == JobStatus.NEEDS_REVIEW.value
    assert stored.read_bytes() == before
    assert before.decode("utf-8").replace("\r\n", "\n") == approved


def test_teamlead_guard_reports_and_never_rewrites_the_letter() -> None:
    letter = _sentence_letter("Ich bin deutscher Muttersprachler.")
    screened = screen_prepared_letter(letter, _native_deutsch_prepared())
    assert not screened.ok
    assert screened.violations == ["Ich bin deutscher Muttersprachler."]
    assert letter == _sentence_letter("Ich bin deutscher Muttersprachler.")


# Teamlead #190: common non-language words next to a native signal are no
# native/gender finding. (Other claim checks, e.g. a job title the profile
# does not carry, stay independent and are not part of this test.)
_COUNTER_CASES = (
    ("Meine Muttersprache ist Deutsch, und ich habe sehr gute Kenntnisse in Projektmanagement.", ""),
    ("Als Muttersprachlerin im Deutschen arbeite ich als Ingenieurin.", "w"),
    ("Deutsch ist meine Muttersprache, ich bin Fachinformatiker für Systemintegration.", ""),
    ("Native German speaker with experience as a Software Engineer.", ""),
    ("Meine Muttersprache ist Deutsch und ich habe Berufserfahrung im Bereich Buchhaltung.", ""),
    ("Deutsch ist meine Muttersprache und im Team des Unternehmens kommuniziere ich klar.", ""),
    ("Meine Muttersprache ist Deutsch und ich habe Erfahrung in der Position als Buchhalterin.", ""),
    ("Meine Muttersprache ist Deutsch, die Stelle als Disponent reizt mich sehr.", ""),
    ("Als Muttersprachler in Deutsch bringe ich Kenntnisse in Buchhaltung mit.", "m"),
    ("I am a native German speaker and work as a Project Manager.", ""),
    ("Deutsch ist meine Muttersprache und meine Erfahrung als Industriekauffrau passt zur Stelle.", ""),
)


@pytest.mark.parametrize(("sentence", "gender"), _COUNTER_CASES)
def test_teamlead_counter_case_is_no_native_or_gender_finding(sentence: str, gender: str) -> None:
    prepared = _native_deutsch_prepared(applicant_gender=gender)
    assert not _native_violation(
        sentence, prepared.native_languages, prepared.profile_languages, prepared.level_languages
    ), sentence
    assert not _gender_violation(sentence, prepared.applicant_gender), sentence


# Teamlead #190, profile level: „Erstsprache“ is native; „zweisprachig“ and
# „bilingual“ are C2 for the explicitly named languages only, never native.


def _languages_profile(*entries: tuple[str, str]):
    out = deepcopy(_fixture(Q4_CL10))
    out["profile"]["qualifications"]["languages"] = [
        {"language": name, "level": level, "source": "cv"} for name, level in entries
    ]
    return _prepared(out)


def test_teamlead_profile_erstsprache_is_native() -> None:
    prepared = _languages_profile(("Deutsch", "Erstsprache"))
    assert prepared.native_languages == frozenset({"deutsch"})
    screened = screen_prepared_letter(_sentence_letter("Meine Muttersprache ist Deutsch."), prepared)
    assert screened.ok, screened.violations


@pytest.mark.parametrize("level", ["zweisprachig", "bilingual", "Zweisprachig aufgewachsen"])
def test_teamlead_profile_bilingual_level_is_c2_for_that_entry(level: str) -> None:
    prepared = _languages_profile(("Deutsch", "Muttersprache"), ("Englisch", level))
    assert prepared.native_languages == frozenset({"deutsch"})
    assert prepared.level_languages == frozenset({"deutsch", "englisch"})
    _assert_finding("Englisch ist meine Muttersprache.", prepared)


def test_teamlead_profile_bilingual_with_two_named_languages_is_c2_for_both() -> None:
    prepared = _languages_profile(("Deutsch/Englisch", "zweisprachig"))
    assert prepared.native_languages == frozenset()
    assert prepared.level_languages == frozenset({"deutsch", "englisch"})
    assert prepared.profile_languages == frozenset({"deutsch", "englisch"})


def test_teamlead_profile_bilingual_without_named_language_counts_for_none() -> None:
    prepared = _languages_profile(("", "zweisprachig"))
    assert prepared.native_languages == frozenset()
    assert prepared.level_languages == frozenset()
    assert prepared.profile_languages == frozenset()


_KRITIKER_BILINGUAL_LETTER = "Ich bin zweisprachig mit Deutsch und Englisch aufgewachsen."


def test_kritiker_same_word_profile_bilingual_c2_letter_bilingual_is_finding() -> None:
    """UNSICHER (Teamlead pending): profile „zweisprachig“ = C2, letter = native claim."""
    prepared = _languages_profile(("Deutsch", "Muttersprache"), ("Englisch", "zweisprachig"))
    assert "englisch" not in prepared.native_languages
    _assert_finding(_KRITIKER_BILINGUAL_LETTER, prepared)


def test_kritiker_same_letter_with_both_native_is_no_finding() -> None:
    prepared = _languages_profile(("Deutsch", "Muttersprache"), ("Englisch", "Muttersprache"))
    screened = screen_prepared_letter(_sentence_letter(_KRITIKER_BILINGUAL_LETTER), prepared)
    assert screened.ok, screened.violations



# --- Teamlead #190: per language, native self-reference, level phrase -----
# Profile „Deutsch Muttersprache“. A native claim is checked against the
# profile entry of exactly the claimed language; other languages in the
# sentence with their own level do not matter.
_PER_LANGUAGE_COUNTER_CASES = (
    "Meine Muttersprache ist Deutsch, Englisch spreche ich auf B2-Niveau.",
    "Deutsch ist meine Muttersprache und ich arbeite gern im Team.",
    "Die Kommunikation mit Native Speakern im Hafen gehört zu meinen Aufgaben.",
    "Ich habe Native-Apps für die Tourenplanung genutzt.",
    "Deutsch spreche ich auf muttersprachlichem Niveau, Englisch auf B2.",
    "Meine Muttersprache ist Deutsch, und ich verfüge über Englischkenntnisse auf B2-Niveau, "
    "was die Kommunikation im internationalen Umfeld unterstützt.",
    "Ich entwickle native Apps für iOS.",
    "Ich arbeite mit Native Speakers aus Irland zusammen.",
)


@pytest.mark.parametrize("sentence", _PER_LANGUAGE_COUNTER_CASES)
def test_teamlead_per_language_counter_case_is_no_finding(sentence: str) -> None:
    prepared = _prepared(_with_levels(_fixture(Q4_CL10), Deutsch="Muttersprache", Englisch="B2"))
    screened = screen_prepared_letter(_sentence_letter(sentence), prepared)
    assert screened.ok, screened.violations


@pytest.mark.parametrize("level", ["Muttersprache", "Erstsprache"])
def test_teamlead_level_phrase_with_native_or_erstsprache_profile_is_no_finding(level: str) -> None:
    prepared = _prepared(_with_levels(_fixture(Q4_CL10), Deutsch=level))
    for sentence in (
        "Ich spreche Deutsch auf muttersprachlichem Niveau.",
        "Deutsch spreche ich auf muttersprachlichem Niveau, Englisch auf B2.",
    ):
        screened = screen_prepared_letter(_sentence_letter(sentence), prepared)
        assert screened.ok, (sentence, screened.violations)


@pytest.mark.parametrize(
    "sentence",
    [
        "Meine Muttersprache ist Deutsch und Englisch.",
        "Ich spreche Deutsch und Englisch auf muttersprachlichem Niveau.",
        "I speak English natively.",
        "I am a native English speaker.",
        "Als Muttersprachler in Englisch bringe ich Erfahrung mit.",
    ],
)
def test_teamlead_claimed_language_below_native_stays_finding(sentence: str) -> None:
    prepared = _prepared(
        _with_levels(_fixture(Q4_CL10), Deutsch="Muttersprache", Englisch="B2"), applicant_gender="m"
    )
    _assert_finding(sentence, prepared)


# --- Teamlead #190: structured findings for per-finding confirmation -------
# Every finding carries the sentence, a kind, the data for a readable reason
# and a key bound to the exact letter text (sha256 of letter, sentence, kind).
# native / gender / salutation can be confirmed by the user; other claims
# (licence, employer, metrics …) stay a hard block.

import hashlib  # noqa: E402

import core.cover_guard as _cg  # noqa: E402


def _findings(letter: str, prepared):
    return _cg.screen_findings(letter, prepared)


def test_findings_native_carries_language_and_profile_level() -> None:
    data = _fixture(Q4_CL10)
    found = [f for f in _findings(data["letter"], _prepared(data)) if f.kind == "native"]
    assert found, "q4 cl-10 with Deutsch C2 must stay a native finding"
    first = found[0]
    assert "Muttersprache ist Deutsch" in first.sentence
    assert first.language == "deutsch"
    assert "C2" in first.profile_level
    assert first.confirmable is True


def test_findings_gender_is_confirmable() -> None:
    data = _fixture(Q2_CL10)
    found = [f for f in _findings(data["letter"], _prepared(data)) if f.kind == "gender"]
    assert found and "ideale Kandidatin" in found[0].sentence
    assert found[0].confirmable is True


def test_findings_salutation_is_a_guard_finding_with_expected_text() -> None:
    """Teamlead #7: same rule, needs_confirmation, the letter is never changed."""
    data = _fixture(Q2_CL30)
    letter = data["letter"]
    before = str(letter)
    found = [f for f in _findings(letter, _prepared(data)) if f.kind == "salutation"]
    assert letter == before
    assert found and found[0].sentence.startswith("Sehr geehrte Damen und Herren")
    assert found[0].expected == "Sehr geehrte Frau Quendel,"
    assert found[0].confirmable is True


def test_findings_licence_claim_is_not_confirmable() -> None:
    prepared = _prepared(_fixture(Q4_CL10))
    found = _findings(_sentence_letter("Ich besitze den Führerschein der Klasse CE."), prepared)
    claims = [f for f in found if f.kind == "claim"]
    assert claims and claims[0].confirmable is False


def test_native_sentence_with_licence_claim_keeps_a_hard_claim_finding() -> None:
    """Confirming the native part must not release a licence claim in the same sentence."""
    prepared = _prepared(_fixture(Q4_CL10))
    sentence = "Meine Muttersprache ist Deutsch und ich besitze den Führerschein der Klasse CE."
    kinds = {f.kind for f in _findings(_sentence_letter(sentence), prepared)}
    assert {"native", "claim"} <= kinds


def test_finding_key_is_bound_to_letter_sentence_and_kind() -> None:
    data = _fixture(Q4_CL10)
    prepared = _prepared(data)
    first = next(f for f in _findings(data["letter"], prepared) if f.kind == "native")
    expected = hashlib.sha256(
        f"{data['letter']}\x00{first.sentence}\x00native".encode()
    ).hexdigest()
    assert first.key == expected
    assert _cg.finding_key(data["letter"], first.sentence, "native") == expected
    regenerated = data["letter"] + "\nMit freundlichen Grüßen\n"
    again = next(f for f in _findings(regenerated, prepared) if f.kind == "native")
    assert again.sentence == first.sentence
    assert again.key != first.key


def test_screen_prepared_letter_violations_unchanged_by_findings_api() -> None:
    data = _fixture(Q4_CL10)
    prepared = _prepared(data)
    sentences = [f.sentence for f in _findings(data["letter"], prepared)]
    violations = screen_prepared_letter(data["letter"], prepared).violations
    assert violations == list(dict.fromkeys(sentences))


def test_apply_path_salutation_finding_keeps_letter_bytes(tmp_path, monkeypatch) -> None:
    """Teamlead #7: a salutation finding is needs_confirmation; the approved
    letter on disk is never changed and the applier is never called."""
    cfg, job, mgr, captured = _apply_setup(tmp_path, monkeypatch, description=_CONTACT_AD)
    _approve_text(
        cfg,
        job,
        lambda text: text.replace("Sehr geehrte Frau Quendel,", "Sehr geehrte Damen und Herren,", 1),
    )
    stored = Path(cfg.root) / "cover_letters" / f"{job.id}.txt"
    before = stored.read_bytes()
    result = mgr.prepare_and_apply(job)
    assert result.needs_review is True
    assert "needs_confirmation" in (result.error_message or "")
    assert captured["calls"] == 0
    assert stored.read_bytes() == before


# --- fp190 probe (Personaler sentence) on the round-3 head -----------------
# „deutscher Muttersprachler“ names Deutsch; the company after „bei der“ is no
# second claimed language. The gender part stays a finding (no profile gender).


def test_probe_deutscher_muttersprachler_bei_company_is_no_native_finding() -> None:
    sentence = "Als deutscher Muttersprachler bei der Nordkai Spedition GmbH koordiniere ich Touren."
    prepared = _native_deutsch_prepared()
    assert not _native_violation(
        sentence, prepared.native_languages, prepared.profile_languages, prepared.level_languages
    )
    kinds = {f.kind for f in _cg.screen_findings(_sentence_letter(sentence), prepared)}
    assert "gender" in kinds and "native" not in kinds


@pytest.mark.parametrize(
    "sentence",
    [
        "Neben Deutsch ist meine Muttersprache Kurmandschi.",
        "Als deutscher Muttersprachler und Kurmandschi-Muttersprachler koordiniere ich Touren.",
    ],
)
def test_probe_language_after_found_language_still_counts(sentence: str) -> None:
    _assert_finding(sentence, _native_deutsch_prepared())


@pytest.mark.parametrize(
    "sentence",
    [
        "Deutsch ist meine Muttersprache, Kurmandschi auch.",
        "Deutsch ist meine Muttersprache, Kurmandschi ebenfalls.",
        "Deutsch ist meine Muttersprache, ebenso Kurmandschi.",
    ],
)
def test_round3_comma_enumeration_after_found_language_still_counts(sentence: str) -> None:
    """Per language must not open a hole: after „Deutsch ist meine Muttersprache“
    a comma without its own level continues the native enumeration."""
    _assert_finding(sentence, _native_deutsch_prepared())


# --- #190 fix 3: a filler adverb is never reported as the claimed language --
# „Meine Muttersprache ist natürlich Deutsch.“ stays a finding (accepted false
# positive, fail-closed), but the reason must not name „natürlich“ as a language.


@pytest.mark.parametrize("native_deutsch", [False, True])
@pytest.mark.parametrize(
    "sentence",
    [
        "Meine Muttersprache ist natürlich Deutsch.",
        "Meine Muttersprache ist natürlich Polnisch.",
        "Natürlich bin ich Muttersprachler.",
        "Meine Muttersprache ist selbstverständlich Deutsch.",
    ],
)
def test_natuerlich_is_not_reported_as_the_native_language(sentence: str, native_deutsch: bool) -> None:
    from core.cover_guard import screen_findings

    prepared = _native_deutsch_prepared() if native_deutsch else _prepared(_fixture(Q4_CL10))
    letter = _sentence_letter(sentence)
    natives = [f for f in screen_findings(letter, prepared) if f.kind == "native"]
    assert natives, "the sentence stays a native finding (fail-closed)"
    for finding in natives:
        assert finding.language.casefold() not in {"natürlich", "selbstverständlich"}, finding


def test_unknown_language_name_is_still_reported_by_name() -> None:
    """Counter-case: a real (custom) language name keeps its readable reason."""
    from core.cover_guard import screen_findings

    letter = _sentence_letter("Meine Muttersprache ist Kurmandschi.")
    natives = [f for f in screen_findings(letter, _prepared(_fixture(Q4_CL10))) if f.kind == "native"]
    assert natives and natives[0].language == "kurmandschi"


# --- Kritiker 19.10.2026: precision fix for tech words must never weaken -----
# Explicit native-language claims keep blocking (green before and after the
# Microsoft fix). Profile: Deutsch native, Englisch known.
_REG_NATIVE = frozenset({"deutsch"})
_REG_KNOWN = frozenset({"deutsch", "englisch"})


@pytest.mark.parametrize(
    "sentence",
    [
        "Meine Muttersprache: Klingonisch.",
        "Ich bin Muttersprachler.",
        "Ich bin Muttersprachlerin und bringe Erfahrung mit.",
        "Meine Muttersprache ist Französisch.",
        "Muttersprache Französisch.",
        "Meine Muttersprache ist Deutsch und Kurmandschi.",
        "I am a native speaker.",
        "I am a native speaker of Klingon.",
        "I am a native Klingon speaker.",
        "I am a native French speaker.",
        "French is my native language.",
    ],
)
def test_explicit_native_claim_without_profile_evidence_still_blocks(sentence: str) -> None:
    from core.cover_guard import _native_check

    assert _native_check(sentence, _REG_NATIVE, _REG_KNOWN)[0] is True


@pytest.mark.parametrize(
    "sentence",
    [
        "Meine Muttersprache ist Deutsch.",
        "I am a native German speaker.",
        "Ich entwickle cloud-native Anwendungen.",
        "Ich habe Apps mit React Native gebaut.",
    ],
)
def test_native_claim_backed_by_profile_or_tech_compound_passes(sentence: str) -> None:
    from core.cover_guard import _native_check

    assert _native_check(sentence, _REG_NATIVE, _REG_KNOWN)[0] is False


# --- Windows Smoke 4f26710 (run 39178281723, step 20): guard_native_spans ----
# "Meine Kenntnisse in Microsoft sowie meine Muttersprachliche * C2 und * *".
# The walk left of the marker crossed „sowie“ and claimed „Microsoft“ as a
# language. The masked words are not logged; the sentences below rebuild the
# logged structure with synthetic words (UNSICHER: not the verbatim letter).
# Profile as in the smoke: Deutsch C2 (level phrases allowed), no native entry.
_SMOKE_NATIVE = frozenset()
_SMOKE_KNOWN = frozenset({"deutsch", "englisch"})
_SMOKE_LEVEL = frozenset({"deutsch"})


@pytest.mark.parametrize(
    "sentence",
    [
        "Meine Kenntnisse in Microsoft 365 sowie meine muttersprachlichen Deutschkenntnisse (C2) runden mein Profil ab.",
        "Meine Kenntnisse in Microsoft 365 sowie meine Muttersprachliche Deutschkenntnisse C2 und gute Teamfähigkeit helfen mir.",
        "Meine Kenntnisse in Microsoft Azure sowie meine muttersprachlichen Deutschkenntnisse (C2) helfen mir.",
        "Meine Erfahrung mit Windows und Android sowie meine muttersprachlichen Deutschkenntnisse (C2) helfen mir.",
    ],
)
def test_smoke_tech_word_before_native_level_phrase_is_not_a_language(sentence: str) -> None:
    from core.cover_guard import _native_check

    # Teamlead 19.10.2026: „muttersprachliche …kenntnisse“ needs native Deutsch.
    assert _native_check(sentence, frozenset({"deutsch"}), _SMOKE_KNOWN, _SMOKE_LEVEL) == (False, "")
    assert _native_check(sentence, _SMOKE_NATIVE, _SMOKE_KNOWN, _SMOKE_LEVEL) == (True, "deutsch")


def test_smoke_profile_native_german_with_microsoft_enumeration_passes() -> None:
    from core.cover_guard import _native_check

    for sentence in (
        "Meine Muttersprache ist Deutsch und Microsoft 365 beherrsche ich sicher.",
        "Muttersprache Deutsch sowie Microsoft 365.",
    ):
        assert _native_check(sentence, frozenset({"deutsch"}), _SMOKE_KNOWN) == (False, ""), sentence


@pytest.mark.parametrize(
    "sentence",
    [
        "Meine Muttersprache ist Microsoft.",
        "I am a native Microsoft speaker.",
        "Meine Kenntnisse in Microsoft 365 sowie meine Muttersprache Klingonisch helfen mir.",
        "Meine Kenntnisse in Microsoft 365 sowie meine Muttersprache Französisch helfen mir.",
        "Ich nutze Microsoft 365, meine Muttersprache ist Deutsch und Kurmandschi.",
    ],
)
def test_tech_word_never_turns_an_explicit_native_claim_into_a_pass(sentence: str) -> None:
    from core.cover_guard import _native_check

    assert _native_check(sentence, frozenset({"deutsch"}), _SMOKE_KNOWN)[0] is True


# --- Kritiker/Personaler 19.10.2026: C2 is never native ---------------------
# Smoke profile (tests/fixtures/cv_corpus/DE_01_Klassisch.pdf, gold): Deutsch
# C2, Englisch C1, Französisch B1. With „Microsoft“ no longer claimed, the walk
# reaches the real language and checks it against the profile.
_DE01_KNOWN = frozenset({"deutsch", "englisch", "französisch"})
_DE01_C2_ONLY = (frozenset(), _DE01_KNOWN, frozenset({"deutsch"}))
_DE01_NATIVE = (frozenset({"deutsch"}), _DE01_KNOWN, frozenset({"deutsch"}))
_C2_NATIVE_CLAIMS = [
    "Meine Kenntnisse in Microsoft 365 sowie meine Muttersprache Deutsch (C2) und gute Englischkenntnisse helfen mir.",
    "Ich spreche Deutsch muttersprachlich.",
    "Deutsch ist meine Muttersprache.",
    "Ich bin deutsche Muttersprachlerin.",
    "I am a native German speaker.",
    "German is my native language.",
    "I speak German natively.",
]


@pytest.mark.parametrize("sentence", _C2_NATIVE_CLAIMS)
def test_native_claim_for_c2_only_language_blocks(sentence: str) -> None:
    from core.cover_guard import _native_check

    assert _native_check(sentence, *_DE01_C2_ONLY) == (True, "deutsch")


@pytest.mark.parametrize("sentence", _C2_NATIVE_CLAIMS)
def test_native_claim_for_native_profile_language_passes(sentence: str) -> None:
    from core.cover_guard import _native_check

    assert _native_check(sentence, *_DE01_NATIVE) == (False, "")
