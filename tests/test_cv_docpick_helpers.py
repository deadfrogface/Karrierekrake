"""Unit tests for Docpick CV import helpers (no DET, no live LLM)."""

from __future__ import annotations

from core.cv_docpick_import import (
    _enrich_address_from_text,
    _fix_employment_pipe,
    _merge_split_employment,
    _norm_month_year,
    _norm_period_end,
    _split_street_house,
    _strip_skill_level,
    suggestion_to_parsed,
)


def test_norm_period_end_maps_present_spellings_to_heute() -> None:
    for raw in ("Present", "current", "bis heute", "ongoing", "jetzt", "—", "-", "heute"):
        assert _norm_period_end(raw) == "heute", raw
    assert _norm_period_end("02/2019") == "02/2019"
    assert _norm_period_end("") == ""
    assert _norm_month_year("2019-02") == "02/2019"


def test_split_street_house_and_software_level() -> None:
    assert _split_street_house("Schäferstraße 69c", "") == ("Schäferstraße", "69c")
    assert _strip_skill_level("Tableau - Grundlagen") == "Tableau"


def test_employment_pipe_and_merge() -> None:
    fixed = _fix_employment_pipe(
        [
            {
                "title": "Materialdisposition",
                "company": "Deichbauer | Nordlicht Manufaktur",
                "start_date": "02/2019",
                "end_date": "08/2021",
                "responsibilities": [],
            }
        ]
    )
    assert fixed[0]["title"] == "Deichbauer"
    assert fixed[0]["company"] == "Nordlicht Manufaktur"
    merged = _merge_split_employment(
        [
            {
                "title": "Uhrentechnikerin",
                "company": "",
                "start_date": "02/2019",
                "end_date": "",
                "responsibilities": [],
            },
            {
                "title": "",
                "company": "Mosaik Dienste AG",
                "start_date": "08/2021",
                "end_date": "",
                "responsibilities": [],
            },
        ]
    )
    assert len(merged) == 1
    assert merged[0]["company"] == "Mosaik Dienste AG"


def test_enrich_address_uk_ch_city() -> None:
    empty = {k: "" for k in ("street", "house_number", "postal_code", "city", "country")}
    uk = _enrich_address_from_text(
        dict(empty),
        "## Daniel Brooks\n\n42 Kingfisher Road · Manchester M1 2AB a@b.com\n",
    )
    assert uk["street"] == "Kingfisher Road"
    assert uk["house_number"] == "42"
    assert uk["city"] == "Manchester"
    ch = _enrich_address_from_text(
        dict(empty),
        "Genève | Schweiz · connor.smith@example.co.uk\n",
    )
    assert ch["city"] == "Genève"
    assert ch["country"] == "Schweiz"
    de = _enrich_address_from_text(
        dict(empty),
        "## Nina Sommer\n\nLeipzig | nina.sommer@example.org\n",
    )
    assert de["city"] == "Leipzig"


def test_suggestion_maps_current_job_end_date() -> None:
    parsed = suggestion_to_parsed(
        {
            "name": {"first_name": "Anna", "last_name": "Beispiel"},
            "email": "anna@example.com",
            "employment": [
                {
                    "company": "Firma GmbH",
                    "position": "Entwicklerin",
                    "start_date": "01/2020",
                    "end_date": "Present",
                }
            ],
            "education": [
                {
                    "institution": "Uni",
                    "qualification": "Studium abgebrochen",
                    "start_date": "2015",
                    "end_date": "ohne Abschluss",
                }
            ],
        }
    )
    assert parsed["work_experience"][0]["end_date"] == "heute"
    assert parsed["education"][0]["end_date"] == "ohne Abschluss"
    assert parsed["education"][0]["qualification"] == "Studium abgebrochen"
