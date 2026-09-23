"""Title-before-date experience and Kaufmann education must parse."""

from __future__ import annotations

from core.cv_parser import parse_cv_text


def test_title_before_date_experience():
    result = parse_cv_text(
        """
Berufserfahrung
Disponentin
Nordhafen Logistik GmbH, Hamburg
Seit 01.03.2023
• Tourenplanung und Disposition
Sachbearbeiterin Versand
Seeland Versand KG, Lübeck
01.08.2020 – 28.02.2023
• Auftragsabwicklung
"""
    )
    titles = [e["title"] for e in result["work_experience"]]
    assert "Disponentin" in titles
    assert "Sachbearbeiterin Versand" in titles
    assert all(not t.startswith("•") for t in titles)
    first = next(e for e in result["work_experience"] if e["title"] == "Disponentin")
    assert "Sachbearbeiterin" not in " ".join(first["responsibilities"])


def test_kaufmann_education_without_prefix():
    result = parse_cv_text(
        """
Ausbildung
Kaufmann für Büromanagement
Abschluss: 15.07.2019
Berufsschule Musterstadt
Mittlere Reife
Abschluss: 20.06.2016
"""
    )
    quals = [e["qualification"] for e in result["education"]]
    assert any("Kaufmann" in q for q in quals)
    assert any("Mittlere Reife" in q for q in quals)


def test_kenntnisse_cefr_becomes_languages_not_skills():
    result = parse_cv_text(
        """
Max Mustermann
Musterstraße 1
12345 Berlin
max@example.com

Kenntnisse
Deutsch – C2
Englisch – C1
Microsoft 365, SAP
"""
    )
    langs = {e["language"]: e["level"] for e in result["languages"]}
    assert langs.get("Deutsch") == "C2"
    assert langs.get("Englisch") == "C1"
    assert "Deutsch – C2" not in result["skills"]
    # Tool tokens under Kenntnisse belong in software (or skills historically).
    tools = " ".join([*result["skills"], *result["software"]])
    assert "Microsoft 365" in tools or "SAP" in tools
    assert "Microsoft" not in langs
