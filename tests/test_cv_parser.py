"""CV parser tests — fictional fixtures only; never invent qualifications."""

from pathlib import Path

from core.config import (
    LanguageEntry,
    ProfileConfig,
    QualificationsConfig,
    strip_example_placeholders,
)
from core.cv_parser import parse_cv_text, parsed_to_qualifications
from desktop.services.profile_merge import merge_qualifications

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_cv_extracts_only_present_data():
    text = """
Lena Winterfeld
lena.winterfeld@example.com
+49 151 0001111

Skills
Excel, Outlook, SAP

Languages
Deutsch C1
Englisch B1

Experience
Disponentin bei Firma Beispiel
"""
    parsed = parse_cv_text(text)
    assert "lena.winterfeld@example.com" in parsed["emails"]
    # Tools listed under a bare "Skills" heading are classified as software when
    # they match known product tokens (Excel/Outlook/SAP).
    tools = " ".join([*parsed["skills"], *parsed["software"]])
    assert "Excel" in tools
    assert not any("Master" in str(e) for e in parsed["education"])


def test_empty_cv():
    assert parse_cv_text("")["skills"] == []


def test_structured_german_cv_sections():
    text = (FIXTURES / "cv_structured_de.txt").read_text(encoding="utf-8")
    q = parsed_to_qualifications(parse_cv_text(text))
    langs = {(l.language, l.level) for l in q.languages}
    assert ("Deutsch", "C2") in langs
    assert ("Englisch", "B2") in langs
    assert ("Dänisch", "A2") in langs
    assert any("C1" in d for d in q.driving_values())
    assert any("Spedition und Logistikdienstleistung" in e.qualification for e in q.education)
    assert any("Mittlere Reife" in e.qualification for e in q.education)
    assert any("15.07.2021" == e.completion_date for e in q.education)
    assert any("Zollgrundlagen" == c.name for c in q.certificates)
    assert any("Staplerschein" == c.name for c in q.certificates)
    assert any("Power BI" == s for s in q.software_values())
    assert any("SAP" in s for s in q.software_values())
    assert len(q.work_experience) >= 2
    assert any("Tourenplanung" in " ".join(e.responsibilities) for e in q.work_experience)


def test_fixture_cv_files_are_parseable():
    """Repository-local fixtures only — no developer machine paths."""
    for name in ("cv_a.txt", "cv_b.txt", "cv_structured_de.txt"):
        path = FIXTURES / name
        assert path.is_file(), path
        q = parsed_to_qualifications(parse_cv_text(path.read_text(encoding="utf-8")))
        assert q.languages or q.work_experience or q.education


def test_example_placeholders_stripped():
    profile = ProfileConfig(
        qualifications=QualificationsConfig(
            skills=["MS Office", "Kommunikation"],
            software=["Excel", "Outlook"],
            languages=[
                LanguageEntry(language="Deutsch", level="C1"),
                LanguageEntry(language="Englisch", level="B1"),
            ],
        )
    )
    cleaned = strip_example_placeholders(profile)
    assert cleaned.qualifications.skills == []
    assert cleaned.qualifications.software == []
    assert cleaned.qualifications.languages == []


def test_reimport_no_duplicates():
    existing = QualificationsConfig(
        languages=[LanguageEntry(language="Deutsch", level="C1")],
        software=["Excel"],
        certificates=[],
    )
    incoming = QualificationsConfig(
        languages=[
            LanguageEntry(language="Deutsch", level="C2"),
            LanguageEntry(language="Englisch", level="C1"),
        ],
        software=["Excel", "Power BI"],
    )
    merged_add = merge_qualifications(existing, incoming, languages="add", software="add")
    assert len(merged_add.languages) == 2
    assert {l.language for l in merged_add.languages} == {"Deutsch", "Englisch"}
    assert merged_add.software_values() == ["Excel", "Power BI"]

    merged_update = merge_qualifications(
        existing, incoming, languages="update", software="update"
    )
    deutsch = next(l for l in merged_update.languages if l.language == "Deutsch")
    assert deutsch.level == "C2"
