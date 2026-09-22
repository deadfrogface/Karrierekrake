"""Section boundary + Kenntnisse routing: Praxis/Bildungsweg must not pollute skills."""

from __future__ import annotations

from core.cv_parser import parse_cv_text
from core.cv_sections import is_heading, split_named_sections


def test_praxis_and_bildungsweg_are_section_headings():
    assert is_heading("Praxis") == "experience"
    assert is_heading("Stationen") == "experience"
    assert is_heading("Werdegang") == "experience"
    assert is_heading("Bildungsweg") == "education"
    assert is_heading("Schule & Ausbildung") == "education"


def test_kenntnisse_does_not_swallow_praxis_employment():
    text = """
Valerie Beispiel
Kenntnisse
Russisch: C1
Englisch: C1
Software: Outlook, SAP S/4HANA,
DaVinci Resolve
Fachkenntnisse: Hygiene, Kundenberatung
Praxis
01/2018 - heute | Seiler | Nordwerk AG
Disposition; Datenschutz
02/2019 - 07/2020 | Praktikant/in | Rhein & Sohn AG
Bildungsweg
2011 - 2014 | Hauptschulabschluss | Mittelschule Flensburg
2015 - 2018 | Ausbildung Seiler | Berufskolleg Hamburg
"""
    sections = split_named_sections(text)
    assert "experience" in sections
    assert "Nordwerk AG" in sections["experience"]
    assert "education" in sections
    assert "Hauptschulabschluss" in sections["education"]
    assert "Nordwerk AG" not in sections.get("skills", "")

    r = parse_cv_text(text)
    skills_l = " ".join(r["skills"]).lower()
    assert "nordwerk" not in skills_l
    assert "01" not in r["skills"]
    assert "2018 - heute" not in r["skills"]
    soft = " ".join(r["software"]).lower()
    assert "outlook" in soft
    assert "s/4hana" in soft or "sap s/4hana" in soft
    assert "davinci" in soft
    assert r["work_experience"], "Praxis block must yield employment"
    assert any("Nordwerk" in (e.get("company") or "") for e in r["work_experience"])
    assert r["education"], "Bildungsweg must yield education"


def test_software_label_does_not_split_product_slash():
    text = """
Name Test
email@example.com
Kenntnisse
Software: SAP S/4HANA, Excel
"""
    r = parse_cv_text(text)
    soft = " ".join(r["software"]).lower()
    assert "s/4hana" in soft or "sap s/4hana" in soft
    assert "4hana" not in [s.lower() for s in r["software"]]
    assert not any(s.lower() == "sap s" for s in r["software"])
