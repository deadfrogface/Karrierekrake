#!/usr/bin/env python3
"""Freeze fictional generalization fixtures (hash recorded before eval)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "benchmark" / "corpus" / "guenther_final_hardening_fixtures.json"

# Credential families deliberately NOT from prior failure set (Pflege/ISTQB/Meister/Staatsexamen/Studium/Netzwerk)
GEN1: list[dict] = []
GEN2: list[dict] = []
WRONG_CO: list[dict] = []
ELIGIBLE: list[dict] = []
BLIND_COVER: list[dict] = []
BLIND_INTERVIEW: list[dict] = []
CROSS_CASE: list[dict] = []
REPAIR_VAL: list[dict] = []


def _add_cred(
    bucket: list,
    cid: str,
    profile: str,
    job: str,
    body: str,
    *,
    expect_ok: bool,
    company: str = "Fiktiv AG",
) -> None:
    bucket.append(
        {
            "id": cid,
            "profile": profile,
            "job": job,
            "body": body,
            "target_company": company,
            "expect_final_ok": expect_ok,
        }
    )


def build_gen1() -> None:
    n = 0
    pairs_missing = [
        ("TÜV-Sachkundeprüfung Sicherheit", "tuev pruefung sicherheit"),
        ("Gabelstaplerschein", "staplerschein"),
        ("Rettungssanitäter-Ausbildung", "rettungssanitaeter"),
        ("Steuerfachangestellte IHK", "steuerfachangestellte"),
        ("Bürokauffrau IHK Abschluss", "buerokauffrau"),
        ("DevOps Professional Zertifikat", "devops professional"),
        ("PMP Projektmanagement", "pmp zertifizierung"),
        ("ISO 9001 Lead Auditor", "iso 9001 lead auditor"),
        ("AWS Cloud Practitioner", "aws cloud practitioner"),
        ("Scrum Master PSM I", "psm scrum master"),
        ("Erste-Hilfe-Sachkunde", "erste hilfe sachkunde"),
        ("SCC-Sicherheitszertifikat", "scc zertifikat"),
        ("Fachkraft für Lagerlogistik", "fachkraft lagerlogistik"),
        ("Kaufmann E-Commerce IHK", "kaufmann ecommerce"),
        ("Medizinische Fachangestellte Examen", "mfa examen"),
        ("Elektroniker für Energie und Gebäudetechnik", "elektroniker energie"),
        ("Fachinformatiker Anwendungsentwicklung", "fachinformatiker anwendungsentwicklung"),
        ("Hotelfachmann/-frau Abschluss", "hotelfach"),
        ("Koch-Ausbildung", "koch ausbildung"),
        ("Erzieher/in staatlich anerkannt", "erzieher staatlich"),
        ("Notfallsanitäter-Ausbildung", "notfallsanitaeter"),
        ("Geprüfter Immobilienfachwirt", "immobilienfachwirt"),
        ("Certified Information Systems Auditor", "cisa"),
        ("Truck-Führerschein Klasse CE", "fuehrerschein ce"),
        ("Pharmazeutisch-technische Assistentin", "pta"),
        ("Geprüfter Wirtschaftsfachwirt IHK", "wirtschaftsfachwirt"),
        ("Fachkraft für Abwassertechnik", "abwassertechnik"),
        ("Sachkundeprüfung §34a GewO", "34a gewo"),
        ("HACCP-Beauftragter Zertifikat", "haccp"),
        ("Geprüfter Technischer Betriebswirt", "technischer betriebswirt"),
    ]
    for cred_label, key in pairs_missing:
        n += 1
        prof = f"Alex Test\nVerwaltung, Excel — kein {cred_label.split()[0]}"
        job = f"Stelle Fiktiv\nPflicht: {cred_label}."
        body = f"Ich habe {cred_label} abgeschlossen und bringe relevante Erfahrung mit."
        _add_cred(GEN1, f"cg1_miss_{n:02d}", prof, job, body, expect_ok=False)

    pairs_have = [
        ("Gabelstaplerschein", "2019 Staplerschein erworben"),
        ("TÜV-Sachkundeprüfung", "TÜV-Sachkundeprüfung Sicherheit 2020"),
        ("Bürokauffrau IHK", "Ausbildung Bürokauffrau IHK 2018"),
        ("AWS Cloud Practitioner", "Zertifikat AWS Cloud Practitioner"),
        ("PSM I Scrum", "Scrum Master PSM I Zertifikat"),
        ("Erste-Hilfe", "Erste-Hilfe-Sachkunde vorhanden"),
        ("Fachkraft Lagerlogistik", "Abschluss Fachkraft für Lagerlogistik"),
        ("Kaufmann E-Commerce", "IHK Kaufmann E-Commerce"),
        ("MFA Examen", "Medizinische Fachangestellte Examen"),
        ("Elektroniker", "Elektroniker für Energie und Gebäudetechnik Ausbildung"),
    ]
    for cred_label, prof_line in pairs_have:
        n += 1
        prof = f"Sam Beleg\n{prof_line}\nKenntnisse: Teamarbeit"
        job = f"Stelle Fiktiv\nPflicht: {cred_label}."
        body = (
            f"Sehr geehrte Damen und Herren, wie in meinem Profil beschrieben ({prof_line}) "
            f"unterstütze ich Ihr Team bei Fiktiv AG. Mit freundlichen Grüßen."
        )
        _add_cred(GEN1, f"cg1_have_{n:02d}", prof, job, body, expect_ok=True, company="Fiktiv AG")

    related = [
        ("Lagererfahrung ohne Staplerschein", "Kommissionierung, Warenwirtschaft", "Gabelstaplerschein"),
        ("Buchhaltung ohne Steuerfachangestellte", "Kreditoren, Excel", "Steuerfachangestellte IHK"),
        ("IT-Support ohne AWS-Zertifikat", "Windows Support, Tickets", "AWS Cloud Practitioner"),
        ("Projektarbeit ohne PMP", "Projektassistenz, MS Project", "PMP"),
        ("Qualität ohne ISO Lead Auditor", "Interne Audits, Checklisten", "ISO 9001 Lead Auditor"),
        ("Agile Team ohne PSM", "Daily Standups, Kanban", "PSM I"),
        ("Erste Hilfe Kurs besucht ohne Sachkunde", "Betrieblicher Ersthelfer Kurs", "Erste-Hilfe-Sachkunde"),
        ("Logistik ohne Fachkraft Abschluss", "Versand, Kommissionierung", "Fachkraft Lagerlogistik"),
        ("Online-Handel ohne Kaufmann E-Commerce", "Shop-Pflege, Kundenservice", "Kaufmann E-Commerce"),
        ("Praxis ohne MFA Examen", "Termine, Empfang", "MFA Examen"),
    ]
    for title, prof_line, cred in related:
        n += 1
        prof = f"Rita Related\n{prof_line}"
        job = f"Stelle\nPflicht: {cred}."
        body = f"Ich habe {cred} abgeschlossen."
        _add_cred(GEN1, f"cg1_rel_{n:02d}", prof, job, body, expect_ok=False)

    diff = [
        ("Elektriker Gesellenbrief", "Gesellenbrief Elektriker", "Elektroniker Energie"),
        ("Koch-Ausbildung", "Koch-Ausbildung abgeschlossen", "Hotelfachmann"),
        ("Erzieher", "Staatl. anerkannter Erzieher", "Kaufmännische Ausbildung"),
        ("SCC", "SCC-Zertifikat", "TÜV-Sachkundeprüfung"),
        ("Fachinformatiker", "Fachinformatiker Systemintegration", "Fachinformatiker Anwendungsentwicklung"),
        ("DevOps Zertifikat", "DevOps Professional", "AWS Cloud Practitioner"),
        ("Bürokauffrau", "Bürokauffrau IHK", "Steuerfachangestellte"),
        ("Rettungssanitäter", "Rettungssanitäter-Ausbildung", "Notfallsanitäter"),
        ("Hotelfach", "Hotelfach-Abschluss", "Koch-Ausbildung"),
        ("E-Commerce Kaufmann", "Kaufmann E-Commerce", "Einzelhandelskaufmann"),
    ]
    for prof_line, have, required in diff:
        n += 1
        prof = f"Diff Case\n{prof_line}"
        job = f"Job\nPflicht: {required}."
        body = f"Ich verfüge über {required}."
        _add_cred(GEN1, f"cg1_diff_{n:02d}", prof, job, body, expect_ok=False)


def build_gen2() -> None:
    items = [
        ("Heftruckführerschein", False, "kein Stapler"),
        ("Geprüfter Bilanzbuchhalter", False, "Buchhaltung Excel"),
        ("Certified Kubernetes Administrator", False, "Linux Admin"),
        ("SAP FI Zertifizierung", False, "kein SAP"),
        ("CEH Ethical Hacker", False, "IT Security Grundlagen"),
        ("Truck-Führerschein Klasse C", False, "PKW Führerschein"),
        ("Facharztqualifikation", False, "Medizinische Verwaltung"),
        ("Notfallsanitäter", False, "Erste Hilfe Kurs"),
        ("Pharmazeutisch-technische Assistentin", False, "Apothekenhelfer"),
        ("Geprüfter Wirtschaftsfachwirt IHK", False, "Teamleitung Vertrieb"),
        ("Staplerschein", True, "Staplerschein 2021"),
        ("IHK Bilanzbuchhalter", True, "Geprüfter Bilanzbuchhalter IHK"),
        ("CKA Kubernetes", True, "Certified Kubernetes Administrator"),
        ("SAP FI Zertifikat", True, "SAP FI Zertifizierung bestanden"),
        ("CEH Zertifikat", True, "CEH Ethical Hacker Zertifikat"),
        ("Geprüfter Industriemeister Metall", False, "CNC-Fräsen, Schichtarbeit"),
        ("Fachkraft für Arbeitssicherheit", False, "Werkstatt, PSA"),
        ("IHK Foreign Language Correspondent", False, "Englisch B1"),
        ("Geprüfter Betriebswirt IHK", False, "Kostenrechnung Excel"),
        ("Certified Data Professional", False, "SQL Grundlagen"),
        ("Sachkundeprüfung Explosionsschutz", False, "Elektroinstallation"),
        ("Geprüfter Technischer Kaufmann", False, "Angebotserstellung"),
        ("Fachkraft für Schutz und Sicherheit", False, "Empfangsdienst"),
        ("Geprüfter Immobiliensachverständiger", False, "Mietverwaltung"),
        ("Industriemeister Metall", True, "Geprüfter Industriemeister Metall 2022"),
        ("Fachkraft Arbeitssicherheit", True, "Fachkraft für Arbeitssicherheit Zertifikat"),
        ("Foreign Language Correspondent", True, "IHK Foreign Language Correspondent"),
        ("Betriebswirt IHK", True, "Geprüfter Betriebswirt IHK Abschluss"),
        ("CDP Data", True, "Certified Data Professional Zertifikat"),
        ("Explosionsschutz Sachkunde", True, "Sachkundeprüfung Explosionsschutz bestanden"),
        ("Technischer Kaufmann", True, "Geprüfter Technischer Kaufmann IHK"),
        ("Schutz und Sicherheit", True, "Fachkraft für Schutz und Sicherheit Ausbildung"),
        ("Immobiliensachverständiger", True, "Geprüfter Immobiliensachverständiger"),
    ]
    for i, (cred, ok, prof_line) in enumerate(items, 1):
        prof = f"Gen2 {i}\n{prof_line}"
        job = f"Stelle\nPflicht: {cred}."
        if ok:
            body = (
                f"Sehr geehrte Damen und Herren, laut Profil: {prof_line}. "
                f"Ich bewerbe mich bei Fiktiv AG."
            )
            company = "Fiktiv AG"
        else:
            body = f"Ich bin im Besitz der Qualifikation {cred}."
            company = "Fiktiv AG"
        _add_cred(GEN2, f"cg2_{i:02d}", prof, job, body, expect_ok=ok, company=company)


def build_wrong_company() -> None:
    cases = [
        ("Northwind GmbH", "Adventure Works GmbH", False),
        ("Litware SE", "Litware", True),
        ("Contoso AG", "Contoso Aktiengesellschaft", True),
        ("Fabrikam KG", "Fabrikam", True),
        ("Tailspin GmbH & Co. KG", "Tailspin", True),
        ("Wide World Importers", "WWI", False),
        ("Beispielklinik Süd", "Beispielklinik", True),
        ("", "für die ausgeschriebene Position", True),
        ("Unknown", "Ich bewerbe mich für die ausgeschriebene Position.", True),
        ("Alpha Beta GmbH", "Gamma Delta GmbH", False),
    ]
    for i in range(30):
        tc, body_co, ok = cases[i % len(cases)]
        prof = "Mira Bewerberin\nOffice Erfahrung"
        job = f"Stelle bei {tc or 'Unbekannt'}"
        if ok:
            body = f"Sehr geehrte Damen und Herren, {body_co} interessiert mich. Mit freundlichen Grüßen."
        else:
            body = f"Sehr geehrte Damen und Herren, bei {body_co} möchte ich mich bewerben."
        WRONG_CO.append(
            {
                "id": f"wc_{i+1:02d}",
                "profile": prof,
                "job": job,
                "body": body,
                "target_company": tc or "Unknown",
                "expect_final_ok": ok,
            }
        )


def build_eligible_writing() -> None:
    templates = [
        ("Sachbearbeiter", "Nordlicht Verwaltung GmbH", "Bürokauffrau IHK 2019", "DATEV, Excel, Korrespondenz"),
        ("IT-Support", "Pixelwerk IT AG", "Fachinformatiker Systemintegration", "Windows, Tickets, AD"),
        ("Lagerist", "LogiTrans SE", "Staplerschein 2020", "Kommissionierung, WMS"),
        ("Pflegehilfe", "Sonnenklinik GmbH", "Pflegehelfer Kurs 2021", "Grundpflege, Dokumentation"),
        ("Koch", "Restaurant Alpenblick", "Koch-Ausbildung 2018", "Mise en Place, HACCP"),
        ("Elektroniker", "EnergiePlus GmbH", "Elektroniker Energie Ausbildung", "Schaltschrank, Wartung"),
        ("HR Assistant", "PeopleFirst KG", "Personalsachbearbeitung 3 Jahre", "Recruiting, Onboarding"),
        ("Verkäufer", "Modehaus Weber", "Einzelhandelskaufmann", "Kasse, Beratung"),
        ("Mechaniker", "AutoFix Werkstatt", "Kfz-Mechatroniker Gesellenbrief", "Diagnose, Service"),
        ("Projektassistenz", "BuildCo AG", "Projektmanagement Grundlagen", "Termine, MS Project"),
        ("Datenschutz", "SecureData GmbH", "Datenschutzbeauftragter Fortbildung", "DSGVO, Audits"),
        ("Marketing", "BrandWave SE", "Marketingfachkraft IHK", "Social Media, Content"),
        ("Technischer Redakteur", "DocuTech GmbH", "Technische Redaktion Zertifikat", "Confluence, XML"),
        ("Empfang", "Hotel Seeblick", "Hotelfachfrau Abschluss", "Reservierung, Gästeservice"),
        ("Qualität", "QualiPro GmbH", "Interne Audits", "ISO-Prozesse, Checklisten"),
        ("Buchhaltung", "FinanzNest AG", "Steuerfachangestellte IHK", "Kreditoren, SAP FI"),
        ("Grafik", "DesignStudio Nord", "Mediengestalter Digital", "Adobe, Layout"),
        ("Pflegefachkraft", "Klinik am Park", "Examinierte Pflegefachkraft 2017", "Intensiv, Hygiene"),
        ("Sicherheit", "Guardian Service", "Sachkundeprüfung §34a", "Objektschutz, Deeskalation"),
        ("Einkauf", "SupplyChain KG", "Industriekaufmann IHK", "Bestellwesen, Lieferanten"),
    ]
    for i, (role, co, cred_line, skills) in enumerate(templates, 1):
        prof = f"Kandidat {i}\n{cred_line}\n{skills}"
        job = f"{role} bei {co}\nAnforderungen: {skills.split(',')[0].strip()}."
        body = (
            f"Sehr geehrte Damen und Herren,\n\n"
            f"mit {cred_line} und Erfahrung in {skills} bewerbe ich mich als {role} bei {co}. "
            f"Ich freue mich auf Ihre Rückmeldung.\n\nMit freundlichen Grüßen\nKandidat {i}"
        )
        ELIGIBLE.append(
            {
                "id": f"ew_{i:02d}",
                "profile": prof,
                "job": job,
                "body": body,
                "target_company": co,
                "expect_final_ok": True,
                "forbid_role_reversal": True,
                "forbid_wrong_role": [],
            }
        )


def build_blind_quality() -> None:
    domains = [
        ("Archivarin", "Stadtarchiv Musterstadt", "Historische Bestände, EAD"),
        ("DevOps Engineer", "CloudNine GmbH", "Linux, CI/CD, Docker"),
        ("Kundenservice", "TelCo Plus AG", "Inbound, CRM, Deutsch C1"),
        ("Produktionshelfer", "MetallWerk Süd", "Montage, Schicht"),
        ("Steuerfachangestellte", "Steuerberatung Krüger", "DATEV, Jahresabschluss"),
        ("Pflegefachkraft", "Altenheim Sonnenhof", "Grundpflege, Medikamentengabe"),
        ("Softwaretester", "AppCheck SE", "Manuelle Tests, Jira"),
        ("Disponent", "SpedLog KG", "Tourenplanung, Telefon"),
        ("Facility Manager", "GebäudeService Nord", "Instandhaltung, SLA"),
        ("Content Manager", "WebWelt GmbH", "CMS, SEO"),
        ("Laborant", "ChemLab AG", "HPLC, GLP"),
        ("Eventmanager", "EventPro Berlin", "Planung, Budget"),
        ("Controller", "Industrie Holding SE", "Reporting, Excel"),
        ("Sozialarbeiter", "Caritas Beratung", "Fallmanagement"),
        ("Netzwerkadmin", "NetSecure IT", "Firewall, VPN"),
        ("Zahnmedizinische Fachangestellte", "Praxis Dr. Weiß", "Prophylaxe, Termine"),
        ("Filialleiter", "SuperMarkt24", "Personal, Kasse"),
        ("Übersetzer", "LinguaWorks", "EN-DE, Fachtexte"),
        ("Maschinenbediener", "KunststoffTech", "Spritzguss, QS"),
        ("Recruiter", "TalentHub", "Active Sourcing, LinkedIn"),
        ("Technischer Einkäufer", "Maschinenbau Ost", "Angebote, Lieferanten"),
        ("Medizinische Dokumentation", "Krankenhaus West", "KIS, ICD"),
        ("Key Account", "B2B Sales Pro", "Akquise, CRM"),
        ("Gärtner", "Grünanlagen Stadt", "Pflege, Maschinen"),
        ("Patentanwaltsfachangestellte", "IP Law Partners", "Fristen, Akten"),
        ("Business Analyst", "FinTech Now", "Anforderungen, UML"),
        ("Rechtsanwaltsfachangestellte", "Kanzlei Hartmann", "Mandatsführung"),
        ("Speditionskaufmann", "CargoLine", "Zoll, Incoterms"),
        ("Werkstudent Marketing", "Startup Labs", "Studium BWL, Social"),
        ("Servicetechniker", "KlimaKontrolle", "Wartung, Kältemittel"),
    ]
    for i, (role, co, skills) in enumerate(domains, 1):
        prof = f"Blind Cover {i}\n{skills}\nReferenz: Projektarbeit in {role.lower()}"
        job = f"{role} (m/w/d)\n{co}\nProfil: {skills}."
        BLIND_COVER.append(
            {
                "id": f"bc_{i:02d}",
                "profile": prof,
                "job": job,
                "target_company": co,
                "forbid_role_reversal": True,
                "forbid_wrong_role": [],
            }
        )
    iv_roles = domains[:20]
    for i, (role, co, skills) in enumerate(iv_roles, 1):
        prof = f"Blind Interview {i}\n{skills}\nBerufserfahrung: 4 Jahre {role}"
        job = f"Vorstellungsgespräch {role} bei {co}\nSchwerpunkte: {skills}."
        BLIND_INTERVIEW.append(
            {
                "id": f"bi_{i:02d}",
                "profile": prof,
                "job": job,
                "target_company": co,
            }
        )


def build_cross_and_repair_val() -> None:
    CROSS_CASE.extend(
        [
            {
                "id": "cc_01",
                "profile": "Person A\nStaplerschein",
                "job": "Stelle Alpha GmbH",
                "body": "Bewerbung bei Beta GmbH",
                "target_company": "Alpha GmbH",
                "expect_final_ok": False,
            },
            {
                "id": "cc_02",
                "profile": "Person B\nDATEV",
                "job": "Stelle Beta GmbH",
                "body": "Sehr geehrte Damen und Herren, bei Beta GmbH interessiert mich die Stelle.",
                "target_company": "Beta GmbH",
                "expect_final_ok": True,
            },
        ]
    )
    for i in range(1, 31):
        REPAIR_VAL.append(
            {
                "id": f"rv_{i:02d}",
                "profile": f"Repair Val {i}\nOffice",
                "job": "Stelle",
                "body": "Sehr geehrte Damen und Herren, ich habe die Qualifikation X ohne Beleg.",
                "target_company": "Fiktiv AG" if i % 3 else "Northwind GmbH",
                "expect_final_ok": False,
            }
        )


def main() -> None:
    build_gen1()
    build_gen2()
    build_wrong_company()
    build_eligible_writing()
    build_blind_quality()
    build_cross_and_repair_val()
    payload = {
        "meta": {
            "purpose": "guenther_final_hardening",
            "gen1_count": len(GEN1),
            "gen2_count": len(GEN2),
            "wrong_company_count": len(WRONG_CO),
            "eligible_writing_count": len(ELIGIBLE),
            "blind_cover_count": len(BLIND_COVER),
            "blind_interview_count": len(BLIND_INTERVIEW),
        },
        "credential_generalization_set1": GEN1,
        "credential_generalization_set2": GEN2,
        "wrong_company": WRONG_CO,
        "eligible_writing": ELIGIBLE,
        "blind_cover_quality": BLIND_COVER,
        "blind_interview_quality": BLIND_INTERVIEW,
        "cross_case_contamination": CROSS_CASE,
        "repair_validator_cases": REPAIR_VAL,
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    payload["meta"]["fixture_sha256"] = hashlib.sha256(raw.encode()).hexdigest()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"wrote": str(OUT), "sha256": payload["meta"]["fixture_sha256"]}, indent=2))


if __name__ == "__main__":
    main()
