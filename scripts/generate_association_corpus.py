#!/usr/bin/env python3
"""Generate synthetic competing-application association fixtures (no real PII).

Writes tests/fixtures/association/competing_application_corpus.json
  - >=250 association scenarios
  - Hard cases: same company, same title/two cities, holding/subsidiary,
    recruiting agency, Workday/generic ATS, forwarded, multi-thread,
    contradictory signals
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "tests" / "fixtures" / "association" / "competing_application_corpus.json"

COMPANIES = [
    ("Nordlicht", "nordlicht"),
    ("Fabrikam", "fabrikam"),
    ("Contoso", "contoso"),
    ("AlpineTech", "alpinetech"),
    ("Rheinwerk", "rheinwerk"),
    ("Ostwind", "ostwind"),
    ("Südwerk", "suedwerk"),
    ("Bergmann", "bergmann"),
    ("Küstenco", "kuestenco"),
    ("Talwerk", "talwerk"),
    ("Hafenwerk", "hafenwerk"),
    ("Stadtwerk", "stadtwerk"),
    ("Waldmann", "waldmann"),
    ("Flusswerk", "flusswerk"),
    ("Gipfel", "gipfel"),
]

ROLES = [
    "Buchhalter",
    "Controller",
    "Sachbearbeiter Verwaltung",
    "Teamassistenz",
    "Payroll Specialist",
    "HR Generalist",
    "IT-Administrator",
    "Projektmanager",
    "Einkäufer",
    "Disponent",
]

CITIES = [
    "Berlin",
    "München",
    "Hamburg",
    "Köln",
    "Frankfurt",
    "Stuttgart",
    "Düsseldorf",
    "Leipzig",
    "Dresden",
    "Hannover",
]

AGENCIES = [
    ("Hays", "hays"),
    ("SThree", "sthree"),
    ("Randstad", "randstad"),
    ("Adecco", "adecco"),
    ("Michael Page", "michaelpage"),
]

# Fictional ATS sender hosts under example.com (privacy-scan safe).
ATS_SENDERS = [
    ("Workday", "workday.example.com", "workday"),
    ("Greenhouse", "greenhouse.example.com", "greenhouse"),
    ("Lever", "lever.example.com", "lever"),
    ("SmartRecruiters", "smartrecruiters.example.com", "smartrecruiters"),
    ("Personio", "personio.example.com", "personio"),
]

HOLDINGS = [
    ("Alpine Holding AG", "AlpineTech GmbH", "alpinetech", "alpineholding"),
    ("Rhein Group SE", "Rheinwerk AG", "rheinwerk", "rheingroup"),
    ("Ostwind Parent GmbH", "Ostwind Logistics", "ostwind", "ostwindparent"),
]


def _case(
    cid: str,
    company: str,
    position: str,
    *,
    domain: str,
    city: str = "",
    contact_email: str = "",
    contact_name: str = "",
    reference: str = "",
    ats_application_id: str = "",
    thread_ids: list[str] | None = None,
    message_ids: list[str] | None = None,
    applied_at: str = "2026-08-01T10:00:00Z",
    status: str = "applied",
    url: str = "",
    parent_company: str = "",
) -> dict:
    email = contact_email or f"hr@{domain}.example.com"
    return {
        "id": cid,
        "company": company,
        "position": position,
        "status": status,
        "contact_email": email,
        "contact_name": contact_name,
        "location": city,
        "city": city,
        "reference": reference,
        "external_ref": reference,
        "ats_application_id": ats_application_id,
        "thread_ids": thread_ids or [],
        "message_ids": message_ids or [],
        "applied_at": applied_at,
        "url": url or f"https://jobs.{domain}.example.com/{cid}",
        "application_url": url or f"https://jobs.{domain}.example.com/{cid}",
        "parent_company": parent_company,
    }


def _scenario(
    sid: str,
    *,
    family: str,
    expect: str,
    expected_case_id: str | None,
    sender: str,
    subject: str,
    body: str,
    cases: list[dict],
    thread_id: str = "",
    message_id: str = "",
    ats_application_id: str = "",
    location_hint: str = "",
    is_forwarded: bool = False,
    notes: str = "",
) -> dict:
    return {
        "id": sid,
        "family": family,
        "expect": expect,  # linked | ambiguous | review_required | unlinked
        "expected_case_id": expected_case_id,
        "forbid_cross_case": True,
        "forbid_best_guess": True,
        "sender": sender,
        "subject": subject,
        "body": body,
        "thread_id": thread_id,
        "message_id": message_id,
        "ats_application_id": ats_application_id,
        "location_hint": location_hint,
        "is_forwarded": is_forwarded,
        "cases": cases,
        "notes": notes,
    }


def build() -> list[dict]:
    rows: list[dict] = []

    # --- Clear unique matches (linked) ---
    for i in range(60):
        co, slug = COMPANIES[i % len(COMPANIES)]
        role = ROLES[i % len(ROLES)]
        city = CITIES[i % len(CITIES)]
        cid = f"clear-{i:03d}"
        case = _case(
            cid,
            f"{co} GmbH",
            role,
            domain=slug,
            city=city,
            contact_email=f"hr@{slug}.example.com",
            contact_name=f"Alex Recruiter{i}",
            reference=f"REF-CL-{i:04d}",
        )
        rows.append(
            _scenario(
                f"assoc_clear_{i:03d}",
                family="clear_unique",
                expect="linked",
                expected_case_id=cid,
                sender=f"HR {co} <hr@{slug}.example.com>",
                subject=f"Ihre Bewerbung als {role} — {city}",
                body=(
                    f"Guten Tag,\n\nvielen Dank für Ihre Bewerbung als {role} "
                    f"bei {co} GmbH am Standort {city}.\n"
                    f"Referenz: REF-CL-{i:04d}\n"
                ),
                cases=[case],
            )
        )

    # --- Same company, two roles (ambiguous without unique signal) ---
    for i in range(35):
        co, slug = COMPANIES[i % len(COMPANIES)]
        r1 = ROLES[i % len(ROLES)]
        r2 = ROLES[(i + 3) % len(ROLES)]
        c1 = _case(f"sameco-a-{i:03d}", f"{co} GmbH", r1, domain=slug, city=CITIES[0])
        c2 = _case(f"sameco-b-{i:03d}", f"{co} GmbH", r2, domain=slug, city=CITIES[1])
        rows.append(
            _scenario(
                f"assoc_same_company_{i:03d}",
                family="same_company_two_roles",
                expect="ambiguous",
                expected_case_id=None,
                sender=f"People Team <noreply@{slug}.example.com>",
                subject="Update zu Ihrer Bewerbung",
                body="Wir melden uns bezüglich Ihrer Unterlagen.",
                cases=[c1, c2],
                notes="Two open applications at same employer; no role/ref unique signal",
            )
        )

    # --- Same title, two cities (ambiguous without location) ---
    for i in range(30):
        co, slug = COMPANIES[(i + 2) % len(COMPANIES)]
        role = ROLES[i % len(ROLES)]
        city_a = CITIES[i % len(CITIES)]
        city_b = CITIES[(i + 4) % len(CITIES)]
        c1 = _case(
            f"twocity-a-{i:03d}",
            f"{co} AG",
            role,
            domain=slug,
            city=city_a,
            reference=f"REF-TC-A-{i:04d}",
        )
        c2 = _case(
            f"twocity-b-{i:03d}",
            f"{co} AG",
            role,
            domain=slug,
            city=city_b,
            reference=f"REF-TC-B-{i:04d}",
        )
        rows.append(
            _scenario(
                f"assoc_same_title_two_cities_{i:03d}",
                family="same_title_two_cities",
                expect="ambiguous",
                expected_case_id=None,
                sender=f"Recruiting <jobs@{slug}.example.com>",
                subject=f"Ihre Bewerbung als {role}",
                body=f"Vielen Dank für Ihre Bewerbung als {role} bei {co} AG.",
                cases=[c1, c2],
            )
        )

    # --- Same title + unique city → linked ---
    for i in range(20):
        co, slug = COMPANIES[(i + 4) % len(COMPANIES)]
        role = ROLES[(i + 1) % len(ROLES)]
        city_a = CITIES[i % len(CITIES)]
        city_b = CITIES[(i + 5) % len(CITIES)]
        c1 = _case(
            f"citylink-a-{i:03d}",
            f"{co} GmbH",
            role,
            domain=slug,
            city=city_a,
        )
        c2 = _case(
            f"citylink-b-{i:03d}",
            f"{co} GmbH",
            role,
            domain=slug,
            city=city_b,
        )
        rows.append(
            _scenario(
                f"assoc_location_disambiguates_{i:03d}",
                family="location_disambiguates",
                expect="linked",
                expected_case_id=c1["id"],
                sender=f"HR <hr@{slug}.example.com>",
                subject=f"Einladung Interview {role} — Standort {city_a}",
                body=(
                    f"Wir laden Sie zum Gespräch für {role} in {city_a} ein.\n"
                    f"Standort: {city_a}\n"
                ),
                cases=[c1, c2],
                location_hint=city_a,
            )
        )

    # --- Holding / subsidiary ambiguity ---
    for i in range(18):
        parent, child, child_slug, parent_slug = HOLDINGS[i % len(HOLDINGS)]
        role = ROLES[i % len(ROLES)]
        c_child = _case(
            f"hold-child-{i:03d}",
            child,
            role,
            domain=child_slug,
            parent_company=parent,
        )
        c_parent = _case(
            f"hold-parent-{i:03d}",
            parent,
            role,
            domain=parent_slug,
            contact_email=f"group.hr@{parent_slug}.example.com",
        )
        rows.append(
            _scenario(
                f"assoc_holding_subsidiary_{i:03d}",
                family="holding_subsidiary",
                expect="ambiguous",
                expected_case_id=None,
                sender=f"Group Talent <noreply@{parent_slug}.example.com>",
                subject=f"Bewerbungsstatus {role}",
                body=(
                    f"Ihre Bewerbung im Verbund {parent} / {child} wird geprüft."
                ),
                cases=[c_child, c_parent],
            )
        )

    # --- Recruiting agency multi-case ---
    for i in range(25):
        agency, aslug = AGENCIES[i % len(AGENCIES)]
        co_a, slug_a = COMPANIES[i % len(COMPANIES)]
        co_b, slug_b = COMPANIES[(i + 5) % len(COMPANIES)]
        c1 = _case(
            f"agency-a-{i:03d}",
            f"{co_a} GmbH",
            ROLES[i % len(ROLES)],
            domain=slug_a,
            contact_email=f"consultant@{aslug}.example.com",
            contact_name=f"Consultant {agency}{i}",
        )
        c2 = _case(
            f"agency-b-{i:03d}",
            f"{co_b} AG",
            ROLES[(i + 2) % len(ROLES)],
            domain=slug_b,
            contact_email=f"consultant@{aslug}.example.com",
            contact_name=f"Consultant {agency}{i}",
        )
        rows.append(
            _scenario(
                f"assoc_agency_multi_{i:03d}",
                family="recruiting_agency",
                expect="ambiguous",
                expected_case_id=None,
                sender=f"{agency} Recruiting <noreply@{aslug}.example.com>",
                subject="Update zu Ihren Bewerbungsunterlagen",
                body="Wir haben Ihre Profile an Kunden weitergeleitet.",
                cases=[c1, c2],
            )
        )

    # --- Agency + unique client reference → linked ---
    for i in range(15):
        agency, aslug = AGENCIES[i % len(AGENCIES)]
        co, slug = COMPANIES[(i + 1) % len(COMPANIES)]
        role = ROLES[i % len(ROLES)]
        ref = f"REF-AG-{i:04d}"
        c1 = _case(
            f"agency-ref-a-{i:03d}",
            f"{co} GmbH",
            role,
            domain=slug,
            contact_email=f"desk@{aslug}.example.com",
            reference=ref,
        )
        c2 = _case(
            f"agency-ref-b-{i:03d}",
            f"{COMPANIES[(i + 7) % len(COMPANIES)][0]} AG",
            ROLES[(i + 4) % len(ROLES)],
            domain=COMPANIES[(i + 7) % len(COMPANIES)][1],
            contact_email=f"desk@{aslug}.example.com",
            reference=f"REF-AG-OTHER-{i:04d}",
        )
        rows.append(
            _scenario(
                f"assoc_agency_unique_ref_{i:03d}",
                family="agency_unique_ref",
                expect="linked",
                expected_case_id=c1["id"],
                sender=f"{agency} <noreply@{aslug}.example.com>",
                subject=f"Feedback {co} — {role}",
                body=f"Bezugnehmend auf Referenz {ref} bei {co} GmbH ({role}).",
                cases=[c1, c2],
            )
        )

    # --- Workday / generic ATS without unique ID → ambiguous ---
    for i in range(22):
        ats_name, ats_domain, ats_key = ATS_SENDERS[i % len(ATS_SENDERS)]
        co, slug = COMPANIES[i % len(COMPANIES)]
        role_a = ROLES[i % len(ROLES)]
        role_b = ROLES[(i + 2) % len(ROLES)]
        c1 = _case(
            f"ats-amb-a-{i:03d}",
            f"{co} GmbH",
            role_a,
            domain=slug,
            contact_email=f"noreply@{ats_domain}",
            ats_application_id=f"WD-A-{i:05d}",
        )
        c2 = _case(
            f"ats-amb-b-{i:03d}",
            f"{co} GmbH",
            role_b,
            domain=slug,
            contact_email=f"noreply@{ats_domain}",
            ats_application_id=f"WD-B-{i:05d}",
        )
        rows.append(
            _scenario(
                f"assoc_ats_generic_{i:03d}",
                family="generic_ats_sender",
                expect="ambiguous",
                expected_case_id=None,
                sender=f"{ats_name} <noreply@{ats_domain}>",
                subject="Application update",
                body=f"Your application at {co} GmbH is under review. Powered by {ats_name}.",
                cases=[c1, c2],
                notes=f"Generic {ats_key} sender without application id in mail",
            )
        )

    # --- ATS application ID unique → linked ---
    for i in range(20):
        ats_name, ats_domain, _ = ATS_SENDERS[i % len(ATS_SENDERS)]
        co, slug = COMPANIES[(i + 3) % len(COMPANIES)]
        aid = f"ATS-{i:06d}"
        c1 = _case(
            f"ats-id-a-{i:03d}",
            f"{co} GmbH",
            ROLES[i % len(ROLES)],
            domain=slug,
            contact_email=f"noreply@{ats_domain}",
            ats_application_id=aid,
        )
        c2 = _case(
            f"ats-id-b-{i:03d}",
            f"{co} GmbH",
            ROLES[(i + 1) % len(ROLES)],
            domain=slug,
            contact_email=f"noreply@{ats_domain}",
            ats_application_id=f"ATS-OTHER-{i:06d}",
        )
        rows.append(
            _scenario(
                f"assoc_ats_id_unique_{i:03d}",
                family="ats_application_id",
                expect="linked",
                expected_case_id=c1["id"],
                sender=f"{ats_name} Notifications <noreply@{ats_domain}>",
                subject="Application status changed",
                body=f"Application ID: {aid}\nCompany: {co} GmbH\nStatus: In review",
                cases=[c1, c2],
                ats_application_id=aid,
            )
        )

    # --- Exact thread reference → linked ---
    for i in range(18):
        co, slug = COMPANIES[i % len(COMPANIES)]
        tid = f"thread-{slug}-{i:04d}"
        c1 = _case(
            f"thread-a-{i:03d}",
            f"{co} GmbH",
            ROLES[i % len(ROLES)],
            domain=slug,
            thread_ids=[tid],
        )
        c2 = _case(
            f"thread-b-{i:03d}",
            f"{co} GmbH",
            ROLES[(i + 2) % len(ROLES)],
            domain=slug,
            thread_ids=[f"thread-other-{i:04d}"],
        )
        rows.append(
            _scenario(
                f"assoc_thread_exact_{i:03d}",
                family="exact_thread",
                expect="linked",
                expected_case_id=c1["id"],
                sender=f"HR <hr@{slug}.example.com>",
                subject="Fortsetzung unseres Gesprächs",
                body="Wie besprochen im bestehenden Thread.",
                cases=[c1, c2],
                thread_id=tid,
            )
        )

    # --- Multiple threads / no unique thread → ambiguous ---
    for i in range(12):
        co, slug = COMPANIES[(i + 1) % len(COMPANIES)]
        c1 = _case(
            f"multithread-a-{i:03d}",
            f"{co} AG",
            ROLES[i % len(ROLES)],
            domain=slug,
            thread_ids=[f"mt-a-{i}", f"mt-shared-{i}"],
        )
        c2 = _case(
            f"multithread-b-{i:03d}",
            f"{co} AG",
            ROLES[(i + 1) % len(ROLES)],
            domain=slug,
            thread_ids=[f"mt-b-{i}", f"mt-shared-{i}"],
        )
        rows.append(
            _scenario(
                f"assoc_multi_thread_{i:03d}",
                family="multiple_threads",
                expect="ambiguous",
                expected_case_id=None,
                sender=f"Recruiting <jobs@{slug}.example.com>",
                subject="Kurze Rückfrage",
                body="Kurze Frage zu Ihrer Bewerbung.",
                cases=[c1, c2],
                thread_id=f"mt-shared-{i}",
            )
        )

    # --- Forwarded mail with original employer signal ---
    for i in range(15):
        co, slug = COMPANIES[(i + 6) % len(COMPANIES)]
        role = ROLES[i % len(ROLES)]
        cid = f"fwd-{i:03d}"
        case = _case(cid, f"{co} GmbH", role, domain=slug, reference=f"REF-FWD-{i:04d}")
        decoy = _case(
            f"fwd-decoy-{i:03d}",
            f"{COMPANIES[(i + 2) % len(COMPANIES)][0]} AG",
            ROLES[(i + 3) % len(ROLES)],
            domain=COMPANIES[(i + 2) % len(COMPANIES)][1],
        )
        rows.append(
            _scenario(
                f"assoc_forwarded_{i:03d}",
                family="forwarded",
                expect="linked",
                expected_case_id=cid,
                sender="Max Mustermann <max.mustermann@applicant.example.com>",
                subject=f"WG: Ihre Bewerbung als {role} bei {co} GmbH",
                body=(
                    f"---------- Weitergeleitete Nachricht ----------\n"
                    f"Von: HR <hr@{slug}.example.com>\n"
                    f"Betreff: Ihre Bewerbung als {role}\n\n"
                    f"Referenz REF-FWD-{i:04d} — {co} GmbH\n"
                ),
                cases=[case, decoy],
                is_forwarded=True,
            )
        )

    # --- Contradictory signals → review_required / ambiguous ---
    for i in range(20):
        co_a, slug_a = COMPANIES[i % len(COMPANIES)]
        co_b, slug_b = COMPANIES[(i + 8) % len(COMPANIES)]
        c1 = _case(
            f"contra-a-{i:03d}",
            f"{co_a} GmbH",
            ROLES[i % len(ROLES)],
            domain=slug_a,
            reference=f"REF-CA-{i:04d}",
            contact_email=f"hr@{slug_a}.example.com",
        )
        c2 = _case(
            f"contra-b-{i:03d}",
            f"{co_b} GmbH",
            ROLES[(i + 1) % len(ROLES)],
            domain=slug_b,
            reference=f"REF-CB-{i:04d}",
            contact_email=f"hr@{slug_b}.example.com",
        )
        rows.append(
            _scenario(
                f"assoc_contradictory_{i:03d}",
                family="contradictory_signals",
                expect="ambiguous",
                expected_case_id=None,
                sender=f"HR <hr@{slug_a}.example.com>",
                subject=f"Update {co_b} GmbH",
                body=(
                    f"Sender domain gehört zu {co_a}, Betreff nennt {co_b}. "
                    f"Referenz REF-CB-{i:04d} widerspricht dem Absender."
                ),
                cases=[c1, c2],
                notes="Domain vs subject/ref conflict → fail closed",
            )
        )

    # --- Same company unique title → linked ---
    for i in range(20):
        co, slug = COMPANIES[(i + 3) % len(COMPANIES)]
        r1 = ROLES[i % len(ROLES)]
        r2 = ROLES[(i + 5) % len(ROLES)]
        c1 = _case(f"uniqrole-a-{i:03d}", f"{co} GmbH", r1, domain=slug)
        c2 = _case(f"uniqrole-b-{i:03d}", f"{co} GmbH", r2, domain=slug)
        rows.append(
            _scenario(
                f"assoc_unique_role_{i:03d}",
                family="unique_role_same_company",
                expect="linked",
                expected_case_id=c1["id"],
                sender=f"HR <hr@{slug}.example.com>",
                subject=f"Einladung: {r1}",
                body=f"Wir möchten Sie zum Interview für die Stelle {r1} einladen.",
                cases=[c1, c2],
            )
        )

    # --- Message-ID exact → linked ---
    for i in range(12):
        co, slug = COMPANIES[i % len(COMPANIES)]
        mid = f"<msg-{i:04d}@{slug}.example.com>"
        c1 = _case(
            f"msgid-a-{i:03d}",
            f"{co} GmbH",
            ROLES[i % len(ROLES)],
            domain=slug,
            message_ids=[mid],
        )
        c2 = _case(
            f"msgid-b-{i:03d}",
            f"{co} GmbH",
            ROLES[(i + 1) % len(ROLES)],
            domain=slug,
            message_ids=[f"<other-{i}@x.example.com>"],
        )
        rows.append(
            _scenario(
                f"assoc_message_id_{i:03d}",
                family="exact_message_id",
                expect="linked",
                expected_case_id=c1["id"],
                sender=f"HR <hr@{slug}.example.com>",
                subject="In-Reply continuation",
                body="Fortsetzung",
                cases=[c1, c2],
                message_id=mid,
            )
        )

    # --- Empty / no signal with multiple cases → ambiguous ---
    for i in range(10):
        co, slug = COMPANIES[i % len(COMPANIES)]
        c1 = _case(f"empty-a-{i:03d}", f"{co} GmbH", ROLES[0], domain=slug)
        c2 = _case(f"empty-b-{i:03d}", f"{co} GmbH", ROLES[1], domain=slug)
        rows.append(
            _scenario(
                f"assoc_empty_content_{i:03d}",
                family="malformed_empty",
                expect="ambiguous",
                expected_case_id=None,
                sender=f"noreply@{slug}.example.com",
                subject="",
                body="",
                cases=[c1, c2],
            )
        )

    assert len(rows) >= 250, len(rows)
    return rows


def main() -> None:
    rows = build()
    families: dict[str, int] = {}
    for r in rows:
        families[r["family"]] = families.get(r["family"], 0) + 1
    payload = {
        "meta": {
            "version": 1,
            "synthetic": True,
            "pii": False,
            "count": len(rows),
            "families": families,
            "description": (
                "Competing ApplicationCase association corpus for PR29. "
                "All names/domains fictional (*.example.com)."
            ),
        },
        "scenarios": rows,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(rows)} scenarios → {OUT.relative_to(ROOT)}")
    for k, v in sorted(families.items()):
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
