"""Split-date employment, competencies heading, profile certificates."""

from __future__ import annotations

from core.cv_parser import parse_cv_text
from core.cv_sections import is_heading


def test_competencies_is_skills_heading():
    assert is_heading("Competencies") == "skills"


def test_split_date_lines_form_employment_record():
    text = (
        "Name\n"
        "Berufspraxis\n"
        "01/2018\n"
        "06/2020\n"
        "Rechtsanwaltsfachangestellte\n"
        "Atelier Morgenrot\n"
        "Hygienemanagement · Prozessoptimierung\n"
        "02/2019\n"
        "07/2021\n"
        "Werkstudent/in\n"
        "Grenzland Technik AG\n"
    )
    jobs = parse_cv_text(text)["work_experience"]
    assert len(jobs) >= 2
    assert jobs[0]["title"] == "Rechtsanwaltsfachangestellte"
    assert jobs[0]["company"] == "Atelier Morgenrot"
    assert jobs[0]["start_date"] == "01/2018"
    assert jobs[0]["end_date"] == "06/2020"
    assert jobs[1]["title"] == "Werkstudent/in"


def test_zertifikate_label_in_weitere_angaben():
    text = (
        "Name\n"
        "Bildungsweg\n"
        "2010 - 2013\n"
        "Abitur | Gymnasium X\n"
        "Weitere Angaben\n"
        "Zertifikate: Sicherheitsunterweisung 2022\n"
    )
    certs = parse_cv_text(text)["certificates"]
    names = " ".join(c.get("name") or "" for c in certs)
    assert "Sicherheitsunterweisung" in names


def test_certificates_label_english_in_profile():
    text = (
        "Name\n"
        "Education\n"
        "2010 - 2013\n"
        "B.Sc. | University\n"
        "Additional Information\n"
        "Certificates: Sicherheitsunterweisung 2023\n"
    )
    certs = parse_cv_text(text)["certificates"]
    names = " ".join(c.get("name") or "" for c in certs)
    assert "Sicherheitsunterweisung" in names


def test_competencies_heading_not_a_skill_value():
    text = (
        "Name\n"
        "Tools\n"
        "SolidWorks: Grundlagen\n"
        "Competencies\n"
        "Reklamationsbearbeitung\n"
        "Dokumentation\n"
    )
    p = parse_cv_text(text)
    skills = [s.lower() for s in (p.get("skills") or [])]
    soft = " ".join(str(s) for s in (p.get("software") or [])).lower()
    assert "competencies" not in skills
    assert "reklamationsbearbeitung" in skills
    assert "solidworks" in soft
