"""Regression: DE_01 visibly lost four CV sections in the fake-mail EXE."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.cv_docpick_import import (
    CvImportError,
    _complete_explicit_lists,
    _missing_explicit_lists,
    extract_cv_text,
    suggestion_to_parsed,
)
from core.cv_parser import parsed_to_qualifications
from core.config import QualificationsConfig
from desktop.services.profile_merge import filter_parsed_for_import, replace_qualifications


PDF = Path(__file__).parent / "fixtures" / "cv_corpus" / "DE_01_Klassisch.pdf"
EN_PDF = Path(__file__).parent / "fixtures" / "cv_corpus" / "EN_01_Classic_Resume.pdf"


def test_targeted_model_completion_preserves_cv_qualifications(monkeypatch):
    source = extract_cv_text(PDF)
    bare = {"name": {"first_name": "Mara", "last_name": "König"},
            "languages": [], "skills": [], "software": [], "certificates": []}
    assert set(_missing_explicit_lists(bare, source)) == {
        "languages", "skills", "software", "certificates"
    }

    def model_retry(text, *, transport, messages):
        assert transport == "inprocess"
        assert "languages" in messages[1]["content"]
        return {
            "languages": [
                {"language": "Deutsch", "level": "C2"},
                {"language": "Englisch", "level": "C1"},
                {"language": "Französisch", "level": "B1"},
            ],
            "skills": ["Kundenservice", "Auftragsmanagement", "KPI-Reporting",
                       "Prozessoptimierung", "Reklamationsmanagement", "erfundene Fähigkeit"],
            "software": ["Microsoft 365", "SAP Business One", "Salesforce",
                         "Jira", "Confluence", "DocuWare", "erfundenes Tool"],
            "certificates": ["IHK Beschwerdemanagement", "Power BI Grundlagen", "Ersthelferin"],
        }

    monkeypatch.setattr("core.cv_docpick_import._llm_extract", model_retry)
    completed = _complete_explicit_lists(bare, source, transport="inprocess")
    assert len(completed["languages"]) == 3
    assert len(completed["skills"]) == 5
    assert len(completed["software"]) == 6
    assert len(completed["certificates"]) == 3

    parsed = suggestion_to_parsed(completed, source_text=source)
    parsed["source_text"] = source
    incoming = parsed_to_qualifications(filter_parsed_for_import(parsed))
    result = replace_qualifications(QualificationsConfig(), incoming)
    assert len(result.languages) == 3
    assert len(result.skill_values()) == 5
    assert len(result.software_values()) == 6
    assert len(result.certificates) == 3


def test_missing_explicit_sections_fail_visible_instead_of_silent_replace(monkeypatch):
    source = extract_cv_text(PDF)
    monkeypatch.setattr("core.cv_docpick_import._llm_extract", lambda *a, **k: {})
    with pytest.raises(CvImportError, match="incomplete_extract"):
        _complete_explicit_lists({"skills": [], "languages": []}, source, transport="inprocess")


def test_no_second_call_when_model_already_filled_sections(monkeypatch):
    source = extract_cv_text(PDF)
    filled = {key: ["present"] for key in ("skills", "languages", "software", "certificates")}
    monkeypatch.setattr("core.cv_docpick_import._llm_extract", lambda *a, **k: pytest.fail("retry"))
    assert _complete_explicit_lists(filled, source, transport="inprocess") == filled


def test_english_headings_and_empty_sections():
    source = extract_cv_text(EN_PDF)
    assert set(_missing_explicit_lists({}, source)) == {
        "languages", "skills", "software", "certificates"
    }
    assert _missing_explicit_lists({}, "Languages\n\nSkills\n\nSoftware\n") == []
