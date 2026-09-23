"""Address parsing: parentheses cities, AT PLZ, FR country codes."""

from __future__ import annotations

from core.cv_parser import parse_cv_text


def test_frankfurt_oder_parentheses_city():
    text = """
Dana Vogel
Hafenallee 40, 15230 Frankfurt (Oder), DE | dana@example.de | +49 153 1023757
Work Experience
01/2018 - heute | Hafenlogistiker | Nordwerk AG
"""
    r = parse_cv_text(text)
    p = r["personal"]
    assert p.get("postal_code") == "15230"
    assert "Frankfurt" in (p.get("city") or "")
    assert p.get("country") == "DE"
    assert p.get("street")
    assert p.get("house_number") == "40"


def test_at_four_digit_postal_and_country():
    text = """
Valerie Xu
Kirchplatz 86, 5020 Salzburg, AT | valerie@example.de | +49 151 1166299
Praxis
01/2018 - heute | Näherin | Nordwerk KG
"""
    r = parse_cv_text(text)
    p = r["personal"]
    assert p.get("postal_code") == "5020"
    assert p.get("city") == "Salzburg"
    assert p.get("country") == "AT"


def test_fr_country_code_on_address_line():
    text = """
Yara Lutz
Marktstraße 61, 67000 Strasbourg, FR | yara@example.de | +49 158 1380112
Work Experience
01/2018 - heute | Revierjäger | Nordwerk GmbH
"""
    r = parse_cv_text(text)
    p = r["personal"]
    assert p.get("postal_code") == "67000"
    assert p.get("city") == "Strasbourg"
    assert p.get("country") == "FR"


def test_pl_postal_with_l_stroke_city():
    text = """
Kinga Wójcik
ul. Jedności Robotniczej 22 | 69-100 Słubice | Polen · kinga@example.pl · +49 480 317910
Werkervaring
11/2018 - 04/2021 | Geomatikerin | Komet Vermessung eG
"""
    r = parse_cv_text(text)
    p = r["personal"]
    assert p.get("street") == "ul. Jedności Robotniczej"
    assert p.get("house_number") == "22"
    assert p.get("postal_code") == "69-100"
    assert p.get("city") == "Słubice"
    assert p.get("country") == "Polen"


def test_city_only_at_four_digit_postal():
    text = """
Xenia Bühler
6900 Bregenz | Österreich · xenia@example.at · +49 473 328193
Professional Experience
12/2018 - 05/2021 | Teamassistenz | Grenzland Mobilität SE
"""
    r = parse_cv_text(text)
    p = r["personal"]
    assert p.get("postal_code") == "6900"
    assert p.get("city") == "Bregenz"
    assert p.get("country") == "Österreich"


def test_city_only_cz_spaced_postal():
    text = """
Mara Černá
350 02 Cheb | Tschechien · mara@example.cz · +49 482 319492
Beruflicher Werdegang
01/2018 - heute | Kerammodelleurin | Marex Marine BV
"""
    r = parse_cv_text(text)
    p = r["personal"]
    assert p.get("postal_code") == "350 02"
    assert p.get("city") == "Cheb"
    assert p.get("country") == "Tschechien"


def test_city_only_be_four_digit_postal():
    text = """
Maëlle Renard
7000 Mons | Belgien · maelle@example.be · +32 488 340058
Werkervaring
03/2018 - 08/2021 | Technicienne forestière | Silex Industrie s.r.o.
"""
    r = parse_cv_text(text)
    p = r["personal"]
    assert p.get("postal_code") == "7000"
    assert p.get("city") == "Mons"
    assert p.get("country") == "Belgien"


def test_wrapped_fachkenntnisse_merges_compound():
    text = """
Name Test
test@example.com
Kenntnisse
Software: Excel
Fachkenntnisse: Hygiene, Handwerkliches
Geschick, Tourenplanung
"""
    r = parse_cv_text(text)
    skills_l = " ".join(r["skills"]).lower()
    assert "handwerkliches geschick" in skills_l or "tourenplanung" in skills_l
    # Bare wrap fragment must not remain once the compound exists.
    if any("handwerkliches geschick" == s.lower() for s in r["skills"]):
        assert "geschick" not in [s.lower() for s in r["skills"]]
