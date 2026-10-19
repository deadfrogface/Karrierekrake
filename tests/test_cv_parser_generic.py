"""Focused generic CV parser behaviour — no corpus name hard-coding."""

from core.cv_parser import parse_cv_text
from core.cv_sections import is_document_title, is_heading, split_named_sections


def test_document_titles_are_not_names():
    for title in (
        "FIKTIVER TEST-LEBENSLAUF",
        "CURRICULUM VITAE",
        "Resume",
        "PROFILE",
        "Bewerbungsprofil",
    ):
        assert is_document_title(title)
        parsed = parse_cv_text(f"{title}\nAlex Example\nBerlin | alex@example.com\n")
        assert parsed["personal"].get("first_name") == "Alex"
        assert "FIKTIVER" not in (parsed["personal"].get("first_name") or "")
        assert "CURRICULUM" not in (parsed["personal"].get("first_name") or "").upper()


def test_cefr_not_licence_without_licence_context():
    text = """
Pat Example
Sprachen
Deutsch C2
Englisch C1
Französisch B1
Kenntnisse
Excel, Word
"""
    parsed = parse_cv_text(text)
    licences = [x["value"] for x in parsed["driving_license"]]
    assert "C1" not in licences
    assert "B1" not in licences
    assert "C2" not in licences


def test_licence_c1_allowed_in_licence_section():
    text = """
Pat Example
Sprachen
Deutsch C2 | Englisch C1
Fahrerlaubnis
Klassen B und C1
"""
    parsed = parse_cv_text(text)
    licences = [x["value"] for x in parsed["driving_license"]]
    assert "B" in licences
    assert "C1" in licences
    langs = {x["language"]: x["level"] for x in parsed["languages"]}
    assert langs.get("Englisch") == "C1"


def test_section_aliases_de_en():
    assert is_heading("WEITERE KENNTNISSE") == "software"
    assert is_heading("TECH STACK") == "software"
    assert is_heading("EMPLOYMENT HISTORY") == "experience"
    assert is_heading("CAREER HISTORY") == "experience"
    assert is_heading("ACADEMIC BACKGROUND") == "education"
    assert is_heading("ADDITIONAL SKILLS") == "skills"
    assert is_heading("Language Proficiency") == "languages"
    sections = split_named_sections(
        "EMPLOYMENT HISTORY\nRole\nACADEMIC BACKGROUND\nDegree\nTECH STACK\nExcel\n"
    )
    assert "experience" in sections and "education" in sections and "software" in sections


def test_missing_contact_fields_not_invented():
    text = """
Sam Example
Leipzig | sam@example.com
Ausbildung
2018 - 2021 B.A. Example, Hochschule Leipzig
"""
    parsed = parse_cv_text(text)
    personal = parsed["personal"]
    assert personal.get("city") == "Leipzig"
    assert not personal.get("street")
    assert not personal.get("postal_code")
    assert not personal.get("date_of_birth")
    assert not parsed.get("phones")


def test_muttersprache_with_cefr_keeps_native_and_cefr():
    # Teamlead 19.10.2026 (spec change): native wording is kept next to CEFR.
    parsed = parse_cv_text("Sprachen\nDeutsch - Muttersprache (C2)\nEnglisch - B2\n")
    langs = {x["language"]: x["level"] for x in parsed["languages"]}
    assert langs["Deutsch"] == "native (C2)"
    assert langs["Englisch"] == "B2"


def test_pipe_separated_single_language_line():
    parsed = parse_cv_text("Sprachen\nDeutsch | C2\nEnglisch | B1\n")
    assert len(parsed["languages"]) == 2
    assert parsed["languages"][0]["language"] == "Deutsch"
    assert parsed["languages"][0]["level"] == "C2"


def test_low_confidence_personal_when_title_mistaken():
    # If somehow only a title-like token remained, confidence must not be high garbage.
    parsed = parse_cv_text("Lebenslauf\n\nSprachen\nDeutsch C2\n")
    # No plausible person name → personal may be empty (preferred) or low confidence
    if parsed["personal"].get("first_name"):
        assert parsed["confidence"].get("personal") != "high" or is_document_title(
            parsed["personal"]["first_name"]
        ) is False
