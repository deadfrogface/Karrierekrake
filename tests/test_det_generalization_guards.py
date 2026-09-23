"""Contrasting generalization guards for DET post-IH2 repairs.

Each new structural rule is covered by: IH2-like positive, unknown positive,
wrong-section negative, no-heading negative, multilingual / wrap variants.
No document-ID or corpus-specific hardcoding.
"""

from __future__ import annotations

from core.cv_parser import parse_cv_text


def _sw(parsed) -> list[str]:
    return [str(x).lower() for x in (parsed.get("software") or [])]


def _sk(parsed) -> list[str]:
    return [str(x).lower() for x in (parsed.get("skills") or [])]


def _langs(parsed) -> list[tuple[str, str]]:
    out = []
    for it in parsed.get("languages") or []:
        if isinstance(it, dict):
            out.append((str(it.get("language") or "").lower(), str(it.get("level") or "").lower()))
        else:
            out.append((str(it.language).lower(), str(it.level or "").lower()))
    return out


def _lic(parsed) -> list[str]:
    out = []
    for it in parsed.get("driving_license") or []:
        if isinstance(it, dict):
            out.append(str(it.get("value") or ""))
        else:
            out.append(str(getattr(it, "value", it)))
    return out


def _emp_companies(parsed) -> list[str]:
    out = []
    for it in parsed.get("work_experience") or parsed.get("experience") or parsed.get("employment") or []:
        if isinstance(it, dict):
            out.append(str(it.get("company") or "").lower())
        else:
            out.append(str(getattr(it, "company", "") or "").lower())
    return out


# --- Software ---


def test_software_ih2_like_revit_under_tools_section():
    text = (
        "Ada Beispiel\nada@example.com\n"
        "Applications / Programme\n"
        "Revit - Basis\n"
        "Berufserfahrung\n"
        "2020 - 2022 | Planerin | Nordwerk AG\n"
    )
    assert any("revit" in s for s in _sw(parse_cv_text(text)))


def test_software_unknown_tool_under_confirmed_section():
    text = (
        "Bo Tester\nbo@example.com\n"
        "Digitale Werkzeuge\n"
        "ZephyrFlux Pro - fortgeschritten\n"
        "Berufserfahrung\n"
        "2019 - 2021 | Analyst | Contoso GmbH\n"
    )
    assert any("zephyrflux" in s for s in _sw(parse_cv_text(text)))


def test_software_same_token_under_employment_not_software():
    text = (
        "Bo Tester\nbo@example.com\n"
        "Berufserfahrung\n"
        "2019 - 2021 | Analyst | Contoso GmbH\n"
        "ZephyrFlux Pro täglich eingesetzt\n"
        "Kenntnisse\n"
        "Reporting\n"
    )
    sw = _sw(parse_cv_text(text))
    assert not any("zephyrflux" in s for s in sw)


def test_software_heading_date_jobtitle_never_software():
    text = (
        "Bo Tester\nbo@example.com\n"
        "Software\n"
        "Applications / Programme\n"
        "01/2018 - 05/2021\n"
        "Teamassistenz\n"
        "Terminsteuerung · Bauüberwachung\n"
        "Jira - Basis\n"
    )
    sw = _sw(parse_cv_text(text))
    assert any("jira" in s for s in sw)
    assert not any("applications" in s for s in sw)
    assert not any("01/2018" in s or "teamassistenz" in s for s in sw)
    assert not any("terminsteuerung" in s for s in sw)


def test_software_no_heading_global_allowlist_not_enough():
    text = (
        "Bo Tester\nbo@example.com\n"
        "Über mich\n"
        "Ich nutze Excel und SAP privat.\n"
        "Berufserfahrung\n"
        "2020 - 2021 | Helpdesk | Contoso\n"
    )
    # Without a software section, casual mentions must not become a software dump.
    assert _sw(parse_cv_text(text)) == []


def test_software_microsoft_365_wrap_not_bare_365():
    text = (
        "Bo Tester\nbo@example.com\n"
        "Kenntnisse\n"
        "Software: Python, QGIS, Microsoft\n"
        "365, ProTool, Docker\n"
        "Berufserfahrung\n"
        "2020 - 2021 | Tech | Contoso\n"
    )
    sw = _sw(parse_cv_text(text))
    assert any("microsoft 365" in s for s in sw)
    assert "365" not in sw
    assert any("python" in s for s in sw)
    assert any("protool" in s for s in sw)
    text = (
        "Nina Sommer\nnina@example.org\n"
        "TOOLS\n"
        "Notion | Asana | Jira\n"
        "Berufserfahrung\n"
        "2020 - 2021 | PM | Contoso\n"
    )
    sw = _sw(parse_cv_text(text))
    assert any("notion" in s for s in sw)
    assert any("asana" in s for s in sw)


def test_software_slash_list_and_wrap_proficiency():
    text = (
        "Bo Tester\nbo@example.com\n"
        "Outils numériques\n"
        "Microsoft Dynamics 365 -\n"
        "fortgeschritten\n"
        "DATEV Lohn und Gehalt / Navision 2018\n"
    )
    sw = _sw(parse_cv_text(text))
    assert any("dynamics" in s for s in sw)
    assert any("datev" in s or "navision" in s for s in sw)


def test_software_organisation_skill_not_accepted_as_tool():
    text = (
        "Bo Tester\nbo@example.com\n"
        "Software\n"
        "Organisation\n"
        "Kommunikation\n"
        "Jira\n"
    )
    sw = _sw(parse_cv_text(text))
    assert any("jira" in s for s in sw)
    assert not any(s == "organisation" for s in sw)
    assert not any(s == "kommunikation" for s in sw)


# --- Languages ---


def test_language_cefr_pair_extracted():
    text = (
        "Ada Beispiel\nada@example.com\n"
        "Sprachen\n"
        "Deutsch: Muttersprache\n"
        "Englisch: B2\n"
        "Berufserfahrung\n"
        "2020 - 2021 | Dev | Firma\n"
    )
    langs = _langs(parse_cv_text(text))
    assert any(a.startswith("deutsch") and "native" in b for a, b in langs)
    assert any(a.startswith("englisch") and "b2" in b for a, b in langs)


def test_language_unknown_endonym_in_clear_section():
    """Unknown-to-taxonomy endonym still accepted when section + CEFR structure clear."""
    text = (
        "Ada Beispiel\nada@example.com\n"
        "Talen en mobiliteit\n"
        "Nederlands: moedertaal\n"
        "Deutsch: B1\n"
    )
    langs = _langs(parse_cv_text(text))
    assert any("nederlands" in a or "niederländ" in a for a, _ in langs)
    assert any(a.startswith("deutsch") for a, _ in langs)


def test_language_c1_without_language_context_not_language():
    text = (
        "Ada Beispiel\nada@example.com\n"
        "Zusätzliche Angaben\n"
        "C1\n"
        "Berufserfahrung\n"
        "2020 - 2021 | Dev | Firma\n"
    )
    langs = _langs(parse_cv_text(text))
    assert langs == []


def test_language_c1_in_language_section_not_licence():
    text = (
        "Ada Beispiel\nada@example.com\n"
        "Languages & Mobility\n"
        "English: C1\n"
        "Deutsch: B2\n"
    )
    p = parse_cv_text(text)
    langs = _langs(p)
    assert any("english" in a or "englisch" in a for a, b in langs if "c1" in b)
    assert "C1" not in _lic(p)


def test_language_fr_nl_headings():
    text = (
        "Ada Beispiel\nada@example.com\n"
        "Langues et mobilité\n"
        "Français: langue maternelle\n"
        "Allemand: B2\n"
    )
    langs = _langs(parse_cv_text(text))
    assert any("français" in a or "franz" in a for a, _ in langs)


def test_language_materni_jezik_normalizes_to_native():
    """SL/HR mother-tongue phrasing must normalize like Muttersprache."""
    text = (
        "Ada Beispiel\nada@example.com\n"
        "Talen en mobiliteit\n"
        "Slovenščina: materni jezik\n"
        "Deutsch: B2\n"
    )
    langs = _langs(parse_cv_text(text))
    assert any("sloven" in a and b == "native" for a, b in langs)
    # Unknown language name still accepted with same structural marker.
    text2 = (
        "Ada Beispiel\nada@example.com\n"
        "Sprachen\n"
        "Hrvatski: materinski jezik\n"
        "Englisch: B1\n"
    )
    langs2 = _langs(parse_cv_text(text2))
    assert any("hrvatski" in a and b == "native" for a, b in langs2)


# --- Skills ---


def test_skills_from_vaardigheden_section():
    text = (
        "Ada Beispiel\nada@example.com\n"
        "Vaardigheden\n"
        "Hydrologische Messung\n"
        "Quantenflux-Analyse\n"
        "Berufserfahrung\n"
        "2020 - 2021 | Tech | Firma\n"
    )
    sk = _sk(parse_cv_text(text))
    assert any("hydrologische" in s for s in sk)
    assert any("quantenflux" in s for s in sk)


def test_skills_heading_not_stored():
    text = (
        "Ada Beispiel\nada@example.com\n"
        "Core Competencies\n"
        "Core Competencies\n"
        "Reporting\n"
    )
    sk = _sk(parse_cv_text(text))
    assert any("reporting" in s for s in sk)
    assert not any("core competencies" == s for s in sk)


def test_skills_employment_line_not_copied():
    text = (
        "Ada Beispiel\nada@example.com\n"
        "Vaardigheden\n"
        "Reporting\n"
        "Werkervaring\n"
        "03/2018 - 08/2021\n"
        "Processoperatör | Grenzland Mobilität SE\n"
        "Hydrologische Messung · Lieferantenprüfung\n"
    )
    sk = _sk(parse_cv_text(text))
    assert any("reporting" in s for s in sk)
    assert not any("processoperatör" in s or "grenzland" in s for s in sk)
    assert not any("03/2018" in s for s in sk)


def test_skills_middot_list_not_emp_leak():
    text = (
        "Ada Beispiel\nada@example.com\n"
        "Core Competencies\n"
        "Terminsteuerung • Bauüberwachung • Routenplanung\n"
        "Professional Experience\n"
        "2019 - 2020 | Tech | Contoso\n"
    )
    sk = _sk(parse_cv_text(text))
    assert any("terminsteuerung" in s for s in sk)
    assert any("bauüberwachung" in s or "bauueberwachung" in s for s in sk)


# --- Employment ---


def test_employment_only_from_employment_blocks():
    text = (
        "Ada Beispiel\nada@example.com\n"
        "Expérience professionnelle\n"
        "10/2018 - 03/2021\n"
        "Landschaftsökologin | Fjord Prüfservice AB\n"
        "Werkstoffanalyse · Reklamationsbearbeitung\n"
        "Compétences\n"
        "Kundenberatung\n"
    )
    cos = _emp_companies(parse_cv_text(text))
    assert any("fjord" in c for c in cos)
    assert not any("kundenberatung" in c for c in cos)


def test_employment_not_invented_from_skills_software():
    text = (
        "Ada Beispiel\nada@example.com\n"
        "Software\n"
        "LabWare LIMS - Basis\n"
        "Compétences\n"
        "Werkstoffanalyse\n"
        "Einsatzplanung\n"
    )
    p = parse_cv_text(text)
    assert _emp_companies(p) == []
    assert any("labware" in s for s in _sw(p))


# --- Licence vs BE / C1 ---


def test_licence_be_from_driving_context_only():
    text = (
        "Ada Beispiel\nada@example.com\n"
        "Adresse: Rue de la Loi 1 | 1000 Bruxelles | Belgien\n"
        "Führerschein: B, BE\n"
        "Sprachen\n"
        "Französisch: C1\n"
    )
    p = parse_cv_text(text)
    lic = _lic(p)
    assert "B" in lic and "BE" in lic
    assert "C1" not in lic


def test_be_country_not_licence():
    text = (
        "Ada Beispiel\nada@example.com\n"
        "Boulevard Test 10 | 4000 Liège | Belgien\n"
        "Sprachen\n"
        "Deutsch: B2\n"
    )
    assert _lic(parse_cv_text(text)) == []


def test_composite_sprachen_fahrerlaubnis_language_not_licence_letter():
    """Türkisch/Dänisch under Sprachen & Fahrerlaubnis must not become T/D."""
    text = (
        "Ada Beispiel\nada@example.com\n"
        "Sprachen & Fahrerlaubnis\n"
        "Türkisch - Muttersprache\n"
        "Englisch - B1\n"
        "Software\n"
        "Jira: gut\n"
    )
    p = parse_cv_text(text)
    assert _lic(p) == []
    assert any("türkisch" in a for a, _ in _langs(p))

    text2 = (
        "Ada Beispiel\nada@example.com\n"
        "Sprachen & Fahrerlaubnis\n"
        "Dänisch - A2\n"
        "Englisch - B2\n"
        "Führerschein: B\n"
    )
    p2 = parse_cv_text(text2)
    assert "D" not in _lic(p2)
    assert "B" in _lic(p2)


# --- Address structural (not document-specific) ---


def test_address_pl_pattern_unknown_city():
    text = (
        "Ada Beispiel\n"
        "ul. Nowa 7 | 00-001 Przykładów | Polen · ada@example.pl\n"
        "Berufserfahrung\n"
        "2020 - 2021 | Tech | Firma\n"
    )
    p = parse_cv_text(text)["personal"]
    assert p.get("postal_code") == "00-001"
    assert "Przykładów" in (p.get("city") or "")
    assert p.get("house_number") == "7"


def test_address_city_only_four_digit_with_country():
    text = (
        "Ada Beispiel\n"
        "5020 Beispielstadt | Österreich · ada@example.at\n"
        "Berufserfahrung\n"
        "2020 - 2021 | Tech | Firma\n"
    )
    p = parse_cv_text(text)["personal"]
    assert p.get("postal_code") == "5020"
    assert p.get("city") == "Beispielstadt"
    assert p.get("country") == "Österreich"
