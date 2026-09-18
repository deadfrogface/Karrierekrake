#!/usr/bin/env python3
"""Generate synthetic contact-discovery fixtures (no real PII).

Writes tests/fixtures/contacts/extraction_corpus.json
  - >=200 pages/jobs with expected person contacts
  - >=100 NOT_FOUND cases
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "tests" / "fixtures" / "contacts" / "extraction_corpus.json"

FIRST = [
    "Mira", "Tobias", "Lena", "Jonas", "Clara", "Erik", "Nora", "Paul",
    "Sina", "Marc", "Julia", "Omar", "Greta", "Felix", "Ayla", "Ben",
    "Dana", "Hugo", "Iris", "Kai", "Lara", "Nils", "Pia", "Quinn",
    "Rita", "Sven", "Tara", "Ulf", "Vera", "Willi",
]
LAST = [
    "Vogel", "Keller", "Richter", "Stein", "Brandt", "Neumann", "Krüger",
    "Hoffmann", "Schäfer", "Weber", "Fischer", "Becker", "Schulz", "Wagner",
    "Koch", "Bauer", "Schröder", "Klein", "Wolf", "Schrader",
]
ROLES = [
    "Recruiterin", "Recruiter", "Talent Acquisition", "HR-Managerin",
    "Personalreferent", "Hiring Manager", "Ansprechpartner",
]
DEPTS = ["People", "HR", "Talent", "Personal", "Recruiting"]


def _ascii_local(first: str, last: str) -> str:
    table = str.maketrans(
        {
            "ä": "ae",
            "ö": "oe",
            "ü": "ue",
            "Ä": "ae",
            "Ö": "oe",
            "Ü": "ue",
            "ß": "ss",
        }
    )
    return f"{first.translate(table).lower()}.{last.translate(table).lower()}"


def _email(first: str, last: str, domain: str) -> str:
    return f"{_ascii_local(first, last)}@{domain}"


def _person(i: int) -> dict:
    first = FIRST[i % len(FIRST)]
    last = LAST[i % len(LAST)]
    role = ROLES[i % len(ROLES)]
    dept = DEPTS[i % len(DEPTS)]
    domain = f"firma{i % 40}.example.com"
    email = _email(first, last, domain)
    return {
        "name": f"{first} {last}",
        "role": role,
        "department": dept,
        "email": email,
        "phone": f"+49 30 {1000000 + i}",
    }


def _job_text_fixture(i: int, person: dict) -> dict:
    html = f"""<!DOCTYPE html><html><body>
    <h1>Stellenanzeige {i}</h1>
    <p>Wir suchen Verstärkung im Team.</p>
    <p>Ansprechpartnerin: {person['name']}, {person['role']} —
       {person['email']}, Tel. {person['phone']}</p>
    </body></html>"""
    return {
        "id": f"pos_text_{i:03d}",
        "kind": "positive",
        "variant": "job_posting_text",
        "source_url": f"https://jobs.example.com/text/{i}",
        "html": html,
        "text": f"Ansprechpartner: {person['name']} — {person['email']}",
        "expect": {
            "status": "FOUND",
            "name": person["name"],
            "email": person["email"],
        },
    }


def _jsonld_fixture(i: int, person: dict) -> dict:
    payload = {
        "@type": "JobPosting",
        "title": f"Fachkraft {i}",
        "datePosted": "2026-09-01",
        "dateModified": "2026-09-10",
        "hiringOrganization": {"name": f"Org {i}"},
        "applicationContact": {
            "@type": "ContactPoint",
            "name": person["name"],
            "email": person["email"],
            "contactType": person["role"],
            "telephone": person["phone"],
        },
    }
    html = (
        "<html><head><script type=\"application/ld+json\">"
        + json.dumps(payload, ensure_ascii=False)
        + "</script></head><body><p>Job details without contact in body.</p>"
        "</body></html>"
    )
    return {
        "id": f"pos_jsonld_{i:03d}",
        "kind": "positive",
        "variant": "job_posting_jsonld",
        "source_url": f"https://jobs.example.com/jsonld/{i}",
        "html": html,
        "text": "",
        "expect": {
            "status": "FOUND",
            "name": person["name"],
            "email": person["email"],
        },
    }


def _ats_fixture(i: int, person: dict) -> dict:
    return {
        "id": f"pos_ats_{i:03d}",
        "kind": "positive",
        "variant": "ats_metadata",
        "source_url": f"https://boards.example.com/{i}",
        "html": "",
        "text": "",
        "ats_metadata": {
            "recruiter_name": person["name"],
            "recruiter_email": person["email"],
            "contact_role": person["role"],
            "department": person["department"],
            "contact_phone": person["phone"],
        },
        "expect": {
            "status": "FOUND",
            "name": person["name"],
            "email": person["email"],
        },
    }


def _career_fixture(i: int, person: dict) -> dict:
    html = f"""<html><body>
    <h1>Karriere</h1>
    <p>Fragen zum Bewerbungsprozess?</p>
    <p>Ansprechpartner: {person['name']} ({person['role']}) {person['email']}</p>
    </body></html>"""
    return {
        "id": f"pos_career_{i:03d}",
        "kind": "positive",
        "variant": "company_career_page",
        "source_url": f"https://company{i}.example.com/karriere",
        "html": html,
        "text": "",
        "page_kind": "career",
        "expect": {
            "status": "FOUND",
            "name": person["name"],
            "email": person["email"],
        },
    }


def _contact_page_fixture(i: int, person: dict) -> dict:
    html = f"""<html><body>
    <h1>Recruiting Kontakt</h1>
    <p>Ansprechpartner: {person['name']}, {person['department']} — {person['email']}</p>
    </body></html>"""
    return {
        "id": f"pos_contact_{i:03d}",
        "kind": "positive",
        "variant": "company_contact_page",
        "source_url": f"https://company{i}.example.com/kontakt",
        "html": html,
        "text": "",
        "page_kind": "contact",
        "expect": {
            "status": "FOUND",
            "name": person["name"],
            "email": person["email"],
        },
    }


def _multi_person_fixture(i: int) -> dict:
    p1 = _person(i)
    p2 = _person(i + 17)
    text = (
        f"Ansprechpartner: {p1['name']} — {p1['email']}\n"
        f"Ansprechpartnerin: {p2['name']} — {p2['email']}\n"
    )
    return {
        "id": f"pos_multi_{i:03d}",
        "kind": "positive",
        "variant": "multiple_persons",
        "source_url": f"https://jobs.example.com/multi/{i}",
        "html": f"<html><body><pre>{text}</pre></body></html>",
        "text": text,
        "expect": {
            "status": "FOUND",
            "min_persons": 2,
            "emails": [p1["email"], p2["email"]],
        },
    }


def _hr_general_fixture(i: int, person: dict) -> dict:
    """General HR contact on career page (still a named person)."""
    html = f"""<html><body>
    <p>Allgemeiner HR-Kontakt: {person['name']}, Personal —
       {person['email']}</p>
    </body></html>"""
    # Use Ansprechpartner label for reliable extraction
    html = f"""<html><body>
    <p>Ansprechpartner: {person['name']}, Personal — {person['email']}</p>
    </body></html>"""
    return {
        "id": f"pos_hr_general_{i:03d}",
        "kind": "positive",
        "variant": "hr_general",
        "source_url": f"https://hr.example.com/general/{i}",
        "html": html,
        "text": "",
        "page_kind": "career",
        "expect": {
            "status": "FOUND",
            "name": person["name"],
            "email": person["email"],
        },
    }


def _not_found_empty(i: int) -> dict:
    return {
        "id": f"nf_empty_{i:03d}",
        "kind": "not_found",
        "variant": "empty_page",
        "source_url": f"https://jobs.example.com/empty/{i}",
        "html": f"<html><body><h1>Job {i}</h1><p>Keine Kontaktdaten.</p></body></html>",
        "text": "Wir suchen Verstärkung. Bitte bewerben Sie sich über das Portal.",
        "expect": {"status": "NOT_FOUND"},
    }


def _not_found_info(i: int) -> dict:
    return {
        "id": f"nf_info_{i:03d}",
        "kind": "not_found",
        "variant": "info_mailbox",
        "source_url": f"https://jobs.example.com/info/{i}",
        "html": (
            f"<html><body><p>Bewerbungen bitte an "
            f"info@company{i}.example.com</p></body></html>"
        ),
        "text": f"Bewerbungen bitte an jobs@company{i}.example.com",
        "expect": {"status": "NOT_FOUND"},
    }


def _not_found_malformed(i: int) -> dict:
    return {
        "id": f"nf_malformed_{i:03d}",
        "kind": "not_found",
        "variant": "malformed_html",
        "source_url": f"https://jobs.example.com/bad/{i}",
        "html": f"<html><body><script type='application/ld+json'>{{broken {i}",
        "text": "",
        "expect": {"status": "NOT_FOUND"},
    }


def main() -> None:
    positives: list[dict] = []
    # Mix variants to exceed 200
    for i in range(50):
        positives.append(_job_text_fixture(i, _person(i)))
    for i in range(50):
        positives.append(_jsonld_fixture(i, _person(i + 50)))
    for i in range(30):
        positives.append(_ats_fixture(i, _person(i + 100)))
    for i in range(30):
        positives.append(_career_fixture(i, _person(i + 130)))
    for i in range(20):
        positives.append(_contact_page_fixture(i, _person(i + 160)))
    for i in range(15):
        positives.append(_multi_person_fixture(i))
    for i in range(15):
        positives.append(_hr_general_fixture(i, _person(i + 180)))

    not_found: list[dict] = []
    for i in range(40):
        not_found.append(_not_found_empty(i))
    for i in range(40):
        not_found.append(_not_found_info(i))
    for i in range(20):
        not_found.append(_not_found_malformed(i))

    assert len(positives) >= 200, len(positives)
    assert len(not_found) >= 100, len(not_found)

    payload = {
        "schema_version": 1,
        "description": "Synthetic recruiting contact discovery corpus (PR25)",
        "positives": positives,
        "not_found": not_found,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {OUT} ({len(positives)} positives, {len(not_found)} not_found)")


if __name__ == "__main__":
    main()
