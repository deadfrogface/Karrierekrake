"""Unit tests for Docpick CV import helpers (no DET, no live LLM)."""

from __future__ import annotations

from core.hardware_peak_gate import RETIRED_SOFT_12GB_DECIMAL_BYTES
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


def test_peak_rss_hard_gate_is_3_3gb_bytes_not_12_gb() -> None:
    """Merge gate is ≤ 3_300_000_000 bytes — RETIRED_NOT_A_PASS soft 12 GB must not be the default."""
    from core.cv_docpick_import import (
        CV_IMPORT_PEAK_RSS_BYTES_MAX,
        CV_IMPORT_PEAK_RSS_GB_MAX,
        CV_IMPORT_PEAK_RSS_MB_MAX,
    )

    assert CV_IMPORT_PEAK_RSS_BYTES_MAX == 3_300_000_000
    assert abs(CV_IMPORT_PEAK_RSS_MB_MAX - (3_300_000_000 / (1024.0 * 1024.0))) < 1e-9
    assert abs(CV_IMPORT_PEAK_RSS_GB_MAX - (3_300_000_000 / (1024.0 ** 3))) < 1e-9
    assert CV_IMPORT_PEAK_RSS_BYTES_MAX < RETIRED_SOFT_12GB_DECIMAL_BYTES  # RETIRED_NOT_A_PASS


def test_norm_period_end_maps_present_spellings_to_heute() -> None:
    for raw in ("Present", "current", "bis heute", "ongoing", "jetzt", "—", "-", "heute"):
        assert _norm_period_end(raw) == "heute", raw
    assert _norm_period_end("02/2019") == "02/2019"
    assert _norm_period_end("") == ""
    assert _norm_month_year("2019-02") == "02/2019"


def test_split_street_house_and_software_level() -> None:
    assert _split_street_house("Schäferstraße 69c", "") == ("Schäferstraße", "69c")
    # The number is in the street and in its own field: it leaves the street.
    assert _split_street_house("Buchenweg 14", "14") == ("Buchenweg", "14")
    assert _split_street_house("Am Stadtpark 22b", "22B") == ("Am Stadtpark", "22B")
    # Another number in the field: nothing is known about which one is right, both stay.
    assert _split_street_house("Buchenweg 14", "16") == ("Buchenweg 14", "16")
    assert _split_street_house("Buchenweg", "14") == ("Buchenweg", "14")
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


def test_explicit_inline_role_is_not_replaced_by_nearby_tools():
    from core.cv_docpick_import import _repair_duty_as_title
    row = {"title": "Projektassistenz", "company": "Example Media GmbH",
           "start_date": "10/2021", "end_date": "10/2023", "responsibilities": []}
    source = ("10/2021 - 10/2023 Projektassistenz | Example Media GmbH\n"
              "ZERTIFIKATE\nExcel Advanced\nTOOLS\nNotion | Asana | Jira")
    assert _repair_duty_as_title([row], source) == [row]


def test_enrich_address_uk_ch_city() -> None:
    empty = {k: "" for k in ("street", "house_number", "postal_code", "city", "country")}
    uk = _enrich_address_from_text(
        dict(empty),
        "## Daniel Brooks\n\n42 Kingfisher Road · Manchester M1 2AB a@example.com\n",
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


def test_norm_dob_formats() -> None:
    from core.cv_docpick_import import _norm_dob

    assert _norm_dob("1991-02-19") == "19.02.1991"
    assert _norm_dob("19/02/1991") == "19.02.1991"
    assert _norm_dob("1985/06/25") == "25.06.1985"
    assert _norm_dob("19.02.1991") == "19.02.1991"


def test_merge_partial_license_from_fuehrerschein_line() -> None:
    """LLM may return only B while text lists B, C1 — merge from source text."""
    from core.cv_docpick_import import _license_codes_from_source_text

    assert _license_codes_from_source_text("Führerschein: B, C1\n") == ["B", "C1"]
    # CEFR levels before Führerschein must not become licence classes.
    assert _license_codes_from_source_text(
        "Polnisch: B1 Englisch: C1 Führerschein: B\n"
    ) == ["B"]
    assert _license_codes_from_source_text(
        "## Fahrerlaubnis\nKlassen B und C1\n"
    ) == ["B", "C1"]
    # Heading alone / languages without FS colon → no codes.
    assert _license_codes_from_source_text(
        "## Sprachkenntnisse & Führerschein\nGriechisch: C1\n"
    ) == []

    parsed = suggestion_to_parsed(
        {
            "name": {"first_name": "A", "last_name": "B"},
            "email": "a@example.com",
            "licenses": ["B"],
            "employment": [],
            "education": [],
            "skills": [],
            "software": [],
            "certificates": [],
            "languages": [],
        },
        source_text="Führerschein: B, C1\nDeutsch C2 | Englisch C1\n",
    )
    assert "B" in parsed["driving_license"]
    assert "C1" in parsed["driving_license"]


def test_present_end_re_does_not_match_empty() -> None:
    from core.cv_docpick_import import _PRESENT_END_RE

    assert _PRESENT_END_RE.match("") is None
    assert _PRESENT_END_RE.match("heute")
    assert _norm_period_end("") == ""


def test_education_null_end_stays_empty_not_heute() -> None:
    parsed = suggestion_to_parsed(
        {
            "name": {"first_name": "A", "last_name": "B"},
            "email": "a@example.com",
            "employment": [],
            "education": [
                {
                    "institution": "Berufsschule",
                    "qualification": "Ausbildung X",
                    "start_date": None,
                    "end_date": None,
                }
            ],
            "skills": [],
            "software": [],
            "certificates": [],
            "languages": [],
        }
    )
    assert parsed["education"][0]["end_date"] == ""


def test_enrich_education_from_ausbildung_section() -> None:
    from core.cv_docpick_import import _enrich_education_from_text

    text = (
        "## Berufserfahrung\n\n## Koch | Restaurant\n\n03/2017 - 08/2024\n\n"
        "## Ausbildung\n\nAusbildung Koch, BBS Trier\n\n## Sprachen\n\nDeutsch\n"
    )
    filled = _enrich_education_from_text([], text)
    assert len(filled) == 1
    assert filled[0]["qualification"] == "Ausbildung Koch, BBS Trier"
    # Do not overwrite non-empty LLM education.
    assert _enrich_education_from_text(
        [{"qualification": "keep", "institution": "", "start_date": "", "end_date": ""}],
        text,
    )[0]["qualification"] == "keep"


def test_enrich_dob_and_repair_heute_from_text() -> None:
    from core.cv_docpick_import import _enrich_dob_from_text, _repair_invented_heute

    pers = _enrich_dob_from_text(
        {"date_of_birth": "02/1970"},
        "Geburtsdatum: 02.01.1970\n",
    )
    assert pers["date_of_birth"] == "02.01.1970"
    fixed = _repair_invented_heute(
        [
            {
                "title": "Deichbauer",
                "company": "Nordlicht Manufaktur",
                "start_date": "02/2019",
                "end_date": "heute",
                "responsibilities": [],
            }
        ],
        "02/2019 - 08/2021 Deichbauer | Nordlicht Manufaktur Materialdisposition\n",
    )
    assert fixed[0]["end_date"] == "08/2021"


def test_repair_heute_requires_matching_start_same_block() -> None:
    from core.cv_docpick_import import _repair_invented_heute

    # True current job — neighbour has a dated end; must NOT steal it.
    text = (
        "## Hotelfachfrau | Dreiflüssestadt Hotel\n\n"
        "2017-08 - heute Rezeption\n\n"
        "## Aushilfe | Café Altstadt\n\n"
        "2015-01 - 2016-12 Service\n"
    )
    kept = _repair_invented_heute(
        [
            {
                "title": "Hotelfachfrau",
                "company": "Dreiflüssestadt Hotel",
                "start_date": "08/2017",
                "end_date": "heute",
                "responsibilities": [],
            }
        ],
        text,
    )
    assert kept[0]["end_date"] == "heute"

    # Invented heute with matching dated end in same block → repair.
    dated = (
        "## Koch | Restaurant Moselufer\n\n"
        "03/2017 - 08/2024\n\nÀ-la-carte-Service\n\n"
        "## Ausbildung\n\nAusbildung Koch\n"
    )
    fixed = _repair_invented_heute(
        [
            {
                "title": "Koch",
                "company": "Restaurant Moselufer",
                "start_date": "03/2017",
                "end_date": "heute",
                "responsibilities": [],
            }
        ],
        dated,
    )
    assert fixed[0]["end_date"] == "08/2024"


def test_suggestion_repair_heute_via_source_text() -> None:
    parsed = suggestion_to_parsed(
        {
            "name": {"first_name": "David", "last_name": "Wolf"},
            "email": "d@example.com",
            "employment": [
                {
                    "company": "Restaurant Moselufer",
                    "position": "Koch",
                    "start_date": "03/2017",
                    "end_date": "heute",
                }
            ],
            "education": [],
            "skills": [],
            "software": [],
            "certificates": [],
            "languages": [],
        },
        source_text=(
            "## Koch | Restaurant Moselufer\n\n03/2017 - 08/2024\n\n"
            "## Ausbildung\n\nAusbildung Koch, BBS Trier\n"
        ),
    )
    assert parsed["work_experience"][0]["end_date"] == "08/2024"
    assert parsed["education"][0]["qualification"] == "Ausbildung Koch, BBS Trier"


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


def test_table_end_date_self_employed_software_duty_apostrophe() -> None:
    from core.cv_docpick_import import (
        _enrich_software_from_text,
        _fix_employment_pipe,
        _normalize_person_apostrophes,
        _preserve_education_source_phrasing,
        _repair_duty_as_title,
        _repair_invented_heute,
        _reroute_certs_software_skills,
    )

    table = (
        "## Berufserfahrung\n\n"
        "| 02/2019   | Uhrentechnikerin                   |\n"
        "|-----------|------------------------------------|\n"
        "| 08/2021   | Mosaik Dienste AG                  |\n"
    )
    fixed = _repair_invented_heute(
        [
            {
                "title": "Uhrentechnikerin",
                "company": "Mosaik Dienste AG",
                "start_date": "02/2019",
                "end_date": "heute",
                "responsibilities": [],
            }
        ],
        table,
    )
    assert fixed[0]["end_date"] == "08/2021"

    self_emp = _fix_employment_pipe(
        [
            {
                "title": "Freelance Translator | Self-employed",
                "company": "",
                "start_date": "03/2018",
                "end_date": "heute",
                "responsibilities": [],
            }
        ]
    )
    assert self_emp[0]["title"] == "Freelance Translator"
    assert self_emp[0]["company"].lower().startswith("self")

    apos = _normalize_person_apostrophes(
        {"first_name": "Finn", "last_name": "O\u2019Connor"}
    )
    assert apos["last_name"] == "O'Connor"

    edu = _preserve_education_source_phrasing(
        [
            {
                "institution": "",
                "qualification": "Schule ohne Abschluss",
                "start_date": "",
                "end_date": "ohne Abschluss",
            }
        ],
        "Left school at 16 without qualifications\n",
    )
    assert "Left school" in edu[0]["qualification"]

    certs, soft, skills = _reroute_certs_software_skills(
        [
            {"name": "TIA Portal"},
            {"name": "Basic Life Support"},
            {"name": "Communication aids"},
        ],
        [],
        ["Session notes"],
    )
    assert any(c["name"] == "Basic Life Support" for c in certs)
    assert "TIA Portal" in soft
    assert "Communication aids" in skills

    soft2 = _enrich_software_from_text(
        [],
        "## Applications\n\nMinitab - Grundlagen Qlik Sense - gute Kenntnisse\n",
    )
    assert "Minitab" in soft2
    assert any("Qlik" in s for s in soft2)

    duty = _repair_duty_as_title(
        [
            {
                "title": "Sprechstundenkoordination",
                "company": "Gemeinschaftspraxis Förde",
                "start_date": "02/2018",
                "end_date": "heute",
                "responsibilities": [],
            }
        ],
        "Medizinische Fachangestellte\nGemeinschaftspraxis Förde\nSprechstundenkoordination\n",
    )
    assert duty[0]["title"] == "Medizinische Fachangestellte"
    assert "Sprechstundenkoordination" in duty[0]["responsibilities"]


STATIONS = (
    "Berufserfahrung\n"
    "2007-04 bis 2009-01 — Klinikverbund Westfalen, Dortmund\nStationssekretariat\n"
    "2005-08 bis 2007-03 — Buchhandlung Lesart, Bonn\nBuchhändlerin\n"
    "2003-09 bis 2005-07 — Bäckerei Holm, Köln\nVerkäuferin\n"
)


def _station(company: str, start: str, end: str) -> dict[str, str]:
    return {"title": "", "company": company, "start_date": start, "end_date": end}


def test_a_station_with_its_neighbours_dates_gets_the_period_of_its_own_line() -> None:
    from core.cv_docpick_import import _repair_dates_from_company_line as repair

    swapped = [_station("Klinikverbund Westfalen", "04/2007", "01/2009"),
               _station("Buchhandlung Lesart", "09/2003", "07/2005"),
               _station("Bäckerei Holm", "08/2005", "03/2007")]
    fixed = repair(swapped, STATIONS)
    assert [(e["start_date"], e["end_date"]) for e in fixed] == [
        ("04/2007", "01/2009"), ("08/2005", "03/2007"), ("09/2003", "07/2005")]
    assert repair(fixed, STATIONS) == fixed
    assert repair([_station("Bäckerei Holm", "", "")], STATIONS)[0]["start_date"] == "09/2003"


def test_the_period_is_left_alone_where_the_document_leaves_a_choice() -> None:
    from core.cv_docpick_import import _repair_dates_from_company_line as repair

    wrong = _station("Bäckerei Holm", "08/2005", "03/2007")
    # the employer on two lines, two periods on its line, no period on its line, a name too short to be sure
    for text in (STATIONS + "Zeugnis der Bäckerei Holm liegt vor\n",
                 "2003-09 bis 2005-07 und 2010-01 bis 2011-01 — Bäckerei Holm\n",
                 "Bäckerei Holm, Köln\n2003-09 bis 2005-07\n",
                 ""):
        assert repair([wrong], text) == [wrong]
    assert repair([_station("Hol", "08/2005", "03/2007")], STATIONS)[0]["start_date"] == "08/2005"
    # the document gives years only: an entry with months of those years is not made coarser
    years = "2019 - 2022 | Supply Chain Administrator | Meridian Homeware Ltd\n"
    precise = _station("Meridian Homeware Ltd", "03/2019", "11/2022")
    assert repair([precise], years) == [precise]
    assert repair([_station("Meridian Homeware Ltd", "2016", "2019")], years)[0]["start_date"] == "2019"
    current = "02.2024 - heute | Operations Analyst | Franken Logistik Solutions GmbH\n"
    assert repair([_station("Franken Logistik Solutions GmbH", "02/2024", "01/2024")], current)[0]["end_date"] == "heute"


def test_the_year_a_certificate_line_starts_with_is_its_year() -> None:
    from core.cv_docpick_import import _certificate_with_year as cert

    assert cert("2024 Lean Management Basics") == {"name": "Lean Management Basics", "issuer": "", "year": "2024"}
    assert cert("Arbeitssicherheit 2025") == {"name": "Arbeitssicherheit 2025", "issuer": "", "year": ""}
    assert cert("ISO 9001 Auditor") == {"name": "ISO 9001 Auditor", "issuer": "", "year": ""}
    assert cert("2024") == {"name": "2024", "issuer": "", "year": ""}


def test_a_course_listed_as_certificate_is_not_an_education_entry_too() -> None:
    from core.cv_docpick_import import _without_certificates_listed_as_education as clean

    certificates = [{"name": "Lean Management Basics", "issuer": "", "year": "2024"}]
    degree = {"institution": "Hochschule Beispielstadt", "qualification": "BCom", "start_date": "2012", "end_date": "2016"}
    again = {"institution": "", "qualification": "2024 Lean Management Basics", "start_date": "2024", "end_date": ""}
    with_school = {"institution": "IHK Beispielstadt", "qualification": "Lean Management Basics",
                   "start_date": "", "end_date": ""}
    other = {"institution": "", "qualification": "Mittlere Reife", "start_date": "", "end_date": ""}
    assert clean([degree, again, with_school, other], certificates) == [degree, with_school, other]
    assert clean([again], []) == [again]


def test_a_period_given_to_the_day_is_kept_by_month() -> None:
    from core.cv_docpick_import import _norm_month_year, _norm_period_end

    assert _norm_month_year("15.07.2015") == "07/2015"
    assert _norm_month_year("01/08/2015") == "01/08/2015"     # day or month first: cannot be told
    assert _norm_month_year("2015-07-15") == "07/2015"
    assert _norm_period_end("28.02.2019") == "02/2019"
    assert _norm_month_year("07.2015") == "07/2015" and _norm_month_year("2015-07") == "07/2015"
    assert _norm_month_year("2015") == "2015"
    assert _norm_month_year("15.13.2015") == "15.13.2015"      # not a date: left as written


def test_a_tool_keeps_the_parts_the_document_lists_with_it() -> None:
    from core.cv_docpick_import import _software_as_listed as listed

    text = "EDV\n• MS Office (Word, Excel, Outlook)\n• SAP\n- DATEV (Grundlagen)\nSAP (FI) und SAP (MM)\n"
    assert listed(["MS Office", "SAP", "Datev"], text) == ["MS Office (Word, Excel, Outlook)", "SAP", "DATEV (Grundlagen)"]
    assert listed(["MS Office (Word)"], text) == ["MS Office (Word)"]          # already has a bracket
    assert listed(["MS Office"], "MS Office (Word)\nMS Office (Excel)\n") == ["MS Office"]   # two wordings: no choice
    assert listed(["Excel"], "") == ["Excel"]
