"""General career-break vs education classification tests (no FH_ IDs)."""

from __future__ import annotations

from core.cv_parser import parse_cv_text
from core.cv_sections import is_heading


def _edu_quals(parsed: dict) -> list[str]:
    return [str(e.get("qualification") or "") for e in (parsed.get("education") or [])]


def test_elternzeit_not_education():
    text = (
        "Bildungsweg\n"
        "2008 - 2011\n"
        "Hauptschulabschluss | Gesamtschule Beispiel\n"
        "Weitere Angaben\n"
        "03/2021 - 11/2022 Elternzeit\n"
    )
    parsed = parse_cv_text(text)
    quals = " ".join(_edu_quals(parsed)).lower()
    assert "elternzeit" not in quals
    assert any("Hauptschulabschluss" in q for q in _edu_quals(parsed))
    notes = " ".join(parsed.get("career_notes") or []).lower()
    assert "elternzeit" in notes


def test_arbeitslosigkeit_not_education():
    parsed = parse_cv_text(
        "Ausbildung\n2010 - 2013\nKaufmann | IHK\n01/2020 - 06/2020 Arbeitslosigkeit\n"
    )
    assert not any("arbeitslosigkeit" in q.lower() for q in _edu_quals(parsed))


def test_sabbatical_not_education():
    parsed = parse_cv_text(
        "Education\n2015 - 2018\nB.Sc. Biology | Example University\n2021 - 2022 Sabbatical\n"
    )
    assert not any("sabbatical" in q.lower() for q in _edu_quals(parsed))


def test_arbeitssuchend_not_education():
    parsed = parse_cv_text(
        "Bildungsweg\n2012 - 2015\nRealschulabschluss | Schule X\n2023 arbeitssuchend\n"
    )
    assert not any("arbeitssuchend" in q.lower() for q in _edu_quals(parsed))


def test_pflegezeit_not_education():
    parsed = parse_cv_text(
        "Bildungsweg\n2009 - 2012\nAbitur | Gymnasium Y\n03/2019 - 09/2019 Pflegezeit\n"
    )
    assert not any("pflegezeit" in q.lower() for q in _edu_quals(parsed))


def test_berufspraxis_is_experience_heading():
    assert is_heading("Berufspraxis") == "experience"
    parsed = parse_cv_text(
        "Berufspraxis\n"
        "01/2018 - 06/2020\n"
        "Laborassistentin | Beispiel GmbH\n"
        "Bildungsweg\n"
        "2008 - 2011\n"
        "Hauptschulabschluss | Schule Z\n"
    )
    assert parsed.get("work_experience")
    assert any(
        "Laborassistentin" in str(e.get("title") or "")
        or "Beispiel" in str(e.get("company") or "")
        for e in parsed["work_experience"]
    )


def test_weitere_angaben_not_education_institution():
    assert is_heading("Weitere Angaben") == "profile"
    parsed = parse_cv_text(
        "Bildungsweg\n"
        "2008 - 2011\n"
        "Hauptschulabschluss | Gesamtschule Basel\n"
        "Weitere Angaben\n"
        "03/2021 - 11/2022 Elternzeit\n"
    )
    for e in parsed.get("education") or []:
        assert "Weitere Angaben" not in str(e.get("institution") or "")
        assert "Elternzeit" not in str(e.get("qualification") or "")
