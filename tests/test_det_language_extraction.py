"""General DET language / licence extraction tests (no FH_ IDs)."""

from __future__ import annotations

from core.cv_parser import parse_cv_text
from core.cv_sections import is_heading, split_named_sections


def _lang_pairs(parsed: dict) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for item in parsed.get("languages") or []:
        if isinstance(item, dict):
            out.append((item.get("language") or "", item.get("level") or ""))
        else:
            out.append((getattr(item, "language", ""), getattr(item, "level", "")))
    return out


def _lic_codes(parsed: dict) -> list[str]:
    codes: list[str] = []
    for item in parsed.get("driving_license") or []:
        if isinstance(item, dict):
            codes.append(str(item.get("value") or ""))
        else:
            codes.append(str(item))
    return codes


def test_01_heading_sprachen():
    assert is_heading("Sprachen") == "languages"


def test_02_heading_sprachkenntnisse():
    assert is_heading("Sprachkenntnisse") == "languages"


def test_03_heading_languages():
    assert is_heading("Languages") == "languages"


def test_04_heading_languages_and_licences():
    assert is_heading("Languages & licences") == "languages"


def test_05_heading_sprachen_fahrerlaubnis():
    assert is_heading("Sprachen & Fahrerlaubnis") == "languages"


def test_06_deutsch_muttersprache_pair():
    parsed = parse_cv_text("Sprachen\nDeutsch – Muttersprache\n")
    pairs = _lang_pairs(parsed)
    assert any(n == "Deutsch" and "native" in (lv or "").lower() for n, lv in pairs)


def test_07_english_c1_pair():
    parsed = parse_cv_text("Languages\nEnglish – C1\n")
    pairs = _lang_pairs(parsed)
    assert ("English", "C1") in pairs


def test_08_german_native_emdash():
    parsed = parse_cv_text("Languages\nGerman — native\n")
    pairs = _lang_pairs(parsed)
    assert any(n == "German" and "native" in (lv or "").lower() for n, lv in pairs)


def test_09_language_without_level():
    parsed = parse_cv_text("Sprachen\nFranzösisch\n")
    pairs = _lang_pairs(parsed)
    assert any(n == "Französisch" and (lv or "") == "" for n, lv in pairs)


def test_10_multiple_languages():
    parsed = parse_cv_text(
        "Sprachen\nDeutsch – Muttersprache\nEnglisch – C1\nSpanisch – B1\n"
    )
    names = {n for n, _ in _lang_pairs(parsed)}
    assert {"Deutsch", "Englisch", "Spanisch"} <= names


def test_11_licence_b_same_section():
    parsed = parse_cv_text(
        "Sprachen & Fahrerlaubnis\nDeutsch – Muttersprache\nFührerschein: B\n"
    )
    assert "B" in _lic_codes(parsed)
    assert any(n == "Deutsch" for n, _ in _lang_pairs(parsed))
    assert not any("Führerschein" in (c.get("name") or "") for c in parsed.get("certificates") or [])


def test_12_licence_c1_same_section():
    parsed = parse_cv_text(
        "Sprachen & Fahrerlaubnis\nDeutsch – C2\nFührerschein: C1\n"
    )
    assert "C1" in _lic_codes(parsed)
    assert ("Deutsch", "C2") in _lang_pairs(parsed)


def test_13_language_c1_and_licence_c1_together():
    parsed = parse_cv_text(
        "Sprachen & Fahrerlaubnis\n"
        "Deutsch – C2\n"
        "Polnisch – C1\n"
        "Führerschein: B, C1\n"
    )
    pairs = dict(_lang_pairs(parsed))
    assert pairs.get("Deutsch") == "C2"
    assert pairs.get("Polnisch") == "C1"
    codes = set(_lic_codes(parsed))
    assert {"B", "C1"} <= codes


def test_14_python_under_software_not_language():
    parsed = parse_cv_text("Software\nPython – Grundlagen\n")
    assert not any(n.lower() == "python" for n, _ in _lang_pairs(parsed))
    soft = " ".join(
        (s if isinstance(s, str) else str(s.get("value") or s))
        for s in (parsed.get("software") or [])
    ).lower()
    assert "python" in soft


def test_15_r_under_tools_not_language():
    parsed = parse_cv_text("Tools\nR – Grundlagen\nExcel – gut\n")
    assert not any(n.lower() == "r" for n, _ in _lang_pairs(parsed))


def test_16_heading_not_stored_as_language():
    parsed = parse_cv_text("Sprachen\nDeutsch – C2\n")
    names = {n.lower() for n, _ in _lang_pairs(parsed)}
    assert "sprachen" not in names
    assert "languages" not in names


def test_17_weitere_kenntnisse_mixed_categories():
    text = (
        "Weitere Kenntnisse\n"
        "Software: Excel, SAP\n"
        "Deutsch: Muttersprache\n"
        "Führerschein: B\n"
    )
    parsed = parse_cv_text(text)
    # Heading maps to software; labelled routing may recover languages/licences.
    soft = " ".join(str(s) for s in (parsed.get("software") or [])).lower()
    assert "excel" in soft or "sap" in soft


def test_18_two_columnish_language_block():
    # Pipe-separated pairs on one visual row (reading-order flatten).
    parsed = parse_cv_text(
        "Sprachen\nDeutsch – Muttersprache | Englisch – B2\n"
    )
    names = {n for n, _ in _lang_pairs(parsed)}
    assert "Deutsch" in names
    assert "Englisch" in names


def test_19_english_cv_languages_licences():
    parsed = parse_cv_text(
        "Languages & licences\n"
        "German — native\n"
        "English – C1\n"
        "Driving licence: B\n"
    )
    pairs = dict(_lang_pairs(parsed))
    assert "German" in pairs and "English" in pairs
    assert pairs.get("English") == "C1"
    assert "B" in _lic_codes(parsed)


def test_20_missing_language_section():
    parsed = parse_cv_text(
        "Berufserfahrung\nSachbearbeiter | Beispiel GmbH\nSoftware\nExcel\n"
    )
    assert _lang_pairs(parsed) == []


def test_21_empty_language_section():
    parsed = parse_cv_text("Sprachen\n\nSoftware\nExcel\n")
    assert _lang_pairs(parsed) == []


def test_22_duplicate_language_lines_deduped():
    parsed = parse_cv_text(
        "Sprachen\nDeutsch – C2\nDeutsch – C2\nEnglisch – B1\n"
    )
    deutsch = [p for p in _lang_pairs(parsed) if p[0] == "Deutsch"]
    assert len(deutsch) == 1


def test_23_swapped_levels_not_invented_from_order():
    # Each line keeps its own level — no cross-line guessing.
    parsed = parse_cv_text("Sprachen\nDeutsch – A1\nEnglisch – C2\n")
    pairs = dict(_lang_pairs(parsed))
    assert pairs.get("Deutsch") == "A1"
    assert pairs.get("Englisch") == "C2"


def test_24_evidence_pair_stays_connected():
    parsed = parse_cv_text("Sprachen\nFranzösisch: B2\nNiederländisch | gute Kenntnisse\n")
    pairs = dict(_lang_pairs(parsed))
    assert pairs.get("Französisch") == "B2"
    assert "gute" in (pairs.get("Niederländisch") or "").lower()


def test_25_unknown_real_language_under_explicit_heading():
    # Known minority language already in model — still under explicit heading.
    parsed = parse_cv_text("Sprachkenntnisse\nKurdisch – Muttersprache\n")
    assert any(n == "Kurdisch" for n, _ in _lang_pairs(parsed))


def test_kenntnisse_sprachen_heading_routes_to_languages():
    assert is_heading("Kenntnisse – Sprachen") == "languages"
    secs = split_named_sections("Kenntnisse – Sprachen\nItalienisch – B1\n")
    assert "Italienisch" in secs.get("languages", "")


def test_kenntnisse_alone_not_entirely_languages():
    # Bare Kenntnisse stays skills — must not swallow arbitrary skill lines as languages.
    assert is_heading("Kenntnisse") == "skills"
    parsed = parse_cv_text("Kenntnisse\nTeamfähigkeit\nOrganisation\n")
    assert not any(n.lower() == "teamfähigkeit" for n, _ in _lang_pairs(parsed))


def test_orphan_cefr_not_a_language():
    parsed = parse_cv_text("Sprachen\nC1\nSoftware\nExcel\n")
    assert not any(n.upper() == "C1" for n, _ in _lang_pairs(parsed))


# --- Teamlead 19.10.2026: „Muttersprache“ is its own level class -----------
# „Deutsch - Muttersprache (C2)“ (tests/fixtures/cv_corpus/DE_01_Klassisch.pdf)
# must not collapse to „C2“: C2 is never native for the cover guard.


def test_muttersprache_with_cefr_keeps_native_class_de():
    from core.cover_guard import _entry_level_class

    parsed = parse_cv_text("Sprachen\nDeutsch - Muttersprache (C2)\nEnglisch - C1\nFranzösisch - B1\n")
    pairs = dict(_lang_pairs(parsed))
    assert pairs["Deutsch"] == "native (C2)"
    assert pairs["Englisch"] == "C1"
    assert pairs["Französisch"] == "B1"
    assert _entry_level_class(pairs["Deutsch"], "") == "native"


def test_native_with_cefr_keeps_native_class_en():
    from core.cover_guard import _entry_level_class

    parsed = parse_cv_text("Languages\nGerman - native (C2)\nEnglish - C1\n")
    pairs = dict(_lang_pairs(parsed))
    assert pairs["German"] == "native (C2)"
    assert pairs["English"] == "C1"
    assert _entry_level_class(pairs["German"], "") == "native"


def test_plain_cefr_without_native_wording_stays_c2():
    parsed = parse_cv_text("Sprachen\nDeutsch - C2\nEnglisch - C1\n")
    assert dict(_lang_pairs(parsed))["Deutsch"] == "C2"


def test_matcher_ranks_native_with_cefr_at_least_c2():
    from core.config import LanguageEntry
    from core.matcher import _profile_lang_level

    for level in ("native (C2)", "Muttersprache (C2)", "native", "C2"):
        assert _profile_lang_level([LanguageEntry(language="Deutsch", level=level)], "deutsch") == 6, level


def test_gold_compare_accepts_native_with_cefr_for_c2_gold():
    """DE_01 gold keeps ["Deutsch", "C2"] and lists Deutsch in native_languages (Personaler 19.10.2026)."""
    import json
    from pathlib import Path

    from scripts.run_cv_corpus import evaluate_doc

    parsed = {"languages": [{"language": "Deutsch", "level": "native (C2)"}]}
    section = evaluate_doc(parsed, {"languages": [["Deutsch", "C2"]]})
    assert section["languages"][0], section["languages"]

    # Wired to the binding gold: the import result for DE_01 must keep native.
    gold_path = Path(__file__).parent / "fixtures" / "cv_corpus" / "expected_results.json"
    de01 = json.loads(gold_path.read_text(encoding="utf-8"))["documents"]["DE_01_Klassisch.pdf"]
    assert de01["native_languages"] == ["Deutsch"]
    parsed = parse_cv_text("Sprachen\nDeutsch - Muttersprache (C2)\nEnglisch - C1\nFranzösisch - B1\n")
    assert evaluate_doc(parsed, de01)["languages"][0], evaluate_doc(parsed, de01)["languages"]
    dropped = {"languages": [dict(x, level="C2") if x["language"] == "Deutsch" else x for x in parsed["languages"]]}
    ok, why = evaluate_doc(dropped, de01)["languages"]
    assert not ok and "Deutsch:native_dropped" in why, why


def test_de01_fixture_import_deutsch_is_native():
    """Kritiker 19.10.2026: the smoke CV itself (DE_01_Klassisch.pdf,
    „Deutsch - Muttersprache (C2)“) imports Deutsch as native. Hard assertion,
    independent of any gold field."""
    from pathlib import Path

    from core.cover_guard import _entry_level_class
    from core.cv_extract import extract_text
    from core.cv_parser import parsed_to_qualifications

    pdf = Path(__file__).parent / "fixtures" / "cv_corpus" / "DE_01_Klassisch.pdf"
    quals = parsed_to_qualifications(parse_cv_text(extract_text(pdf)))
    levels = {entry.language: entry.level for entry in quals.languages}
    assert levels["Deutsch"] == "native (C2)"
    assert _entry_level_class(levels["Deutsch"], "") == "native"
    assert _entry_level_class(levels["Englisch"], "") == "other"
    assert _entry_level_class(levels["Französisch"], "") == "other"


def test_en01_fixture_import_english_is_native():
    from pathlib import Path

    from core.cover_guard import _entry_level_class
    from core.cv_extract import extract_text
    from core.cv_parser import parsed_to_qualifications

    pdf = Path(__file__).parent / "fixtures" / "cv_corpus" / "EN_01_Classic_Resume.pdf"
    quals = parsed_to_qualifications(parse_cv_text(extract_text(pdf)))
    levels = {entry.language: entry.level for entry in quals.languages}
    assert _entry_level_class(levels["English"], "") == "native"
    assert _entry_level_class(levels["German"], "") == "other"
