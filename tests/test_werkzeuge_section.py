"""Werkzeuge section maps like Kenntnisse (languages/software/skills)."""

from __future__ import annotations

from core.cv_parser import parse_cv_text
from core.cv_sections import is_heading, split_named_sections


def test_werkzeuge_is_skills_heading():
    assert is_heading("Werkzeuge") == "skills"


def test_werkzeuge_after_qualifikationen_not_swallowed():
    text = """
Elias Beispiel
elias@example.com
Stationen
01/2018 - heute | Zahntechnikerin | Nordwerk GmbH
Teamkoordination; Fehleranalyse
Qualifikationen
1985 - 1988 | Abitur | Gymnasium Konstanz
Werkzeuge
Polnisch: C1
Englisch: A2
Software: Confluence, Figma, Python
Fachkenntnisse: Arbeitssicherheit, Präsentation, Projektplanung
Zertifikate: Zahntechnikerin - Sicherheitsunterweisung
"""
    sections = split_named_sections(text)
    assert "skills" in sections
    assert "Confluence" in sections["skills"]
    assert "Werkzeuge" not in (sections.get("education") or "")
    assert "Confluence" not in (sections.get("education") or "")

    r = parse_cv_text(text)
    langs = {e["language"] for e in r["languages"]}
    assert "Polnisch" in langs and "Englisch" in langs
    soft = " ".join(r["software"]).lower()
    assert "confluence" in soft and "figma" in soft and "python" in soft
    skills_l = " ".join(r["skills"]).lower()
    assert "präsentation" in skills_l or "projektplanung" in skills_l
    assert r["education"], "Abitur must remain education"
