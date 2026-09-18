"""Source / place field normalization matrix (~100+ cases) for DACH PR24."""

from __future__ import annotations

import pytest

from core.geo_normalize import (
    dach_countries_for_intent,
    extract_country_hint,
    normalize_city_name,
    normalize_country_code,
    normalize_place_fields,
    normalize_postal_code,
    source_location_blob_to_fields,
)
from core.intent_filter import apply_search_intent, normalize_job_for_intent
from core.models import Job, RemoteType
from core.search_intent import SearchIntent, Strictness
from search.indeed import IndeedSource
from search.jsonld import job_from_job_posting, job_from_list_card


# ---------------------------------------------------------------------------
# Country aliases (~40)
# ---------------------------------------------------------------------------

_COUNTRY_CASES = [
    ("DE", "DE"),
    ("de", "DE"),
    ("Deu", "DE"),
    ("GER", "DE"),
    ("Germany", "DE"),
    ("germany", "DE"),
    ("Deutschland", "DE"),
    ("deutschland", "DE"),
    ("Bundesrepublik Deutschland", "DE"),
    ("Federal Republic of Germany", "DE"),
    ("(DE)", "DE"),
    ("DE,", "DE"),
    ("AT", "AT"),
    ("at", "AT"),
    ("AUT", "AT"),
    ("Austria", "AT"),
    ("austria", "AT"),
    ("Österreich", "AT"),
    ("österreich", "AT"),
    ("Oesterreich", "AT"),
    ("OsterreicH", "AT"),
    ("(AT)", "AT"),
    ("CH", "CH"),
    ("ch", "CH"),
    ("CHE", "CH"),
    ("Switzerland", "CH"),
    ("switzerland", "CH"),
    ("Schweiz", "CH"),
    ("schweiz", "CH"),
    ("Suisse", "CH"),
    ("Svizzera", "CH"),
    ("Swiss Confederation", "CH"),
    ("(CH)", "CH"),
    ("", ""),
    (None, ""),
    ("   ", ""),
    ("FR", ""),
    ("France", ""),
    ("IT", ""),
    ("US", ""),
    ("UK", ""),
    ("NL", ""),
    ("BE", ""),
    ("PL", ""),
    ("XYZ", ""),
]


@pytest.mark.parametrize("raw,iso", _COUNTRY_CASES)
def test_normalize_country_matrix(raw, iso):
    assert normalize_country_code(raw) == iso


# ---------------------------------------------------------------------------
# Location blob parsing (JobSpy / ATS style) (~30)
# ---------------------------------------------------------------------------

_BLOB_CASES = [
    ("Berlin, Germany", "Berlin", "DE"),
    ("München, Deutschland", "München", "DE"),
    ("Hamburg, DE", "Hamburg", "DE"),
    ("10115 Berlin", "10115 Berlin", "DE"),
    ("78462 Konstanz, Germany", "78462 Konstanz", "DE"),
    ("Konstanz, Baden-Württemberg, Germany", "Konstanz", "DE"),
    ("Wien, Österreich", "Wien", "AT"),
    ("Vienna, Austria", "Vienna", "AT"),
    ("1010 Wien, AT", "1010 Wien", "AT"),
    ("Salzburg, Austria", "Salzburg", "AT"),
    ("Bregenz, Österreich", "Bregenz", "AT"),
    ("Zürich, Schweiz", "Zürich", "CH"),
    ("Zurich, Switzerland", "Zurich", "CH"),
    ("Basel, CH", "Basel", "CH"),
    ("Genève, Suisse", "Genève", "CH"),
    ("Bern, Switzerland", "Bern", "CH"),
    ("Kreuzlingen, Switzerland", "Kreuzlingen", "CH"),
    ("Romanshorn 8590, Schweiz", "Romanshorn 8590", "CH"),
    ("Remote", "Remote", ""),
    ("Home Office", "Home Office", ""),
    ("", "", ""),
    ("Frankfurt am Main, Germany", "Frankfurt am Main", "DE"),
    ("Köln / Cologne, DE", "Köln / Cologne", "DE"),
    ("Düsseldorf, Germany", "Düsseldorf", "DE"),
    ("Innsbruck, AT", "Innsbruck", "AT"),
    ("Graz, Österreich", "Graz", "AT"),
    ("Lausanne, Switzerland", "Lausanne", "CH"),
    ("Lugano, Schweiz", "Lugano", "CH"),
    ("Passau, Deutschland", "Passau", "DE"),
    ("Schärding, Österreich", "Schärding", "AT"),
]


@pytest.mark.parametrize("blob,city_prefix,cc", _BLOB_CASES)
def test_source_location_blob_matrix(blob, city_prefix, cc):
    fields = source_location_blob_to_fields(blob)
    if city_prefix:
        assert fields["city"]
    assert fields["country_code"] == cc


# ---------------------------------------------------------------------------
# PLZ normalization
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "raw,country,expect_digits",
    [
        ("78462", "DE", "78462"),
        ("D-78462", "DE", "78462"),
        ("6900", "AT", "6900"),
        ("CH-8001", "CH", "8001"),
        ("", "DE", ""),
        ("abc", "DE", ""),
        ("123", "DE", "123"),
    ],
)
def test_normalize_postal(raw, country, expect_digits):
    assert normalize_postal_code(raw, country_code=country) == expect_digits


# ---------------------------------------------------------------------------
# Intent: cross-border country expansion + radius
# ---------------------------------------------------------------------------

def _job(**kwargs) -> Job:
    defaults = dict(
        id="j",
        source="test",
        source_job_id="1",
        title="Buchhalter/in",
        company="Firma",
        description="",
        remote_type=RemoteType.ONSITE.value,
    )
    defaults.update(kwargs)
    return Job(**defaults)


def test_intent_cross_border_allows_ch_near_de_home():
    intent = SearchIntent(
        target_roles=["Buchhalter"],
        countries=["DE"],
        radius_km=25.0,
        strictness=Strictness.BALANCED,
    )
    job = _job(
        title="Buchhalter",
        city="Kreuzlingen",
        country_code="CH",
        description="Standort Schweiz",
        distance_km=6.0,
    )
    r = apply_search_intent(job, intent, cross_border_dach=True, home_country="DE")
    assert r.included
    assert not r.excluded


def test_intent_cross_border_off_excludes_ch_when_hint_present():
    intent = SearchIntent(
        target_roles=["Buchhalter"],
        countries=["DE"],
        radius_km=25.0,
        strictness=Strictness.BALANCED,
    )
    job = _job(
        title="Buchhalter",
        city="Zürich",
        country_code="CH",
        description="Arbeit in der Schweiz (CH)",
        distance_km=6.0,
    )
    r = apply_search_intent(job, intent, cross_border_dach=False, home_country="DE")
    assert r.excluded


def test_intent_radius_excludes_far_at():
    intent = SearchIntent(
        target_roles=["Buchhalter"],
        countries=["DE", "AT", "CH"],
        radius_km=25.0,
        strictness=Strictness.BALANCED,
    )
    job = _job(
        title="Buchhalter",
        city="Innsbruck",
        country_code="AT",
        description="Österreich",
        distance_km=140.0,
    )
    r = apply_search_intent(job, intent, cross_border_dach=True)
    assert r.excluded


def test_intent_remote_ignores_radius():
    intent = SearchIntent(
        target_roles=["Buchhalter"],
        radius_km=5.0,
        strictness=Strictness.BALANCED,
    )
    job = _job(
        title="Buchhalter",
        remote_type=RemoteType.REMOTE.value,
        distance_km=None,
        description="100% Remote Deutschland",
    )
    r = apply_search_intent(job, intent, cross_border_dach=True)
    assert r.included


def test_dach_countries_for_intent_expansion():
    assert dach_countries_for_intent(
        ["DE"], cross_border_enabled=True, home_country="DE"
    ) == ["AT", "CH", "DE"]
    assert dach_countries_for_intent(
        ["DE"], cross_border_enabled=False, home_country="DE"
    ) == ["DE"]


# ---------------------------------------------------------------------------
# Indeed / JSON-LD source normalization
# ---------------------------------------------------------------------------

def test_indeed_normalize_sets_country_de():
    src = IndeedSource()
    row = {
        "title": "Sachbearbeiter",
        "company": "ACME",
        "location": "Konstanz, Germany",
        "job_url": "https://example.com/j/1",
        "description": "Büro",
        "is_remote": False,
    }
    job = src.normalize(row)
    assert job is not None
    assert job.country_code == "DE"
    assert "Konstanz" in job.city


def test_indeed_normalize_switzerland_token():
    src = IndeedSource()
    row = {
        "title": "Accountant",
        "company": "ACME",
        "location": "Basel, Switzerland",
        "job_url": "https://example.com/j/2",
        "description": "",
        "is_remote": False,
    }
    job = src.normalize(row)
    assert job is not None
    assert job.country_code == "CH"


def test_jsonld_address_country():
    item = {
        "@type": "JobPosting",
        "title": "Controller",
        "hiringOrganization": {"name": "Firm"},
        "url": "https://example.com/jobs/3",
        "jobLocation": {
            "address": {
                "addressLocality": "Salzburg",
                "postalCode": "5020",
                "addressCountry": "AT",
            }
        },
        "description": "Finance",
    }
    job = job_from_job_posting(item, source="stepstone")
    assert job is not None
    assert job.country_code == "AT"
    assert job.postal_code == "5020"
    assert job.city == "Salzburg"


def test_jsonld_list_card_schweiz():
    job = job_from_list_card(
        source="xing",
        title="Buchhalterin Finanzbuchhaltung",
        url="https://example.com/x/1",
        company="Co",
        city="Zürich, Schweiz",
    )
    assert job is not None
    assert job.country_code == "CH"


def test_normalize_job_for_intent_uses_country_code():
    job = _job(country_code="CH", description="keine landesworte")
    norm = normalize_job_for_intent(job)
    assert norm.country_hint == "CH"


# ---------------------------------------------------------------------------
# Extra city / unicode / place field cases to reach ~100
# ---------------------------------------------------------------------------

_CITY_CASES = [
    ("München", "München"),
    ("Zürich", "Zürich"),
    ("Genève", "Genève"),
    ("  Berlin  ", "Berlin"),
    ("Köln, Germany", "Köln"),
    ("Wien, Österreich", "Wien"),
    ("", ""),
]


@pytest.mark.parametrize("raw,expect", _CITY_CASES)
def test_normalize_city_matrix(raw, expect):
    assert normalize_city_name(raw) == expect


@pytest.mark.parametrize(
    "texts,expect",
    [
        (("Job in Deutschland",), "DE"),
        (("Standort Schweiz",), "CH"),
        (("Büro Österreich",), "AT"),
        (("Germany and Switzerland",), ""),  # conflicting
        (("",), ""),
        (("Konstanz, DE",), "DE"),
        (("(CH) Grenzregion",), "CH"),
    ],
)
def test_extract_country_hint_matrix(texts, expect):
    assert extract_country_hint(*texts) == expect


@pytest.mark.parametrize(
    "city,postal,country,expect_cc",
    [
        ("Konstanz", "78462", "DE", "DE"),
        ("Kreuzlingen", "", "CH", "CH"),
        ("Bregenz", "6900", "AT", "AT"),
        ("Lugano", "6900", "CH", "CH"),
        ("Berlin", "10115", "Germany", "DE"),
        ("Wien", "1010", "Austria", "AT"),
        ("Bern", "3011", "Switzerland", "CH"),
        ("Basel", "", "Suisse", "CH"),
        ("Passau", "", "Deutschland", "DE"),
        ("Schärding", "", "Österreich", "AT"),
    ],
)
def test_normalize_place_fields_matrix(city, postal, country, expect_cc):
    p = normalize_place_fields(city=city, postal_code=postal, country=country)
    assert p.country_code == expect_cc
    assert p.city


def test_place_fields_do_not_invent_coords():
    p = normalize_place_fields(city="Konstanz", country_code="DE")
    assert p.latitude is None
    assert p.longitude is None
