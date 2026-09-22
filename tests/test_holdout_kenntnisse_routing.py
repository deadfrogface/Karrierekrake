"""Regression: compact Kenntnisse labeled lines route to correct categories."""

from __future__ import annotations

from core.cv_parser import parse_cv_text


def test_kenntnisse_labeled_software_skills_licence_not_mixed():
    text = """
Max Beispiel
Musterstraße 2, 10115 Berlin, DE | max@example.com | +49 170 1111111
Berufserfahrung
01/2020 - heute | Sachbearbeiter | Demo GmbH
Ausbildung
2015 - 2018 | Kaufmann für Büromanagement | Berufsschule Berlin
Kenntnisse
Deutsch: Muttersprache
Englisch: B1
Führerschein: B
Software: DATEV, Excel
Fachkenntnisse: Organisation, Kommunikation
Zertifikate: Erste Hilfe
Berufswunsch: Sachbearbeiter
"""
    r = parse_cv_text(text)
    langs = {e["language"] for e in r["languages"]}
    assert "Deutsch" in langs and "Englisch" in langs
    soft = " ".join(r["software"]).lower()
    assert "datev" in soft and "excel" in soft
    skills = " ".join(r["skills"]).lower()
    assert "organisation" in skills or "kommunikation" in skills
    assert not any(s.lower().startswith("software:") for s in r["skills"])
    certs = " ".join(c["name"] for c in r["certificates"]).lower()
    assert "erste hilfe" in certs
    lic = r["driving_license"]
    assert any((x.get("value") if isinstance(x, dict) else x) == "B" for x in lic)
    assert r.get("target_role") == "Sachbearbeiter"
    assert r["work_experience"], "real job must remain"
    assert r["personal"].get("country") == "DE"


def test_education_ohne_abschluss_not_certificate():
    text = """
Name Test
Ausbildung
2013 - ohne Abschluss | Hauptschule ohne Abschluss | Schule X
2016 - 2019 | Ausbildung | Schule Y
"""
    r = parse_cv_text(text)
    quals = [e["qualification"] for e in r["education"]]
    assert any("Hauptschule" in q for q in quals)
    assert any("Ausbildung" in q for q in quals)
    assert not any("Hauptschule" in (c["name"] or "") for c in r["certificates"])
