#!/usr/bin/env python3
"""Freeze writing-quality fixtures (dev + final blind + interview) with SHA256."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "benchmark" / "corpus" / "guenther_writing_quality_final_fixtures.json"


def _case(cid, role, company, profile, job_extra="", *, hard_block=False, unknown_co=False, similar_trap=False):
    co = "" if unknown_co else company
    job = f"{role} (m/w/d)\n"
    if co:
        job += f"{co}\n"
    job += job_extra or f"Anforderungen: siehe Profil-Schnittmenge.\n"
    if hard_block:
        job += "Pflicht: abgeschlossene formelle Fachkraft-Ausbildung XYZ (Hard).\n"
    return {
        "id": cid,
        "profile": profile,
        "job": job,
        "target_company": co or "Unknown",
        "forbid_role_reversal": True,
        "forbid_wrong_role": [],
        "expect_hard_block": hard_block,
        "unknown_company": unknown_co,
        "similar_company_trap": similar_trap,
        "role": role,
    }


def build_dev() -> list[dict]:
    cases = []
    templates = [
        ("Sachbearbeiter", "Nordlicht Verwaltung GmbH", "Lea Admin\nBürokauffrau IHK 2019\nDATEV, Excel, Korrespondenz", "strong"),
        ("IT-Support", "Pixelwerk IT AG", "Tom Support\nWindows, Tickets, Active Directory Grundlagen", "medium"),
        ("Lagerist", "LogiTrans SE", "Sam Lager\nKommissionierung, WMS, Staplerschein 2020", "strong"),
        ("Kundenberater", "TelCo Plus AG", "Nina Service\nInbound-Telefonie, CRM, Deutsch C1", "strong"),
        ("Buchhalter", "FinanzNest AG", "Omar Finance\nKreditorenbuchhaltung, Excel — kein DATEV", "desirable_gap"),
        ("Pflegehelfer", "Sonnenklinik GmbH", "Rita Care\nGrundpflege Kurs, Dokumentation — keine Pflegeausbildung", "hard_gap"),
        ("Verkäufer", "Modehaus Weber", "Kai Retail\nKasse, Beratung, Einzelhandel 3 Jahre", "strong"),
        ("HR Assistant", "PeopleFirst KG", "Mira HR\nOnboarding, Recruiting-Support, Excel", "medium"),
        ("DevOps", "CloudNine GmbH", "Alex Ops\nLinux Admin, Docker Grundlagen — kein Zertifikat", "related"),
        ("Controller", "Industrie Holding SE", "Sven Control\nReporting, Excel, Kostenstellen", "strong"),
        ("Disponent", "SpedLog KG", "Ute Logistik\nTourenplanung, Telefon, Disposition", "strong"),
        ("Marketing", "BrandWave SE", "Paul Market\nSocial Media, Content — Quereinsteiger aus Journalismus", "career"),
        ("Elektroniker", "EnergiePlus GmbH", "Ben Electro\nSchaltschrank, Wartung, Ausbildung Elektroniker", "strong"),
        ("Recruiter", "TalentHub", "Clara Talent\nActive Sourcing, LinkedIn — kein Personio", "desirable_gap"),
        ("Facility", "GebäudeService Nord", "Dirk Facility\nInstandhaltung, SLA, Handwerkserfahrung", "medium"),
        ("Unknown role", "", "Eva Sparse\nOffice, Excel", "unknown_co"),
        ("Analyst", "Northwind Analytics GmbH", "Finn Data\nSQL, Reporting — vorher bei Adventure Works Analytics", "similar_trap"),
        ("Koch", "Restaurant Alpenblick", "Gabi Kitchen\nKoch-Ausbildung 2018, HACCP", "strong"),
        ("Short CV", "OfficeWorks GmbH", "Hans Kurz\nBüro", "sparse"),
        ("Rich CV", "MedTech Solutions SE", "Ina Rich\nMedizinische Dokumentation\nKIS, ICD, Hygiene\n3 Jahre Klinikverwaltung\nExcel, Word", "rich"),
    ]
    for i, (role, co, prof, tag) in enumerate(templates, 1):
        hard = tag == "hard_gap"
        unk = tag == "unknown_co"
        sim = tag == "similar_trap"
        c = _case(f"dev_{i:02d}", role, co or "Unknown", prof, hard_block=hard, unknown_co=unk, similar_trap=sim)
        c["tag"] = tag
        cases.append(c)
    return cases


def build_blind40() -> list[dict]:
    """40 fresh blind covers — distinct from prior bc_* and dev_*."""
    cases = []
    # 8 strong
    strong = [
        ("Fachinformatiker Support", "BitForge GmbH", "Nora IT\nFachinformatiker Systemintegration\nWindows, Tickets, AD"),
        ("Lohnbuchhalter", "PayRight AG", "Lars Payroll\nDATEV Lohn, Entgeltabrechnung 4 Jahre"),
        ("Lagerfachkraft", "CargoBay SE", "Mona Warehouse\nFachkraft Lagerlogistik, Staplerschein"),
        ("Hotelfachfrau", "Seehotel Bellevue", "Pia Hotel\nHotelfach-Abschluss, Reservierung, Gästeservice"),
        ("Maschinenbediener", "FormTech GmbH", "Quinn Machine\nSpritzguss, QS, Schichtarbeit"),
        ("Steuerfachangestellte", "Kanzlei Bergmann", "Sara Tax\nSteuerfachangestellte IHK, DATEV, Jahresabschluss"),
        ("Netzwerktechniker", "SecureNet KG", "Tim Network\nFirewall, VPN, Switching — CCNA nicht vorhanden"),
        ("Vertriebsinnendienst", "SalesDesk AG", "Ulla Sales\nAngebote, CRM, Kundentelefon"),
    ]
    for i, (role, co, prof) in enumerate(strong, 1):
        cases.append(_case(f"fb_strong_{i:02d}", role, co, prof))
    # 8 medium
    medium = [
        ("Office Manager", "BureauOne GmbH", "Viktor Office\nTerminplanung, Korrespondenz, Excel"),
        ("Content Creator", "MediaPulse SE", "Wendy Media\nCMS, SEO Grundlagen, Texten"),
        ("Technischer Redakteur", "DocuLine AG", "Xander Docs\nConfluence, XML-Grundlagen"),
        ("Einkaufsassistenz", "ProcureEast KG", "Yara Buy\nBestellwesen, Lieferantenkommunikation"),
        ("Qualitätsprüfer", "QualiCheck GmbH", "Zeno Quality\nChecklisten, Messmittel, ISO-Prozesse"),
        ("Empfangsmitarbeiter", "CityClinic Nord", "Anna Front\nEmpfang, Termine, Telefon"),
        ("IT-Helpdesk", "HelpNow AG", "Boris Help\nFirst-Level Support, Windows"),
        ("Projektassistenz", "ProjectHouse SE", "Carla Project\nTermine, MS Project Grundlagen"),
    ]
    for i, (role, co, prof) in enumerate(medium, 1):
        cases.append(_case(f"fb_med_{i:02d}", role, co, prof))
    # 8 career / transferable
    career = [
        ("Customer Success", "SaaS Care GmbH", "Dina Change\nCallcenter Inbound 3 Jahre — Quereinstieg SaaS"),
        ("Junior Controller", "FinHold AG", "Erik Switch\nBuchhaltung Kreditoren — Interesse Controlling"),
        ("Junior Recruiter", "HireFast KG", "Fiona Pivot\nEmpfang und Terminplanung — Wechsel zu Recruiting"),
        ("Logistikkoordinator", "MoveIt SE", "Georg Retail\nEinzelhandel Filialarbeit — Transfer Disposition"),
        ("HR Generalist Junior", "PeopleCore GmbH", "Hanna Admin\nSachbearbeitung Verwaltung — Transfer Personal"),
        ("Junior Data Analyst", "InsightLab AG", "Ivan Excel\nExcel-Auswertungen, Reporting — kein Studium Data Science"),
        ("Facility Support", "BuildCare SE", "Julia Craft\nHandwerk Montage — Transfer Instandhaltung"),
        ("Inside Sales", "GlowSales GmbH", "Klaus Service\nKundenservice Telefon — Transfer Vertrieb"),
    ]
    for i, (role, co, prof) in enumerate(career, 1):
        cases.append(_case(f"fb_career_{i:02d}", role, co, prof))
    # 5 missing desirable
    desirable = [
        ("Buchhalter", "LedgerPro AG", "Lena Books\nKreditoren, Excel — kein DATEV", "DATEV wünschenswert."),
        ("Marketing Manager", "BrandNova SE", "Mark Content\nContent, Social — kein Google Ads Zertifikat", "Google Ads Zertifikat wünschenswert."),
        ("Systemadmin", "InfraWorks GmbH", "Nina Linux\nLinux, Bash — kein AWS Zertifikat", "AWS Cloud Practitioner wünschenswert."),
        ("Pflegeassistenz", "Haus am Bach", "Otto Care\nGrundpflege, Dokumentation — kein Englisch B2 Zertifikat", "Englisch B2 Zertifikat wünschenswert."),
        ("Bauleiter Assistenz", "BauStark AG", "Petra Site\nBauzeichnung Lesen — kein Autocad Zertifikat", "AutoCAD Zertifikat wünschenswert."),
    ]
    for i, (role, co, prof, extra) in enumerate(desirable, 1):
        cases.append(_case(f"fb_des_{i:02d}", role, co, prof, job_extra=extra + "\n"))
    # 4 unknown company
    for i, (role, prof) in enumerate(
        [
            ("Sachbearbeitung", "Quinn Office\nExcel, Ablage, Telefon"),
            ("Support Specialist", "Rita Soft\nTickets, Windows"),
            ("Lagerhilfe", "Steve Pack\nKommissionierung"),
            ("Assistent/in GF", "Tara Assist\nKalender, Korrespondenz"),
        ],
        1,
    ):
        cases.append(_case(f"fb_unk_{i:02d}", role, "", prof, unknown_co=True))
    # 3 similar company traps
    traps = [
        ("Analyst", "Northwind Insights GmbH", "Uma Data\nSQL, Dashboards\nFrüher: Adventure Works Insights"),
        ("Consultant", "Litware Consulting SE", "Vince Consult\nProzessanalyse\nFrüher: Contoso Consulting"),
        ("Engineer", "Fabrikam Robotics AG", "Wade Eng\nSPS, Inbetriebnahme\nFrüher: Tailspin Robotics"),
    ]
    for i, (role, co, prof) in enumerate(traps, 1):
        cases.append(_case(f"fb_trap_{i:02d}", role, co, prof, similar_trap=True))
    # 2 genuine hard blocks
    cases.append(
        _case(
            "fb_hard_01",
            "Pflegefachkraft",
            "Klinik Westpark",
            "Xena Admin\nBüroorganisation — keine Pflegeausbildung",
            hard_block=True,
            job_extra="Pflicht: abgeschlossene Pflegeausbildung.\n",
        )
    )
    cases.append(
        _case(
            "fb_hard_02",
            "LKW-Fahrer",
            "TransEuro KG",
            "Yuri City\nPKW Führerschein B — kein CE",
            hard_block=True,
            job_extra="Pflicht: Führerschein Klasse CE.\n",
        )
    )
    # 2 sparse
    cases.append(_case("fb_sparse_01", "Bürohilfe", "PaperClip GmbH", "Zoe Mini\nBüro"))
    cases.append(_case("fb_sparse_02", "Aushilfe Verkauf", "ShopQuick AG", "Ada Brief\nKundenkontakt"))
    assert len(cases) == 40, len(cases)
    return cases


def build_interview20() -> list[dict]:
    out = []
    for i, (role, co, skills) in enumerate(
        [
            ("Controller", "FinHold SE", "Reporting, Excel, Kostenrechnung"),
            ("IT-Support", "ByteCare GmbH", "Windows, Tickets, AD"),
            ("Pflegehelfer", "Haus Sonne", "Grundpflege, Dokumentation"),
            ("Disponent", "FleetMove KG", "Tourenplanung, Telefon"),
            ("Recruiter", "TalentBridge", "Active Sourcing, LinkedIn"),
            ("Buchhaltung", "LedgerLite AG", "Kreditoren, DATEV"),
            ("Marketing", "PulseBrand SE", "CMS, SEO, Content"),
            ("Lager", "StockRoom GmbH", "Kommissionierung, Staplerschein"),
            ("Hotelfach", "Alpenhof", "Reservierung, Gästeservice"),
            ("Elektroniker", "PowerFix AG", "Schaltschrank, Wartung"),
            ("HR", "PeopleNest KG", "Onboarding, Personalakte"),
            ("Sales", "DealFlow AG", "Akquise, CRM"),
            ("QA", "TestSphere SE", "Manuelle Tests, Jira"),
            ("Facility", "CampusCare", "Instandhaltung, SLA"),
            ("Einkauf", "SupplyWest GmbH", "Bestellwesen, Lieferanten"),
            ("Sozialarbeit", "Beratung Plus", "Fallmanagement"),
            ("Netzwerk", "NetGuard IT", "Firewall, VPN"),
            ("Empfang", "MedCenter Nord", "Termine, Telefon"),
            ("Produktion", "MetalForm GmbH", "Montage, Schicht"),
            ("Business Analyst", "FinTech Hub", "Anforderungen, UML"),
        ],
        1,
    ):
        out.append(
            {
                "id": f"fi_{i:02d}",
                "profile": f"Interview Cand {i}\n{skills}\nBerufserfahrung: 3 Jahre {role}",
                "job": f"Vorstellungsgespräch {role} bei {co}\nSchwerpunkte: {skills}.",
                "target_company": co,
            }
        )
    return out


def main() -> None:
    payload = {
        "meta": {
            "purpose": "guenther_writing_quality_final",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "model_under_test": "phi4-mini",
        },
        "development_covers": build_dev(),
        "final_blind_covers": build_blind40(),
        "fresh_interviews": build_interview20(),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    payload["meta"]["fixture_sha256"] = hashlib.sha256(raw.encode()).hexdigest()
    payload["meta"]["dev_count"] = len(payload["development_covers"])
    payload["meta"]["blind_count"] = len(payload["final_blind_covers"])
    payload["meta"]["interview_count"] = len(payload["fresh_interviews"])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"wrote": str(OUT), "sha256": payload["meta"]["fixture_sha256"], **{k: payload["meta"][k] for k in ("dev_count","blind_count","interview_count")}}, indent=2))


if __name__ == "__main__":
    main()
