"""Deterministic fake UI fixtures for visual QA — no real PII."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import uuid

from core.database import Database
from core.lifecycle import CaseStatus
from core.models import ApplicationRecord, Job, JobStatus


def seed_visual_qa_db(db_path: str | Path, *, scenario: str = "populated") -> Database:
    """Seed a local SQLite DB for screenshots / polish QA.

    Scenarios: empty | apps_one | apps_many | inbox_mix | overview_active
    """
    db = Database(str(db_path))
    if scenario == "empty":
        return db

    now = datetime.now(timezone.utc)
    rows = [
        ("Nordlicht Consulting GmbH", "Office Manager (m/w/d)", JobStatus.APPLIED, CaseStatus.APPLIED),
        ("RheinOffice GmbH", "Teamassistenz", JobStatus.APPLIED, CaseStatus.INTERVIEW),
        ("Acme Recruiting", "Backend Engineer", JobStatus.NEEDS_REVIEW, CaseStatus.APPLIED),
        ("Kölner Medienhaus", "Redakteur", JobStatus.APPLIED, CaseStatus.APPLIED),
        ("TechStart Berlin", "Product Owner", JobStatus.CLOSED, CaseStatus.REJECTED),
        ("Muster Soft AG", "Software Engineer", JobStatus.APPLIED, CaseStatus.OFFER),
        ("HafenLogistik", "Dispatcher", JobStatus.QUEUED, CaseStatus.TO_APPLY),
        ("Alpen IT", "DevOps", JobStatus.APPLYING, CaseStatus.TO_APPLY),
    ]
    if scenario == "apps_one":
        rows = rows[:1]
    elif scenario == "overview_active":
        rows = rows[:4]

    case_by_company: dict[str, str] = {}
    for i, (company, title, job_status, case_status) in enumerate(rows):
        job = Job(
            id=str(uuid.uuid4()),
            source="demo",
            source_job_id=f"demo-{i}",
            title=title,
            company=company,
            city="Berlin",
            url=f"https://jobs.example/{i}",
            match_score=70 + (i * 3) % 25,
            status=job_status.value,
            remote_type="hybrid",
            distance_km=float(12 + i),
        )
        db.upsert_job(job)
        db.save_application(
            ApplicationRecord(
                job_id=job.id,
                company=company,
                position=title,
                status=job_status.value,
                application_date=(now - timedelta(days=i)).isoformat(),
            )
        )
        case = db.ensure_case_from_job(job, status=case_status.value)
        case_by_company[company] = case.id

    if scenario in {"inbox_mix", "overview_active", "apps_many", "populated"}:
        mails = [
            {
                "id": "m-ambig",
                "gmail_id": "m-ambig",
                "sender": "Acme Recruiting <hr@acme.example>",
                "subject": "Ihre Bewerbung",
                "body_text": "Wir melden uns zu Ihrer Bewerbung.",
                "category": "generic",
                "association_status": "ambiguous",
                "case_id": "",
                "received_at": now.isoformat(),
            },
            {
                "id": "m-interview",
                "gmail_id": "m-interview",
                "sender": "RheinOffice GmbH <jobs@rheinoffice.example>",
                "subject": "Einladung zum Gespräch",
                "body_text": "Wir laden Sie herzlich zum Interview ein.",
                "category": "interview_invite",
                "association_status": "linked",
                "case_id": case_by_company.get("RheinOffice GmbH", ""),
                "received_at": (now - timedelta(days=1)).isoformat(),
            },
            {
                "id": "m-confirm",
                "gmail_id": "m-confirm",
                "sender": "Kölner Medienhaus <bewerbung@medien.example>",
                "subject": "Ihre Bewerbung ist eingegangen",
                "body_text": "Eingangsbestätigung.",
                "category": "confirmation",
                "association_status": "linked",
                "case_id": case_by_company.get("Kölner Medienhaus", ""),
                "received_at": (now - timedelta(days=3)).isoformat(),
            },
            {
                "id": "m-reject",
                "gmail_id": "m-reject",
                "sender": "TechStart Berlin <talent@techstart.example>",
                "subject": "Rückmeldung zu Ihrer Bewerbung",
                "body_text": "Leider müssen wir Ihnen absagen.",
                "category": "rejection",
                "association_status": "linked",
                "case_id": case_by_company.get("TechStart Berlin", ""),
                "received_at": (now - timedelta(days=4)).isoformat(),
            },
            {
                "id": "m-offer",
                "gmail_id": "m-offer",
                "sender": "Muster Soft AG <hr@muster.example>",
                "subject": "Angebot",
                "body_text": "Wir freuen uns, Ihnen ein Angebot zu unterbreiten.",
                "category": "offer",
                "association_status": "linked",
                "case_id": case_by_company.get("Muster Soft AG", ""),
                "received_at": (now - timedelta(days=2)).isoformat(),
            },
        ]
        for row in mails:
            if not row.get("case_id") and row["id"] != "m-ambig":
                continue
            db.save_email_message(row)

    return db
