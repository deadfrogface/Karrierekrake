"""Personaler-Gold: native-speaker status is its own target field (SMOKE_DE_EN_10).

C2 alone is never native. A language whose PDF line explicitly says
Muttersprache / native / mother tongue is listed in ``native_languages`` of
``tests/fixtures/cv_corpus/expected_results.json``; the Sollwerte sheet carries
the same fact in its ``SPRACHE_n`` lines. An extract that drops the native
status (e.g. ``C2`` or an empty level for such a language) is a mismatch, and
so is a native claim for a language the gold does not list as native.
No model is needed here: synthetic extracts and the deterministic text parser only.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "tests" / "fixtures" / "cv_corpus"
EXPECTED = CORPUS / "expected_results.json"
SOLL = CORPUS / "CV_Parser_Sollwerte_Vollstaendig.txt"
sys.path.insert(0, str(ROOT / "scripts"))

from run_cv_corpus import evaluate_doc
from run_cv_sollwerte_corpus import (
    PDFS,
    _sollwert_says_native,
    evaluate,
    parse_sollwerte,
)

# Personaler-Gold 19.10.2026, quoted from pdftotext of each PDF.
NATIVE_BY_PDF = {
    "DE_01_Klassisch.pdf": ["Deutsch"],  # "Deutsch - Muttersprache (C2)"
    "DE_02_Zweispaltig_Trap.pdf": [],
    "DE_03_C1_Kontextfalle.pdf": [],
    "DE_04_Unvollstaendige_Kontaktdaten.pdf": ["Deutsch"],  # "Deutsch: Muttersprache"
    "DE_05_Zweiseitig.pdf": [],
    "EN_01_Classic_Resume.pdf": ["English"],  # "English - Native"
    "EN_02_Two_Column_Trap.pdf": [],
    "EN_03_Missing_Address_Fields.pdf": ["Arabic"],  # "Arabic Native"
    "EN_04_German_Address_English_CV.pdf": [],
    "EN_05_Skills_Heavy.pdf": ["English"],  # "English - Native"
}
_NATIVE_WORDING = re.compile(r"muttersprach|mother\s+tongue|\bnative\b", re.IGNORECASE)


@pytest.fixture(scope="module")
def gold() -> dict:
    return json.loads(EXPECTED.read_text(encoding="utf-8"))["documents"]


@pytest.fixture(scope="module")
def soll() -> dict:
    return parse_sollwerte(SOLL)


def _langs(*pairs: tuple[str, str]) -> dict:
    return {"languages": [{"language": n, "level": lv} for n, lv in pairs]}


# --- gold field ---------------------------------------------------------------


def test_gold_lists_native_languages_for_all_smoke_cvs(gold: dict) -> None:
    assert sorted(NATIVE_BY_PDF) == sorted(PDFS)
    for pdf, natives in NATIVE_BY_PDF.items():
        assert gold[pdf].get("native_languages") == natives, pdf


def test_gold_native_languages_are_gold_languages_and_keep_levels(gold: dict) -> None:
    # Tightening only: the level values stay as before (DE_01 Deutsch stays "C2").
    assert ["Deutsch", "C2"] in gold["DE_01_Klassisch.pdf"]["languages"]
    for pdf, doc in gold.items():
        names = [pair[0] for pair in doc.get("languages") or []]
        for name in doc.get("native_languages") or []:
            assert name in names, (pdf, name)


@pytest.mark.parametrize("pdf", sorted(NATIVE_BY_PDF))
def test_gold_native_languages_match_pdf_wording(pdf: str, gold: dict) -> None:
    """Native only where the PDF says so; C2 alone is not native."""
    from core.cv_extract import extract_text

    segments = re.split(r"[\n;|,]", extract_text(CORPUS / pdf))
    for name, _level in gold[pdf]["languages"]:
        said_native = any(
            re.search(rf"\b{re.escape(name)}\b", seg) and _NATIVE_WORDING.search(seg)
            for seg in segments
        )
        assert said_native == (name in gold[pdf]["native_languages"]), (pdf, name)


def test_sollwerte_sheet_and_json_gold_agree_on_native(gold: dict, soll: dict) -> None:
    from run_cv_sollwerte_corpus import expected_native_languages

    for pdf in PDFS:
        assert expected_native_languages(soll[pdf]) == gold[pdf]["native_languages"], (
            pdf
        )


# --- expected_results.json comparator (scripts/run_cv_corpus.evaluate_doc) -----


def test_de01_extract_dropping_native_is_language_mismatch(gold: dict) -> None:
    exp = gold["DE_01_Klassisch.pdf"]
    ok, why = evaluate_doc(
        _langs(("Deutsch", "C2"), ("Englisch", "C1"), ("Französisch", "B1")), exp
    )["languages"]
    assert not ok and "Deutsch:native_dropped" in why, why


@pytest.mark.parametrize(
    "level", ["native (C2)", "Muttersprache (C2)", "C2 (Muttersprache)"]
)
def test_de01_extract_keeping_native_passes(level: str, gold: dict) -> None:
    exp = gold["DE_01_Klassisch.pdf"]
    ok, why = evaluate_doc(
        _langs(("Deutsch", level), ("Englisch", "C1"), ("Französisch", "B1")), exp
    )["languages"]
    assert ok, why


@pytest.mark.parametrize(
    "level", ["C2", "", "near-native", "muttersprachliches Niveau"]
)
def test_native_only_gold_rejects_non_native_level(level: str, gold: dict) -> None:
    exp = gold["EN_01_Classic_Resume.pdf"]
    ok, why = evaluate_doc(
        _langs(("English", level), ("German", "B2"), ("French", "A2")), exp
    )["languages"]
    assert not ok and "English:native_dropped" in why, why


def test_native_claim_for_non_native_gold_language_is_mismatch(gold: dict) -> None:
    exp = gold["DE_02_Zweispaltig_Trap.pdf"]
    # "Muttersprache (C2)" passes the level check (C2 is contained); only the native field catches it.
    got = _langs(
        ("Deutsch", "Muttersprache (C2)"),
        ("Englisch", "C1"),
        ("Niederländisch", "B1"),
        ("Polnisch", "A2"),
    )
    ok, why = evaluate_doc(got, exp)["languages"]
    assert not ok and "Deutsch:invented_native" in why, why


def test_gold_without_native_field_keeps_previous_tolerance() -> None:
    # Other corpora have no native_languages key: unchanged behaviour there.
    ok, why = evaluate_doc(
        _langs(("Deutsch", "C2")), {"languages": [["Deutsch", "native"]]}
    )["languages"]
    assert ok, why


# --- Sollwerte comparator (scripts/run_cv_sollwerte_corpus.evaluate) -----------


def _soll_lang_fails(parsed: dict, exp: dict) -> list[dict]:
    return [f for f in evaluate(parsed, exp) if str(f["field"]).startswith("SPRACHE")]


def test_sollwerte_de01_dropping_native_fails(soll: dict) -> None:
    fails = _soll_lang_fails(
        _langs(("Deutsch", "C2"), ("Englisch", "C1"), ("Französisch", "B1")),
        soll["DE_01_Klassisch.pdf"],
    )
    assert [(f["field"], f["kind"]) for f in fails] == [
        ("SPRACHE_1", "native_dropped")
    ], fails


def test_sollwerte_de01_keeping_native_passes(soll: dict) -> None:
    got = _langs(("Deutsch", "native (C2)"), ("Englisch", "C1"), ("Französisch", "B1"))
    assert _soll_lang_fails(got, soll["DE_01_Klassisch.pdf"]) == []


def test_sollwerte_native_only_gold_rejects_c2(soll: dict) -> None:
    fails = _soll_lang_fails(
        _langs(("Arabic", "C2"), ("German", "C1"), ("English", "C2")),
        soll["EN_03_Missing_Address_Fields.pdf"],
    )
    assert ("SPRACHE_3", "native_dropped") in [
        (f["field"], f["kind"]) for f in fails
    ], fails


def test_sollwerte_native_claim_for_c2_language_fails(soll: dict) -> None:
    got = _langs(("German", "native (C2)"), ("English", "C1"), ("Italian", "B2"))
    fails = _soll_lang_fails(got, soll["EN_04_German_Address_English_CV.pdf"])
    assert [(f["field"], f["kind"]) for f in fails] == [
        ("SPRACHE_1", "invented_native")
    ], fails


# --- _sollwert_says_native: negated wording is not native (review finding) ----

_NEGATED_NATIVE = [
    "non-native",
    "non native",
    "nicht Muttersprache",
    "keine Muttersprache",
    "not native",
]


@pytest.mark.parametrize("phrase", _NEGATED_NATIVE)
@pytest.mark.parametrize(
    "template",
    [
        "Deutsch | {p}",
        "Deutsch | C2 | {p}",
        "Deutsch | C2 | zusätzlich ausdrücklich: {p}",
    ],
)
def test_sollwert_negated_native_is_not_native(template: str, phrase: str) -> None:
    for p in (phrase, phrase.upper(), phrase.capitalize()):
        val = template.format(p=p)
        assert _sollwert_says_native(val) is False, val


@pytest.mark.parametrize(
    "val",
    [
        "Deutsch | Muttersprache",
        "Deutsch | muttersprache",
        "English | native",
        "English | Native",
        "Deutsch | C2 | zusätzlich ausdrücklich: Muttersprache",
        "Deutsch | native | Originalwert: Muttersprache",
        "English | native | Originalwert: Native",
        "Arabic | native | Originalwert: Native",
        "English | C2 | mother tongue",
    ],
)
def test_sollwert_native_phrasings_still_native(val: str) -> None:
    assert _sollwert_says_native(val) is True, val


@pytest.mark.parametrize(
    "val", ["Deutsch | C2", "English | C1 | fluent", "Deutsch | C2 |"]
)
def test_sollwert_plain_levels_are_not_native(val: str) -> None:
    assert _sollwert_says_native(val) is False, val


# --- deterministic import path vs gold (no model) -----------------------------


@pytest.mark.parametrize("pdf", PDFS)
def test_det_text_parser_meets_native_gold(pdf: str, gold: dict, soll: dict) -> None:
    from core.cv_extract import extract_text
    from core.cv_parser import parse_cv_text

    parsed = parse_cv_text(extract_text(CORPUS / pdf))
    ok, why = evaluate_doc(parsed, gold[pdf])["languages"]
    assert ok, why
    assert _soll_lang_fails(parsed, soll[pdf]) == []
