"""Synthetic personas — no real people / no real PII."""

from __future__ import annotations

from typing import Any

PERSONAS: dict[str, dict[str, Any]] = {
    "PERSONA_1": {
        "id": "PERSONA_1",
        "label": "Strong profile / complete CV",
        "profile": {
            "first_name": "Alex",
            "last_name": "Berger",
            "email": "alex.berger@example.com",
            "phone": "+49 30 0000001",
            "city": "Berlin",
            "country": "DE",
            "desired_role": "Lohnbuchhalter",
        },
        "search_intent": {
            "target_roles": ["Lohnbuchhalter", "Payroll Specialist"],
            "mandatory_skills": ["SAP"],
            "preferred_skills": ["DATEV"],
            "countries": ["DE"],
            "radius_km": 50,
            "remote_mode": "hybrid",
            "strictness": "strict",
            "salary_min": 45000,
        },
        "has_cv": True,
    },
    "PERSONA_2": {
        "id": "PERSONA_2",
        "label": "Sparse profile / missing information",
        "profile": {
            "first_name": "Sam",
            "last_name": "Klein",
            "email": "sam.klein@example.org",
            "city": "",
            "country": "DE",
            "desired_role": "",
        },
        "search_intent": {
            "target_roles": [],
            "countries": ["DE"],
            "strictness": "explore",
        },
        "has_cv": False,
    },
    "PERSONA_3": {
        "id": "PERSONA_3",
        "label": "Career changer",
        "profile": {
            "first_name": "Jordan",
            "last_name": "Vogel",
            "email": "jordan.vogel@example.net",
            "city": "Hamburg",
            "country": "DE",
            "desired_role": "Controller",
        },
        "search_intent": {
            "target_roles": ["Controller", "Junior Controller"],
            "mandatory_skills": [],
            "preferred_skills": ["Excel"],
            "excluded_skills": ["SAP FI"],
            "countries": ["DE", "AT"],
            "strictness": "balanced",
            "remote_mode": "remote",
        },
        "has_cv": True,
    },
    "PERSONA_4": {
        "id": "PERSONA_4",
        "label": "Long work history",
        "profile": {
            "first_name": "Morgan",
            "last_name": "Hartmann",
            "email": "morgan.hartmann@example.com",
            "city": "München",
            "country": "DE",
            "desired_role": "Head of Payroll",
        },
        "search_intent": {
            "target_roles": ["Head of Payroll", "Payroll Lead"],
            "mandatory_skills": ["SAP", "Leadership"],
            "countries": ["DE", "CH"],
            "radius_km": 80,
            "strictness": "strict",
            "salary_min": 80000,
        },
        "has_cv": True,
    },
    "PERSONA_5": {
        "id": "PERSONA_5",
        "label": "Recent qualification / training",
        "profile": {
            "first_name": "Riley",
            "last_name": "Neumann",
            "email": "riley.neumann@example.com",
            "city": "Leipzig",
            "country": "DE",
            "desired_role": "Buchhalter",
        },
        "search_intent": {
            "target_roles": ["Buchhalter", "Junior Accountant"],
            "preferred_skills": ["DATEV"],
            "countries": ["DE"],
            "strictness": "explore",
            "remote_mode": "onsite",
            "radius_km": 30,
        },
        "has_cv": True,
    },
    "PERSONA_6": {
        "id": "PERSONA_6",
        "label": "Multilingual profile",
        "profile": {
            "first_name": "Camille",
            "last_name": "Dubois",
            "email": "camille.dubois@example.com",
            "city": "Basel",
            "country": "CH",
            "desired_role": "Payroll Specialist",
        },
        "search_intent": {
            "target_roles": ["Payroll Specialist", "Lohnbuchhaltung"],
            "mandatory_skills": ["Französisch", "Deutsch"],
            "countries": ["CH", "DE", "AT"],
            "strictness": "balanced",
            "remote_mode": "hybrid",
        },
        "has_cv": True,
    },
    "PERSONA_7": {
        "id": "PERSONA_7",
        "label": "No CV / manual profile only",
        "profile": {
            "first_name": "Taylor",
            "last_name": "Brandt",
            "email": "taylor.brandt@example.com",
            "city": "Köln",
            "country": "DE",
            "desired_role": "Office Manager",
        },
        "search_intent": {
            "target_roles": ["Office Manager", "Teamassistenz"],
            "countries": ["DE"],
            "strictness": "balanced",
            "radius_km": 40,
        },
        "has_cv": False,
    },
    "PERSONA_8": {
        "id": "PERSONA_8",
        "label": "Malformed / problematic CV input",
        "profile": {
            "first_name": "Casey",
            "last_name": "Richter",
            "email": "casey.richter@example.com",
            "city": "Frankfurt",
            "country": "DE",
            "desired_role": "Sachbearbeiter",
        },
        "search_intent": {
            "target_roles": ["Sachbearbeiter"],
            "countries": ["DE"],
            "strictness": "explore",
        },
        "has_cv": False,
        "cv_problematic": True,
    },
}


def all_personas() -> list[dict[str, Any]]:
    return list(PERSONAS.values())


def get_persona(persona_id: str) -> dict[str, Any]:
    return PERSONAS[persona_id]
