"""Schema-Prüfung für das Personaler-Gold der Anschreiben.

Dieser Test lädt kein Modell und keine Qt-Oberfläche. Er prüft nur,
ob die Fälle unter ``tests/fixtures/anschreiben_gold/`` vollständig und
in sich stimmig sind.

Der Vergleich Generator gegen Gold — Brief erzeugen und gegen
``expected_outcome``, ``must_mention`` und ``must_not_contain`` halten —
gehört in den Anschreiben-PR. Diese Datei implementiert ihn bewusst nicht.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "anschreiben_gold"
DOC = ROOT / "docs" / "personaler" / "ANSCHREIBEN_GOLD.md"

ALLOWED_OUTCOMES = frozenset(
    {
        "interview",
        "papierkorb",
        "job_incomplete",
        "no_evidence",
        "blocked_demo",
    }
)

# Beide Sätze sind in jedem Brief verboten, auch als einzige Begründung.
PHRASE_EXPERIENCE = (
    "Gern bringe ich meine bisherigen beruflichen Erfahrungen in Ihr Team ein."
)
PHRASE_SKILLS = (
    "Zu meinen relevanten Kenntnissen zählen insbesondere: "
    "meine bisherigen beruflichen Erfahrungen."
)
PLACEHOLDERS = (PHRASE_EXPERIENCE, PHRASE_SKILLS)

REQUIRED_KEYS = frozenset(
    {
        "schema_version",
        "id",
        "tags",
        "profile",
        "job",
        "expected_outcome",
        "must_mention",
        "must_not_contain",
        "rationale",
    }
)

REQUIRED_TAGS = frozenset(
    {
        "logistics_match",
        "empty_description",
        "zero_overlap",
        "demo_source",
        "fixture_source",
        "education_misfiled",
        "missing_credential",
        "company_invalid",
        "named_contact",
        "english_ad",
        "long_ad",
        "html_remnants",
    }
)

QUALIFICATION_KEYS = frozenset(
    {
        "education",
        "work_experience",
        "skills",
        "software",
        "driving_license",
        "languages",
        "certificates",
    }
)

JOB_KEYS = frozenset(
    {
        "id",
        "source",
        "title",
        "company",
        "description",
        "city",
        "status",
    }
)

EMAIL_RE = re.compile(
    r"[A-Za-z0-9._%+\-]+@([A-Za-z0-9.\-]+\.[A-Za-z]{2,})"
)
ALLOWED_EMAIL_DOMAINS = frozenset({"example.com", "example.org", "example.net"})


def _load_cases() -> list[dict]:
    paths = sorted(FIXTURES.glob("*.json"))
    assert paths, f"no gold fixtures in {FIXTURES}"
    cases = []
    for path in paths:
        data = json.loads(path.read_text(encoding="utf-8"))
        data["_path"] = path
        cases.append(data)
    return cases


def _texts(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return "\n".join(_texts(item) for item in value.values())
    if isinstance(value, list):
        return "\n".join(_texts(item) for item in value)
    return ""


CASES = _load_cases()


@pytest.fixture(scope="module")
def cases() -> list[dict]:
    return CASES


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["id"])
def test_gold_case_schema(case: dict) -> None:
    missing = REQUIRED_KEYS - set(case)
    assert not missing, f"{case.get('id')}: missing {sorted(missing)}"
    assert case["schema_version"] == "1.0"
    assert case["id"] == case["_path"].stem
    assert case["expected_outcome"] in ALLOWED_OUTCOMES
    assert isinstance(case["rationale"], str) and len(case["rationale"].strip()) >= 40
    assert case["tags"] and set(case["tags"]) <= REQUIRED_TAGS

    for phrase in PLACEHOLDERS:
        assert phrase in case["must_not_contain"], case["id"]

    assert isinstance(case["must_mention"], list)
    assert isinstance(case["must_not_contain"], list)
    assert all(isinstance(item, str) and item.strip() for item in case["must_mention"])
    assert all(isinstance(item, str) and item.strip() for item in case["must_not_contain"])

    profile = case["profile"]
    application = profile["application"]
    assert application["first_name"].strip()
    assert application["last_name"].strip()
    assert application["email"].strip()

    qualifications = profile["qualifications"]
    assert QUALIFICATION_KEYS <= set(qualifications)
    for key in QUALIFICATION_KEYS:
        assert isinstance(qualifications[key], list), key

    job = case["job"]
    assert JOB_KEYS <= set(job)
    assert isinstance(job["title"], str) and job["title"].strip()
    assert isinstance(job["company"], str)
    assert isinstance(job["description"], str)
    assert isinstance(job["source"], str) and job["source"].strip()
    assert job["status"] == "new"

    blob = _texts(profile) + "\n" + _texts(job)
    for phrase in PLACEHOLDERS:
        assert phrase not in blob, case["id"]
    for domain in {match.group(1).lower() for match in EMAIL_RE.finditer(blob)}:
        assert domain in ALLOWED_EMAIL_DOMAINS, case["id"]

    for fact in case["must_mention"]:
        assert fact in blob, f"{case['id']}: must_mention {fact!r} not in profile or job"

    outcome = case["expected_outcome"]
    if outcome == "interview":
        assert len(case["must_mention"]) >= 2, case["id"]
        qual_blob = _texts(qualifications)
        linked = [fact for fact in case["must_mention"] if fact in qual_blob]
        assert len(linked) >= 2, f"{case['id']}: fewer than two profile facts in must_mention"
        assert job["company"].strip()
        assert job["description"].strip()
    else:
        assert case["must_mention"] == [], case["id"]


def test_corpus_covers_outcomes_and_scenarios(cases: list[dict]) -> None:
    assert len(cases) >= 12
    ids = [case["id"] for case in cases]
    assert len(ids) == len(set(ids))
    assert {case["expected_outcome"] for case in cases} == ALLOWED_OUTCOMES
    tags = [tag for case in cases for tag in case["tags"]]
    assert set(tags) == REQUIRED_TAGS
    assert len(tags) == len(REQUIRED_TAGS)


def test_scenario_shapes(cases: list[dict]) -> None:
    by_tag = {case["tags"][0]: case for case in cases}

    logistics = by_tag["logistics_match"]
    assert logistics["expected_outcome"] == "interview"
    assert logistics["job"]["company"] == "HafenLogistik GmbH"
    assert "Dispatcher" in logistics["job"]["title"]

    empty = by_tag["empty_description"]
    assert empty["expected_outcome"] == "job_incomplete"
    assert empty["job"]["description"].strip() == ""
    assert empty["job"]["title"] == "Dispatcher"
    assert empty["job"]["company"] == "HafenLogistik"

    overlap = by_tag["zero_overlap"]
    assert overlap["expected_outcome"] == "no_evidence"
    assert overlap["job"]["description"].strip()
    assert "Konditor" in overlap["job"]["title"]

    demo = by_tag["demo_source"]
    assert demo["expected_outcome"] == "blocked_demo"
    assert demo["job"]["source"] == "demo"
    assert demo["job"]["description"].strip()

    fixture = by_tag["fixture_source"]
    assert fixture["expected_outcome"] == "interview"
    assert fixture["job"]["source"] == "fixture"

    education = by_tag["education_misfiled"]
    assert education["expected_outcome"] == "papierkorb"
    quals = education["profile"]["qualifications"]
    assert quals["education"] == []
    titles = [entry["title"] for entry in quals["work_experience"]]
    assert any(title.lower().startswith("ausbildung") for title in titles)

    trap = by_tag["missing_credential"]
    assert trap["expected_outcome"] == "interview"
    assert "ADR-Schein" in trap["job"]["description"]
    assert "ADR-Schein" in trap["must_not_contain"]
    assert "ADR-Schein" not in _texts(trap["profile"])

    company = by_tag["company_invalid"]
    assert company["expected_outcome"] == "papierkorb"
    assert company["job"]["company"].strip() == ""
    assert company["job"]["description"].strip()
    assert "Firma 0" in company["job"]["description"]
    assert "Firma 0" in company["must_not_contain"]
    assert "Ihr Unternehmen" in company["must_not_contain"]

    contact = by_tag["named_contact"]
    assert contact["expected_outcome"] == "interview"
    assert "Lotte Quendel" in contact["job"]["description"]
    assert "Lotte Quendel" in contact["must_mention"]

    english = by_tag["english_ad"]
    assert english["expected_outcome"] == "interview"
    assert "Requirements:" in english["job"]["description"]
    assert "Das bringen Sie mit:" not in english["job"]["description"]

    long_ad = by_tag["long_ad"]
    description = long_ad["job"]["description"]
    assert long_ad["expected_outcome"] == "interview"
    assert len(description) >= 2500
    marker = description.index("Das bringen Sie mit:")
    assert marker > len(description) * 0.55
    assert description.index("Tourenplanung") > marker
    assert description.index("SAP TM") > marker

    html = by_tag["html_remnants"]
    body = html["job"]["description"]
    assert html["expected_outcome"] == "interview"
    assert "<p>" in body and "&nbsp;" in body
    assert "<p>" in html["must_not_contain"]
    assert "&nbsp;" in html["must_not_contain"]


def test_doc_names_every_case(cases: list[dict]) -> None:
    text = DOC.read_text(encoding="utf-8")
    for case in cases:
        assert case["id"] in text, case["id"]
    for outcome in ALLOWED_OUTCOMES:
        assert f"`{outcome}`" in text
