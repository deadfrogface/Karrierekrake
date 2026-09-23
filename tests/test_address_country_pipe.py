"""Address country / pipe-separated header extraction tests."""

from __future__ import annotations

from core.cv_parser import parse_cv_text


def test_country_after_pipe_deutschland():
    text = (
        "Aylin Berger\n"
        "Lütticher Straße 3a | 52064 Aachen | Deutschland · a@example.de · +49 151 2300000\n"
        "Berufserfahrung\nSachbearbeiter | Firma GmbH\n"
    )
    p = parse_cv_text(text)
    pers = p["personal"]
    assert pers.get("country") == "Deutschland"
    assert pers.get("city") == "Aachen"
    assert pers.get("postal_code") == "52064"
    assert "Lütticher" in (pers.get("street") or "")
    assert pers.get("house_number") == "3a"


def test_country_after_pipe_schweiz_four_digit():
    text = (
        "Klara Lindholm\n"
        "Spalenvorstadt 113 | 4051 Basel | Schweiz · k@example.org · +41 79 1234567\n"
        "Berufspraxis\nLaborassistentin | Beispiel AG\n"
    )
    p = parse_cv_text(text)
    pers = p["personal"]
    assert pers.get("country") == "Schweiz"
    assert pers.get("city") == "Basel"
    assert pers.get("postal_code") == "4051"
    assert "Spalenvorstadt" in (pers.get("street") or "")


def test_country_comma_still_works():
    text = (
        "Max Mustermann\n"
        "Musterstraße 1, 10115 Berlin, Deutschland\n"
        "Berufserfahrung\nEntwickler | Tech GmbH\n"
    )
    p = parse_cv_text(text)
    assert p["personal"].get("country") == "Deutschland"
    assert p["personal"].get("city") == "Berlin"


def test_no_country_not_invented():
    text = (
        "Max Mustermann\n"
        "Berlin\n"
        "Berufserfahrung\nEntwickler | Tech GmbH\n"
    )
    p = parse_cv_text(text)
    assert not (p["personal"].get("country") or "").strip()
    assert p["personal"].get("city") == "Berlin"


def test_house_number_letter_suffix():
    text = (
        "Name Test\n"
        "Hauptstraße 12b | 80331 München | Deutschland\n"
        "Sprachen\nDeutsch – Muttersprache\n"
    )
    p = parse_cv_text(text)
    assert p["personal"].get("house_number") == "12b"
    assert p["personal"].get("country") == "Deutschland"


def test_country_niederlande_nl_postal():
    text = (
        "Levent Mancini\n"
        "Oldenzaalsestraat 124 | 7511 AB Enschede | Niederlande · a@example.nl\n"
        "Berufspraxis\nMediendesigner | Firma BV\n"
    )
    p = parse_cv_text(text)
    assert p["personal"].get("country") == "Niederlande"
    assert "7511" in (p["personal"].get("postal_code") or "")
    assert "Enschede" in (p["personal"].get("city") or "")


def test_country_luxemburg_l_postal():
    text = (
        "Olga Pietsch\n"
        "Rue de la Gare 13 | L-1616 Luxembourg | Luxemburg · o@example.lu\n"
        "Berufspraxis\nAnalyst | Bank SA\n"
    )
    p = parse_cv_text(text)
    assert p["personal"].get("country") == "Luxemburg"
    assert p["personal"].get("postal_code") == "1616"
    assert "Luxembourg" in (p["personal"].get("city") or "")


def test_city_country_only_luxembourg():
    text = (
        "Khadija Oltmann\n"
        "Luxembourg | Luxemburg · k@example.lu\n"
        "Sprachen\nDeutsch – Muttersprache\n"
    )
    p = parse_cv_text(text)
    assert p["personal"].get("city") == "Luxembourg"
    assert p["personal"].get("country") == "Luxemburg"
    assert not (p["personal"].get("street") or "").strip()


def test_date_first_duty_line_not_next_title():
    text = (
        "Name\n"
        "Berufspraxis\n"
        "01/2018 - 06/2020\n"
        "Milchtechnologe | Rheinbogen Service KG\n"
        "Qualitätssicherung · Prozessoptimierung\n"
        "02/2019 - 07/2021\n"
        "Werkstudent/in | Atelier Morgenrot\n"
        "Warenkontrolle · Bestandsführung\n"
    )
    p = parse_cv_text(text)
    jobs = p["work_experience"]
    assert len(jobs) >= 2
    assert jobs[0]["title"] == "Milchtechnologe"
    assert jobs[0]["company"] == "Rheinbogen Service KG"
    assert any("Qualitätssicherung" in r for r in (jobs[0].get("responsibilities") or []))
    assert jobs[1]["title"] == "Werkstudent/in"
    assert jobs[1]["company"] == "Atelier Morgenrot"
