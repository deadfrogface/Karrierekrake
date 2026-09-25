#!/usr/bin/env python3
"""Build a NEW independent DE/EN blind corpus (never used in Round2/3).

Creates PDFs + full V3 GT under tests/docpick_blind_de_en_v1/.
Does NOT run extraction. Phase A extract must happen with GT sealed away.
"""

from __future__ import annotations

import json
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "tests" / "docpick_blind_de_en_v1"
PDF_DIR = OUT / "phase_a_pdfs"
GT_DIR = OUT / "phase_b_solutions"


def _pdf(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(path), pagesize=A4)
    width, height = A4
    y = height - 50
    c.setFont("Helvetica", 11)
    for line in lines:
        if y < 50:
            c.showPage()
            c.setFont("Helvetica", 11)
            y = height - 50
        c.drawString(50, y, line[:110])
        y -= 16
    c.save()


DOCS = [
    {
        "id": "BL_DE_01",
        "lang": "de",
        "lines": [
            "Jonas Feldmann",
            "Kastanienallee 14, 10435 Berlin",
            "jonas.feldmann@example.com",
            "+49 176 5550123",
            "Geburtsdatum: 03.04.1988",
            "",
            "Berufserfahrung",
            "03/2018 – heute",
            "Logistikkoordinator",
            "Nordhafen Logistik AG, Berlin",
            "- Tourenplanung und Speditionsabstimmung",
            "",
            "08/2014 – 02/2018",
            "Disponent",
            "Spree Fracht GmbH, Potsdam",
            "",
            "Ausbildung",
            "08/2011 – 07/2014",
            "Kaufmann fuer Spedition und Logistikdienstleistung (IHK)",
            "OSZ Handel 1 / Spree Fracht GmbH",
            "",
            "Sprachen",
            "Deutsch – Muttersprache",
            "Englisch – B2",
            "Polnisch – A2",
            "",
            "Fuehrerschein: B, BE",
            "",
            "EDV",
            "SAP TM",
            "Microsoft Excel",
            "Transporeon",
            "",
            "Kenntnisse",
            "Disposition",
            "Kundenkommunikation",
            "",
            "Zertifikate",
            "ADR-Basiskurs 2019",
        ],
        "gt": {
            "language": "de",
            "name": {"first_name": "Jonas", "last_name": "Feldmann"},
            "email": "jonas.feldmann@example.com",
            "phone": "+49 176 5550123",
            "dob": "03.04.1988",
            "address": {
                "street": "Kastanienallee",
                "house_number": "14",
                "postal_code": "10435",
                "city": "Berlin",
                "country": "Deutschland",
            },
            "languages": [["Deutsch", "Muttersprache"], ["Englisch", "B2"], ["Polnisch", "A2"]],
            "licenses": ["B", "BE"],
            "employment": [
                {
                    "company": "Nordhafen Logistik AG",
                    "position": "Logistikkoordinator",
                    "start_date": "03/2018",
                    "end_date": "heute",
                },
                {
                    "company": "Spree Fracht GmbH",
                    "position": "Disponent",
                    "start_date": "08/2014",
                    "end_date": "02/2018",
                },
            ],
            "education": [
                {
                    "institution": "OSZ Handel 1 / Spree Fracht GmbH",
                    "qualification": "Kaufmann fuer Spedition und Logistikdienstleistung (IHK)",
                    "start_date": "08/2011",
                    "end_date": "07/2014",
                }
            ],
            "skills": ["Disposition", "Kundenkommunikation"],
            "software": ["SAP TM", "Microsoft Excel", "Transporeon"],
            "certificates": ["ADR-Basiskurs 2019"],
            "work_count": 2,
            "education_count": 1,
            "missing": [],
        },
    },
    {
        "id": "BL_DE_02",
        "lang": "de",
        "lines": [
            "Nora Weiss",
            "Am Sportpark 7, 80339 Muenchen",
            "nora.weiss@example.org",
            "+49 89 4442211",
            "Geburtsdatum: 19.11.1995",
            "",
            "Berufserfahrung",
            "01/2021 – heute",
            "Laborantin",
            "Isar Diagnostik GmbH, Muenchen",
            "",
            "Ausbildung",
            "09/2017 – 08/2020",
            "Biologisch-technische Assistentin",
            "Berufsfachschule Muenchen",
            "",
            "Sprachen",
            "Deutsch C2",
            "Englisch B1",
            "",
            "Software",
            "LIMS",
            "GraphPad Prism",
            "",
            "Kenntnisse",
            "Probenvorbereitung",
            "Qualitaetskontrolle",
        ],
        "gt": {
            "language": "de",
            "name": {"first_name": "Nora", "last_name": "Weiss"},
            "email": "nora.weiss@example.org",
            "phone": "+49 89 4442211",
            "dob": "19.11.1995",
            "address": {
                "street": "Am Sportpark",
                "house_number": "7",
                "postal_code": "80339",
                "city": "Muenchen",
                "country": "Deutschland",
            },
            "languages": [["Deutsch", "C2"], ["Englisch", "B1"]],
            "licenses": [],
            "employment": [
                {
                    "company": "Isar Diagnostik GmbH",
                    "position": "Laborantin",
                    "start_date": "01/2021",
                    "end_date": "heute",
                }
            ],
            "education": [
                {
                    "institution": "Berufsfachschule Muenchen",
                    "qualification": "Biologisch-technische Assistentin",
                    "start_date": "09/2017",
                    "end_date": "08/2020",
                }
            ],
            "skills": ["Probenvorbereitung", "Qualitaetskontrolle"],
            "software": ["LIMS", "GraphPad Prism"],
            "certificates": [],
            "work_count": 1,
            "education_count": 1,
            "missing": ["licenses", "certificates"],
        },
    },
    {
        "id": "BL_EN_01",
        "lang": "en",
        "lines": [
            "Emily Carter",
            "42 Willow Road, Manchester M1 2AB, United Kingdom",
            "emily.carter@example.com",
            "+44 7700 900123",
            "Date of birth: 12.07.1991",
            "",
            "Work Experience",
            "06/2019 – Present",
            "Product Analyst",
            "Northern Apps Ltd, Manchester",
            "",
            "02/2016 – 05/2019",
            "Junior Analyst",
            "Pennine Data Co, Leeds",
            "",
            "Education",
            "09/2012 – 06/2015",
            "BSc Business Analytics",
            "University of Leeds",
            "",
            "Languages",
            "English – Native",
            "German – B1",
            "",
            "Software",
            "SQL",
            "Tableau",
            "Python",
            "",
            "Skills",
            "Requirements gathering",
            "Stakeholder reporting",
            "",
            "Certificates",
            "ISTQB Foundation 2018",
        ],
        "gt": {
            "language": "en",
            "name": {"first_name": "Emily", "last_name": "Carter"},
            "email": "emily.carter@example.com",
            "phone": "+44 7700 900123",
            "dob": "12.07.1991",
            "address": {
                "street": "Willow Road",
                "house_number": "42",
                "postal_code": "M1 2AB",
                "city": "Manchester",
                "country": "United Kingdom",
            },
            "languages": [["English", "Native"], ["German", "B1"]],
            "licenses": [],
            "employment": [
                {
                    "company": "Northern Apps Ltd",
                    "position": "Product Analyst",
                    "start_date": "06/2019",
                    "end_date": "heute",
                },
                {
                    "company": "Pennine Data Co",
                    "position": "Junior Analyst",
                    "start_date": "02/2016",
                    "end_date": "05/2019",
                },
            ],
            "education": [
                {
                    "institution": "University of Leeds",
                    "qualification": "BSc Business Analytics",
                    "start_date": "09/2012",
                    "end_date": "06/2015",
                }
            ],
            "skills": ["Requirements gathering", "Stakeholder reporting"],
            "software": ["SQL", "Tableau", "Python"],
            "certificates": ["ISTQB Foundation 2018"],
            "work_count": 2,
            "education_count": 1,
            "missing": ["licenses"],
        },
    },
    {
        "id": "BL_EN_02",
        "lang": "en",
        "lines": [
            "Daniel Okoro",
            "18 Harbour Street, Dublin D02 XY45, Ireland",
            "daniel.okoro@example.net",
            "+353 85 1234567",
            "Date of birth: 28.02.1987",
            "",
            "Experience",
            "11/2017 – Present",
            "Facilities Supervisor",
            "GreenYard Facilities, Dublin",
            "",
            "Education",
            "09/2006 – 06/2010",
            "Diploma in Building Services",
            "TU Dublin",
            "",
            "Languages",
            "English C2",
            "French A2",
            "",
            "Driving licence: B",
            "",
            "Tools",
            "Maximo",
            "MS Outlook",
            "",
            "Skills",
            "Vendor management",
            "Health and safety coordination",
        ],
        "gt": {
            "language": "en",
            "name": {"first_name": "Daniel", "last_name": "Okoro"},
            "email": "daniel.okoro@example.net",
            "phone": "+353 85 1234567",
            "dob": "28.02.1987",
            "address": {
                "street": "Harbour Street",
                "house_number": "18",
                "postal_code": "D02 XY45",
                "city": "Dublin",
                "country": "Ireland",
            },
            "languages": [["English", "C2"], ["French", "A2"]],
            "licenses": ["B"],
            "employment": [
                {
                    "company": "GreenYard Facilities",
                    "position": "Facilities Supervisor",
                    "start_date": "11/2017",
                    "end_date": "heute",
                }
            ],
            "education": [
                {
                    "institution": "TU Dublin",
                    "qualification": "Diploma in Building Services",
                    "start_date": "09/2006",
                    "end_date": "06/2010",
                }
            ],
            "skills": ["Vendor management", "Health and safety coordination"],
            "software": ["Maximo", "MS Outlook"],
            "certificates": [],
            "work_count": 1,
            "education_count": 1,
            "missing": ["certificates"],
        },
    },
]


def main() -> int:
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    GT_DIR.mkdir(parents=True, exist_ok=True)
    documents = {}
    manifest_docs = []
    for d in DOCS:
        pdf_name = f"{d['id']}.pdf"
        pdf_path = PDF_DIR / pdf_name
        _pdf(pdf_path, d["lines"])
        documents[pdf_name] = d["gt"]
        manifest_docs.append(
            {
                "id": d["id"],
                "lang": d["lang"],
                "path": str(pdf_path.relative_to(ROOT)),
                "corpus_id": "DOCPICK_BLIND_DE_EN_V1",
            }
        )
    gt = {
        "schema_version": "karrierekrake_cv_gt_full_v3",
        "corpus_id": "DOCPICK_BLIND_DE_EN_V1",
        "disclaimer": (
            "NEW independent synthetic DE/EN CVs authored 2026-09-24 for Docpick blind. "
            "Not used in Round2/Round3 development. Small n=4 — not a large-scale proof."
        ),
        "documents": documents,
    }
    (GT_DIR / "expected_results_full_v3.json").write_text(
        json.dumps(gt, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    # Phase-A manifest must NOT embed GT — only PDF paths
    manifest = {
        "id": "DOCPICK_BLIND_DE_EN_V1",
        "locked": True,
        "gt_not_loaded": True,
        "documents": manifest_docs,
    }
    (OUT / "EXTRACTION_MANIFEST_PDF_ONLY.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    (OUT / "README.md").write_text(
        "# Docpick Blind DE/EN v1\n\n"
        "Independent synthetic corpus (2 DE + 2 EN). Protocol:\n"
        "1. Freeze parser/prompt/model\n"
        "2. Run sealed extract (PDF only) → frozen_predictions + seal\n"
        "3. Only then load phase_b_solutions and score V3.1\n"
        "4. Label as BLIND — not Round2/3\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(DOCS)} PDFs + GT under {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
