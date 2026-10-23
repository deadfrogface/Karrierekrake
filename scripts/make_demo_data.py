"""Fill an empty data folder with an invented person, jobs, applications and mail for a demo.

    python scripts/make_demo_data.py <folder>

Everything here is made up (Mara Beispiel, example.org addresses, invented employers). The demo starts with
``KARRIEREKRAKE_DEMO=1 KARRIEREKRAKE_DATA_DIR=<folder>``, so it never touches the real data of the person who runs it.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PERSON = dict(first="Mara", last="Beispiel", email="mara.beispiel@example.org", phone="0221 0000000",
              street="Beispielstraße 1", postal="50667", city="Köln")

JOBS = [
    # title, company, city, km, remote, employment, source, score, reasons, description
    ("Sachbearbeiter Rechnungswesen (m/w/d)", "Rheinwerk Logistik GmbH", "Köln", 3.2, "onsite", "Vollzeit", "bundesagentur", 66,
     ["working time matched", "salary unknown (not hard-failed)", "country matched (DACH cross-border)", "within radius 20.0 km",
      "Direkt: Erfahrung Sachbearbeiter, Köln", "Direkt: Kenntnisse SAP, DATEV"]),
    ("Buchhalter Debitoren (m/w/d)", "Domblick Versicherungen AG", "Köln", 5.1, "hybrid", "Vollzeit", "indeed", 61,
     ["working time matched", "salary unknown (not hard-failed)", "within radius 20.0 km", "Direkt: Erfahrung Buchhaltung"]),
    ("Sachbearbeiter Auftragsabwicklung", "Kölsch & Söhne Handels GmbH", "Frechen", 11.4, "onsite", "Vollzeit", "stepstone", 54,
     ["working time matched", "within radius 20.0 km", "Direkt: Kenntnisse Excel"]),
    ("Finanzbuchhalter (m/w/d) mit Homeoffice-Option", "Neumarkt Treuhand GmbH", "Köln", 4.0, "hybrid", "Teilzeit", "xing", 58,
     ["working time matched", "within radius 20.0 km", "Direkt: Kenntnisse DATEV"]),
    ("Kaufmännischer Sachbearbeiter Einkauf", "Bergisch Metall GmbH", "Bergisch Gladbach", 14.9, "onsite", "Vollzeit", "bundesagentur", 49,
     ["working time matched", "within radius 20.0 km"]),
    ("Sachbearbeiter Kreditorenbuchhaltung", "Agnes Klinikverbund", "Köln", 7.7, "onsite", "Vollzeit", "linkedin", 47,
     ["working time matched", "within radius 20.0 km", "Direkt: Erfahrung Rechnungen"]),
    ("Servicekraft Kundenservice (m/w/d)", "Rheinbahn Service GmbH", "Köln", 2.6, "onsite", "Teilzeit", "indeed", 37, ["working time matched"]),
    ("Controlling Assistenz", "Deutzer Maschinenbau AG", "Köln", 6.2, "hybrid", "Vollzeit", "stepstone", 44,
     ["working time matched", "within radius 20.0 km"]),
    ("Sachbearbeiter Personalwesen", "Kranhaus Immobilien GmbH", "Leverkusen", 18.3, "onsite", "Vollzeit", "xing", 41,
     ["working time matched", "within radius 20.0 km"]),
    ("Buchhaltung Teilzeit 20 Std.", "Weißer Rhein Apotheken", "Köln", 3.9, "onsite", "Teilzeit", "bundesagentur", 52,
     ["working time matched", "within radius 20.0 km", "Direkt: Kenntnisse Excel"]),
    ("Sachbearbeiter Vertrieb Innendienst", "Hohe Pforte Elektrotechnik", "Köln", 8.8, "onsite", "Vollzeit", "indeed", 39,
     ["working time matched", "within radius 20.0 km"]),
    ("Sachbearbeiter Reisekosten", "Südstadt Consulting GmbH", "Köln", 4.7, "remote", "Vollzeit", "linkedin", 57,
     ["working time matched", "100% remote — no distance penalty"]),
]

AD = ("Ihre Aufgaben: Sie prüfen und buchen Eingangsrechnungen, überwachen Zahlungseingänge, stimmen Konten ab und "
      "unterstützen bei Monats- und Jahresabschlüssen. Sie arbeiten eng mit Einkauf und Controlling zusammen. "
      "Ihr Profil: abgeschlossene kaufmännische Ausbildung, erste Berufserfahrung in der Buchhaltung, sicherer Umgang mit "
      "MS Excel, Kenntnisse in SAP oder DATEV von Vorteil, genaue und selbstständige Arbeitsweise. Wir bieten: einen "
      "sicheren Arbeitsplatz, flexible Arbeitszeiten, 30 Tage Urlaub, Jobticket und ein freundliches Team in Köln. Bitte "
      "bewerben Sie sich mit Lebenslauf und Gehaltsvorstellung.")


def iso(days_ago: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).replace(microsecond=0).isoformat()


def build(folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    os.environ["KARRIEREKRAKE_DATA_DIR"] = str(folder)
    from core.config import EducationEntry, ExperienceEntry, LanguageEntry, SourcedText
    from core.database import Database
    from core.lifecycle import ApplicationCase, LifecycleEvent, LifecycleEventType
    from core.models import ApplicationRecord, Job
    from desktop.services import ConfigService

    service = ConfigService()
    cfg = service.load()
    app = cfg.application
    app.first_name, app.last_name, app.email, app.phone = PERSON["first"], PERSON["last"], PERSON["email"], PERSON["phone"]
    app.street, app.postal_code, app.city, app.country = PERSON["street"], PERSON["postal"], PERSON["city"], "DE"
    app.address = f"{PERSON['street']}, {PERSON['postal']} {PERSON['city']}"
    loc = cfg.profile.location
    loc.home_address, loc.postal_code, loc.city, loc.max_distance_km = app.address, PERSON["postal"], PERSON["city"], 20
    loc.home_latitude, loc.home_longitude = 50.9375, 6.9603
    cfg.profile.jobs.desired_titles = ["Sachbearbeiter Rechnungswesen"]
    q = cfg.profile.qualifications
    q.work_experience = [
        ExperienceEntry(title="Sachbearbeiterin Buchhaltung", company="Rheinland Büroservice GmbH", location="Köln",
                        start_date="03/2021", end_date="08/2025",
                        responsibilities=["Prüfung und Buchung von Eingangsrechnungen", "Kontenabstimmung und Mahnwesen",
                                          "Vorbereitung von Monatsabschlüssen mit DATEV"]),
        ExperienceEntry(title="Büroassistentin", company="Altstadt Verwaltung KG", location="Köln",
                        start_date="09/2018", end_date="02/2021", responsibilities=["Telefon- und Postbearbeitung", "Terminplanung"]),
    ]
    q.education = [EducationEntry(qualification="Bürokauffrau (IHK)", institution="Berufskolleg Köln", completion_date="2018")]
    q.skills = [SourcedText(value="Debitorenbuchhaltung"), SourcedText(value="Mahnwesen")]
    q.software = [SourcedText(value="SAP"), SourcedText(value="DATEV"), SourcedText(value="Excel")]
    q.languages = [LanguageEntry(language="Deutsch", level="C2"), LanguageEntry(language="Englisch", level="B2")]
    cfg.settings.language, cfg.settings.dry_run, cfg.settings.mode = "de", True, "review_before_submit"
    service.save(cfg)
    service.mark_first_run_done()

    db = Database(service.load().db_path)
    jobs = []
    for index, (title, company, city, km, remote, kind, source, score, reasons) in enumerate(JOBS):
        job = Job(id=f"demo-job-{index}", source=source, source_job_id=f"demo-{index}", title=title, company=company,
                  description=AD, city=city, postal_code="", country_code="DE", latitude=50.94 + index * 0.003,
                  longitude=6.96 + index * 0.004, airline_km=km, remote_type=remote, employment_type=kind,
                  url=f"https://example.org/jobs/{index}", application_url=f"https://example.org/jobs/{index}/apply",
                  match_score=score, match_reasons=[f"✓ {r}" if not r.startswith("Direkt") else r for r in reasons],
                  rejection_reasons=[], status="new", discovered_at=iso(index % 4))
        db.upsert_job(job)
        jobs.append(job)

    def application(job, status, days):
        db.save_application(ApplicationRecord(id=f"demo-app-{job.id}", job_id=job.id, company=job.company, position=job.title,
                                              application_date=iso(days), platform=job.source, status=status))

    def case(job, status, *events):
        row = db.upsert_case(ApplicationCase(id=f"demo-case-{job.id}", job_id=job.id, company=job.company, position=job.title,
                                             status=status, applied_at=iso(9)))
        for index, (kind, source, days) in enumerate(events):
            db.append_lifecycle_event(LifecycleEvent(event_type=kind, case_id=row.id, source=source, occurred_at=iso(days),
                                                     idempotency_key=f"demo-{row.id}-{index}"))
        return row

    E = LifecycleEventType
    application(jobs[0], "applied", 2)
    case(jobs[0], "applied", (E.APPLICATION_CREATED.value, "manual", 2), (E.APPLICATION_SENT.value, "apply", 2))
    application(jobs[1], "confirmation", 9)
    case(jobs[1], "interview", (E.APPLICATION_CREATED.value, "manual", 9), (E.APPLICATION_SENT.value, "manual", 9),
         (E.APPLICATION_RECEIVED.value, "imap", 8), (E.INTERVIEW_REQUESTED.value, "imap", 3))
    application(jobs[2], "applied", 14)
    case(jobs[2], "rejected", (E.APPLICATION_CREATED.value, "manual", 14), (E.APPLICATION_SENT.value, "manual", 14),
         (E.APPLICATION_RECEIVED.value, "imap", 13), (E.REJECTION_RECEIVED.value, "imap", 5))
    application(jobs[3], "to_apply", 1)
    case(jobs[3], "to_apply", (E.APPLICATION_CREATED.value, "manual", 1))

    for index, (sender, subject, body, category) in enumerate([
        ("karriere@domblick.example.org", "Einladung zum Vorstellungsgespräch",
         "Sehr geehrte Frau Beispiel, vielen Dank für Ihre Bewerbung. Wir möchten Sie gern zu einem Vorstellungsgespräch "
         "einladen. Bitte nennen Sie uns zwei Terminvorschläge.", "interview"),
        ("personal@rheinwerk.example.org", "Eingangsbestätigung Ihrer Bewerbung",
         "Vielen Dank für Ihre Bewerbung als Sachbearbeiter Rechnungswesen. Wir haben Ihre Bewerbung erhalten.", "confirmation"),
        ("jobs@koelschsoehne.example.org", "Ihre Bewerbung bei Kölsch & Söhne",
         "Leider müssen wir Ihnen mitteilen, dass wir uns für einen anderen Bewerber entschieden haben.", "rejection"),
    ]):
        db.save_email_message({"gmail_id": f"demo-mail-{index}", "subject": subject, "sender": sender, "body_text": body,
                               "category": category, "confidence": 0.9, "association_status": "unlinked",
                               "received_at": iso(3 + index)})
    print(f"Demo-Daten in {folder}")


if __name__ == "__main__":
    build(Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT / "demo-data")
