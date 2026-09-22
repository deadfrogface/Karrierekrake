"""Post-routing cleanup: software/language must not remain in skills."""

from __future__ import annotations

from core.cv_parser import parse_cv_text


def test_wrapped_software_not_left_in_skills():
    text = """
Name Test
test@example.com
Kenntnisse
Englisch: C1
Software: DATEV, Adobe InDesign,
Figma
Fachkenntnisse: Disposition, Kundenberatung
"""
    r = parse_cv_text(text)
    soft = " ".join(r["software"]).lower()
    assert "figma" in soft
    assert "datev" in soft
    assert not any(s.lower() == "figma" for s in r["skills"])


def test_romanes_language_from_kenntnisse():
    text = """
Name Test
test@example.com
Kenntnisse
Romanes: Muttersprache
Englisch: B2
Software: Outlook
Fachkenntnisse: Qualitätssicherung
"""
    r = parse_cv_text(text)
    langs = {e["language"].lower(): e.get("level") for e in r["languages"]}
    assert "romanes" in langs
    assert not any("romanes" in s.lower() for s in r["skills"])


def test_sicherheitsunterweisung_not_skill_extra():
    text = """
Name Test
test@example.com
Kenntnisse
Deutsch: Muttersprache
Zertifikate: Erzieher - Sicherheitsunterweisung
Fachkenntnisse: Organisation
"""
    r = parse_cv_text(text)
    assert not any("sicherheitsunterweisung" == s.lower() for s in r["skills"])
    certs = " ".join(c["name"] for c in r["certificates"]).lower()
    assert "sicherheitsunterweisung" in certs or "erzieher" in certs
