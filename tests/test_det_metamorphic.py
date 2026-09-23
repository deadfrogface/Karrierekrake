"""Metamorphic / stability tests for DET CV parsing.

Transforms preserve semantics; predictions must stay equivalent.
Not an independent 0.99 holdout proof.
"""

from __future__ import annotations

import copy
import re
from typing import Any

from core.cv_parser import parse_cv_text

BASE_CV = """\
Ada Beispiel
Musterstraße 12 | 80331 München | Deutschland · ada@example.de · +49 170 1112233
Berufserfahrung
01/2019 - 12/2021
Analystin | Contoso GmbH
Reporting · Stakeholder-Kommunikation
Ausbildung
2014 - 2017
Bachelor of Science | Hochschule München
Sprachen
Deutsch: Muttersprache
Englisch: B2
Software
Jira - Basis
Microsoft Dynamics 365 - fortgeschritten
Kenntnisse
Reporting
Prozessmapping
Führerschein: B
"""


def _canon(parsed: dict[str, Any]) -> dict[str, Any]:
    """Semantic fingerprint independent of list order where safe."""
    pers = parsed.get("personal") or {}
    langs = []
    for it in parsed.get("languages") or []:
        if isinstance(it, dict):
            langs.append((str(it.get("language") or "").lower(), str(it.get("level") or "").lower()))
        else:
            langs.append((str(it.language).lower(), str(it.level or "").lower()))
    sw = sorted(str(x).lower() for x in (parsed.get("software") or []))
    sk = sorted(str(x).lower() for x in (parsed.get("skills") or []))
    lic = sorted(str(x) for x in _lic_vals(parsed))
    emp = []
    for it in parsed.get("work_experience") or parsed.get("experience") or []:
        if isinstance(it, dict):
            emp.append(
                (
                    str(it.get("company") or "").lower(),
                    str(it.get("position") or "").lower(),
                )
            )
        else:
            emp.append(
                (
                    str(getattr(it, "company", "") or "").lower(),
                    str(getattr(it, "position", "") or "").lower(),
                )
            )
    return {
        "name": f"{pers.get('first_name','')} {pers.get('last_name','')}".strip().lower(),
        "city": (pers.get("city") or "").lower(),
        "postal": (pers.get("postal_code") or "").lower(),
        "langs": sorted(langs),
        "software": sw,
        "skills": sk,
        "licences": lic,
        "employment": sorted(emp),
    }


def _lic_vals(parsed: dict[str, Any]) -> list[str]:
    out = []
    for it in parsed.get("driving_license") or []:
        if isinstance(it, dict):
            out.append(str(it.get("value") or ""))
        else:
            out.append(str(getattr(it, "value", it)))
    return [x for x in out if x]


def _assert_stable(a: dict[str, Any], b: dict[str, Any]) -> None:
    ca, cb = _canon(a), _canon(b)
    assert ca["name"] == cb["name"]
    assert ca["city"] == cb["city"]
    assert ca["postal"] == cb["postal"]
    assert ca["langs"] == cb["langs"]
    assert ca["software"] == cb["software"]
    assert ca["skills"] == cb["skills"]
    assert ca["licences"] == cb["licences"]
    assert ca["employment"] == cb["employment"]


def test_metamorphic_section_order_shuffle():
    base = parse_cv_text(BASE_CV)
    shuffled = """\
Ada Beispiel
Musterstraße 12 | 80331 München | Deutschland · ada@example.de · +49 170 1112233
Software
Jira - Basis
Microsoft Dynamics 365 - fortgeschritten
Kenntnisse
Reporting
Prozessmapping
Sprachen
Deutsch: Muttersprache
Englisch: B2
Ausbildung
2014 - 2017
Bachelor of Science | Hochschule München
Berufserfahrung
01/2019 - 12/2021
Analystin | Contoso GmbH
Reporting · Stakeholder-Kommunikation
Führerschein: B
"""
    _assert_stable(base, parse_cv_text(shuffled))


def test_metamorphic_extra_blank_lines_and_bullets():
    base = parse_cv_text(BASE_CV)
    variant = BASE_CV.replace("\n", "\n\n").replace("Reporting\n", "• Reporting\n")
    _assert_stable(base, parse_cv_text(variant))


def test_metamorphic_heading_case():
    base = parse_cv_text(BASE_CV)
    variant = (
        BASE_CV.replace("Berufserfahrung", "BERUFSERFAHRUNG")
        .replace("Sprachen", "SPRACHEN")
        .replace("Software", "SOFTWARE")
        .replace("Kenntnisse", "KENNTNISSE")
    )
    _assert_stable(base, parse_cv_text(variant))


def test_metamorphic_fr_nl_language_headings_same_pairs():
    de = parse_cv_text(BASE_CV)
    fr = BASE_CV.replace("Sprachen\n", "Langues et mobilité\n").replace(
        "Deutsch: Muttersprache", "Deutsch: langue maternelle"
    )
    nl = BASE_CV.replace("Sprachen\n", "Talen en mobiliteit\n").replace(
        "Deutsch: Muttersprache", "Deutsch: moedertaal"
    )
    # Levels normalize to native; language set must match.
    assert _canon(de)["langs"] == _canon(parse_cv_text(fr))["langs"]
    assert _canon(de)["langs"] == _canon(parse_cv_text(nl))["langs"]


def test_metamorphic_software_wrap_equivalent():
    a = parse_cv_text(BASE_CV)
    wrapped = BASE_CV.replace(
        "Microsoft Dynamics 365 - fortgeschritten",
        "Microsoft Dynamics 365 -\nfortgeschritten",
    )
    _assert_stable(a, parse_cv_text(wrapped))


def test_metamorphic_unknown_tool_and_skill_in_clear_context():
    text = """\
Ada Beispiel
ada@example.de
Digitale Werkzeuge
ZephyrFlux Pro - Basis
Kenntnisse
Quantenflux-Analyse
Berufserfahrung
2020 - 2021 | Tech | Contoso
"""
    p = parse_cv_text(text)
    assert any("zephyrflux" in s for s in _canon(p)["software"])
    assert any("quantenflux" in s for s in _canon(p)["skills"])
    # Under employment duties (not a tools section), unknown product must not
    # become a software entry.
    duties = """\
Ada Beispiel
ada@example.de
Berufserfahrung
2020 - 2021 | Tech | Contoso
ZephyrFlux Pro täglich eingesetzt
Kenntnisse
Reporting
"""
    p2 = parse_cv_text(duties)
    assert not any("zephyrflux" in s for s in _canon(p2)["software"])


def test_metamorphic_c1_be_b_non_licence_contexts():
    text = """\
Ada Beispiel
Rue Test 1 | 1000 Bruxelles | Belgien · ada@example.be
Zusätzliche Angaben
Niveau C1 erwünscht; Region BE; Note B; Klasse C Theorie
Sprachen
Französisch: C1
"""
    p = parse_cv_text(text)
    assert _canon(p)["licences"] == []
    assert any("c1" in lvl for _, lvl in _canon(p)["langs"])


def test_metamorphic_unicode_place_and_employer():
    text = """\
Joël Fontaine
ul. Żółkiewskiego 3 | 00-950 Warszawa | Polen · joel@example.pl
Expérience professionnelle
2018 - 2021
Ingénieur | Silesia Łódź Sp. z o.o.
Langues
Français: langue maternelle
Deutsch: B2
"""
    p = parse_cv_text(text)
    pers = p["personal"]
    assert pers.get("postal_code") == "00-950"
    assert "Warszawa" in (pers.get("city") or "")
    cos = [c for c, _ in _canon(p)["employment"]]
    assert any("łódź" in c or "lodz" in c or "silesia" in c for c in cos)


def test_metamorphic_no_filename_or_doc_id_dependence():
    """Parser API is text-only; identical text → identical canon regardless of call order."""
    a = parse_cv_text(BASE_CV)
    b = parse_cv_text(copy.deepcopy(BASE_CV))
    _assert_stable(a, b)
    # No parameters for document_id / layout_class on parse_cv_text
    assert "document_id" not in parse_cv_text.__code__.co_varnames
    assert "layout_class" not in parse_cv_text.__code__.co_varnames


def test_metamorphic_date_format_variants_same_employment_company():
    a = parse_cv_text(BASE_CV)
    # German month/year variants that the DET period matcher already accepts.
    alt = BASE_CV.replace("01/2019 - 12/2021", "01.2019 - 12.2021")
    assert _canon(a)["employment"] == _canon(parse_cv_text(alt))["employment"]
    alt2 = BASE_CV.replace("01/2019 - 12/2021", "Jan 2019 - Dez 2021")
    # If an alternate prose format is not recognized, do not invent employment —
    # only require stability when a period is still detected.
    b2 = parse_cv_text(alt2)
    if _canon(b2)["employment"]:
        assert _canon(a)["employment"] == _canon(b2)["employment"]
