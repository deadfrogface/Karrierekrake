"""Licence blob / composite heading / software-skill-cert routing guards."""

from __future__ import annotations

from core.cv_parser import parse_cv_text, _parse_driving, normalize_driving_license
from core.cv_sections import is_heading, split_named_sections


def _lic_vals(parsed) -> list[str]:
    out = []
    for it in parsed.get("driving_license") or []:
        if isinstance(it, dict):
            out.append(str(it.get("value") or ""))
        else:
            out.append(str(getattr(it, "value", it)))
    return [x for x in out if x]


def _lang_pairs(parsed) -> list[tuple[str, str]]:
    out = []
    for it in parsed.get("languages") or []:
        if isinstance(it, dict):
            out.append((str(it.get("language") or "").lower(), str(it.get("level") or "").lower()))
        else:
            out.append((str(it.language).lower(), str(it.level or "").lower()))
    return out


def _cert_names(parsed) -> list[str]:
    out = []
    for it in parsed.get("certificates") or []:
        if isinstance(it, dict):
            out.append(str(it.get("name") or "").lower())
        else:
            out.append(str(it.name).lower())
    return out


def test_composite_heading_wrap_sprachen_fuehrerschein():
    text = (
        "Max Mustermann\n"
        "Sprachkenntnisse &\n"
        "Führerschein\n"
        "Deutsch: Muttersprache\n"
        "Englisch: B2\n"
        "Führerschein: B\n"
        "Berufserfahrung\n"
        "2020 - 2022 Entwickler | Firma AG\n"
    )
    secs = split_named_sections(text)
    assert "languages" in secs
    assert "französisch" not in (secs.get("license") or "").lower()
    parsed = parse_cv_text(text)
    langs = _lang_pairs(parsed)
    assert any(a == "deutsch" for a, _ in langs)
    assert any(a == "englisch" and "b2" in b for a, b in langs)
    assert "B" in _lic_vals(parsed)


def test_parse_driving_never_returns_language_blob():
    blob = (
        "Französisch: B2\n"
        "Englisch: B1\n"
        "Programme und Werkzeuge\n"
        "SAP MM - Grundlagen\n"
        "Fachkompetenzen\n"
        "Arbeitsvorbereitung\n"
    )
    assert _parse_driving(blob) == []
    assert normalize_driving_license(["Englisch: B2"]) == []


def test_fuehrerschein_b_be_and_c1_licence_vs_language_c1():
    text = (
        "Ada Beispiel\n"
        "Sprachen & Führerschein\n"
        "Englisch: C1\n"
        "Führerschein: B, BE\n"
        "Fahrerlaubnis: C1\n"
    )
    parsed = parse_cv_text(text)
    langs = _lang_pairs(parsed)
    assert any(a == "englisch" and "c1" in b for a, b in langs)
    lic = set(_lic_vals(parsed))
    assert {"B", "BE", "C1"} <= lic


def test_driving_licence_english_label():
    text = "Sam Sample\nLanguages and Driving licence\nGerman: Native\nEnglish: B2\nDriving licence: B\n"
    parsed = parse_cv_text(text)
    assert "B" in _lic_vals(parsed)


def test_licence_section_bare_c1_with_section_context():
    text = "Sam Sample\nFührerschein\n• C1\nBerufserfahrung\n2020 Koch | Kantine AG\n"
    parsed = parse_cv_text(text)
    assert "C1" in _lic_vals(parsed)


def test_no_licence_section_yields_empty():
    text = (
        "Sam Sample\n"
        "Sprachkenntnisse\n"
        "Deutsch: Muttersprache\n"
        "Englisch: B2\n"
        "Berufserfahrung\n"
        "2020 Koch | Kantine AG\n"
    )
    parsed = parse_cv_text(text)
    assert not _lic_vals(parsed)


def test_bare_c1_without_licence_context_not_licence():
    text = "Sam Sample\nSprachen\nEnglisch: C1\nBerufserfahrung\n2020 Koch | Kantine AG\n"
    parsed = parse_cv_text(text)
    assert not _lic_vals(parsed)
    assert any(a == "englisch" for a, _ in _lang_pairs(parsed))


def test_heading_fuehrerschein_without_value():
    text = "Sam Sample\nFührerschein\nBerufserfahrung\n2020 Koch | Kantine AG\n"
    parsed = parse_cv_text(text)
    assert not _lic_vals(parsed)


def test_programme_und_werkzeuge_software_with_levels():
    text = (
        "Sam Sample\n"
        "Programme und Werkzeuge\n"
        "LibreOffice Calc - Grundlagen\n"
        "SAP MM - gute Kenntnisse\n"
        "EPLAN Electric P8 - sehr gut\n"
        "RStudio\n"
        "Berufserfahrung\n"
        "2020 Koch | Kantine AG\n"
    )
    assert is_heading("Programme und Werkzeuge") == "software"
    parsed = parse_cv_text(text)
    sw = [s.lower() for s in parsed["software"]]
    assert "libreoffice calc" in sw
    assert "sap mm" in sw
    assert "eplan electric p8" in sw
    assert "rstudio" in sw
    assert not any("grundlagen" in s for s in sw)
    assert not any("kenntnisse" in s for s in sw)


def test_fachkompetenzen_skills_not_certificates():
    text = (
        "Sam Sample\n"
        "Fachkompetenzen\n"
        "Lieferantenkoordination\n"
        "Probenahme\n"
        "Instandhaltung\n"
        "Berufserfahrung\n"
        "2020 Koch | Kantine AG\n"
    )
    assert is_heading("Fachkompetenzen") == "skills"
    parsed = parse_cv_text(text)
    skills = [s.lower() for s in parsed["skills"]]
    assert "lieferantenkoordination" in skills
    assert "probenahme" in skills
    assert "instandhaltung" in skills
    assert not parsed["certificates"]


def test_weitere_angaben_zertifikate_not_heading_as_cert():
    text = (
        "Sam Sample\n"
        "Weitere Angaben\n"
        "Zertifikate: Arbeitssicherheit 2024\n"
        "Berufserfahrung\n"
        "2020 Koch | Kantine AG\n"
    )
    parsed = parse_cv_text(text)
    names = _cert_names(parsed)
    assert any("arbeitssicherheit" in n for n in names)
    assert not any(n.strip() == "weitere angaben" for n in names)


def test_weitere_angaben_without_certificate_stays_empty():
    text = (
        "Sam Sample\n"
        "Weitere Angaben\n"
        "Berufswunsch: Laborleitung\n"
        "Berufserfahrung\n"
        "2020 Koch | Kantine AG\n"
    )
    parsed = parse_cv_text(text)
    assert not any(
        "berufswunsch" in n or "laborleitung" in n for n in _cert_names(parsed)
    )


def test_applications_heading_not_auto_software_without_tools_context():
    assert is_heading("Applications") is None


def test_applications_contextual_software_heading():
    text = (
        "Sam Sample\n"
        "Languages & Driving Licence\n"
        "English: native\n"
        "German: C1\n"
        "Applications\n"
        "ZBrush - Grundlagen\n"
        "RStudio - gute Kenntnisse\n"
        "Core Skills\n"
        "Montageplanung\n"
        "Probenahme\n"
    )
    secs = split_named_sections(text)
    assert "software" in secs
    assert "applications" not in (secs.get("software") or "").lower()
    assert "zbrush" in (secs.get("software") or "").lower()
    parsed = parse_cv_text(text)
    sw = [s.lower() for s in parsed["software"]]
    assert "zbrush" in sw and "rstudio" in sw
    assert "applications" not in [s.lower() for s in parsed["skills"]]


def test_born_dob_and_unicode_name():
    text = (
        "Mikołaj Czarnecki\n"
        "Museumstraße 14 | 6020 Innsbruck | Österreich · "
        "mikolaj@example.de · +49 157 4361029 · Born: 06.12.1983\n"
        "Sprachen\nDeutsch: Muttersprache\n"
    )
    parsed = parse_cv_text(text)
    personal = parsed["personal"]
    assert personal.get("first_name") == "Mikołaj"
    assert personal.get("last_name") == "Czarnecki"
    assert personal.get("date_of_birth") == "06.12.1983"