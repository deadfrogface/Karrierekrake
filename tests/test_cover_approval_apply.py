"""Automatic apply uses an approved cover letter and never replaces it."""

from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import MagicMock

from apply.base import ApplyResult
from apply.manager import ApplicationManager
from apply.preview import build_application_preview
from core.config import ExperienceEntry, SourcedText, empty_app_config
from core.cover_letter import (
    CoverLetterResult,
    approve_cover_letter,
    cover_profile_fingerprint,
)
from core.database import Database
from core.models import Job, JobStatus, OperatingMode


def _ready(tmp_path: Path, *, mode: str, dry_run: bool, auto_submit: bool):
    cfg = empty_app_config(root=tmp_path)
    cfg.application.first_name = "Erika"
    cfg.application.last_name = "Beispiel"
    cfg.application.email = "erika@example.org"
    cfg.application.phone = "+491701111111"
    cfg.application.cv_path = str(tmp_path / "cv.pdf")
    (tmp_path / "cv.pdf").write_bytes(b"%PDF-1.4")
    cfg.profile.qualifications.skills = [
        SourcedText(value="Buchhaltung", source="manual"),
        SourcedText(value="Monatsabschlüsse", source="manual"),
    ]
    cfg.profile.qualifications.work_experience = [
        ExperienceEntry(
            title="Buchhaltung",
            company="Mandant Beispiel GmbH",
            start_date="2018-01",
            end_date="2024-06",
            source="manual",
        )
    ]
    cfg.settings.mode = mode
    cfg.settings.dry_run = dry_run
    cfg.settings.automatic_submission = auto_submit
    cfg.settings.delay_between_applications_seconds = 0
    cfg.settings.language = "de"
    return cfg


def _job(job_id: str = "job-approved") -> Job:
    return Job(
        id=job_id,
        source="indeed",
        title="Buchhalter",
        company="Nordlicht Partner GmbH",
        url="https://boards.greenhouse.io/nordlicht/jobs/1",
        application_url="https://boards.greenhouse.io/nordlicht/jobs/1",
        status=JobStatus.NEW.value,
        ats_type="greenhouse",
        match_score=90,
        description="Buchhaltung und Monatsabschlüsse für den Mandantenstamm.",
    )


def _mgr(cfg, monkeypatch) -> tuple[ApplicationManager, dict]:
    captured: dict = {"calls": 0, "cover": None, "submit": None}

    class _Stub:
        def __init__(self, page, *, dry_run=True, submit=False):
            captured["submit"] = submit
            captured["dry_run"] = dry_run

        def apply(self, job, resume_pdf_path, cover_letter_text, profile):
            captured["calls"] += 1
            captured["cover"] = cover_letter_text
            return ApplyResult(success=True, needs_review=True, dry_run_stopped=True)

    monkeypatch.setattr("apply.manager.APPLIERS", {"greenhouse": _Stub})
    monkeypatch.setattr(
        "apply.manager.ATSDetector.detect",
        staticmethod(lambda url: "greenhouse"),
    )
    db = Database(Path(cfg.root) / "data" / "jobs.db")
    return ApplicationManager(cfg, db, MagicMock()), captured


def _approve(cfg, job) -> Path:
    preview = build_application_preview(job, cfg)
    assert preview.cover_refusal_code == ""
    path = approve_cover_letter(
        job,
        cfg,
        preview.cover_letter_preview,
        generated_sha256=preview.cover_letter_sha256,
        profile_fingerprint=preview.cover_profile_fingerprint,
    )
    meta_path = path.with_name(f"{job.id}.meta.json")
    assert cover_profile_fingerprint(cfg, job) == preview.cover_profile_fingerprint
    import json

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta["profile_fingerprint"] == preview.cover_profile_fingerprint
    return path


def test_approved_cover_reaches_applier_even_if_compose_differs(tmp_path: Path, monkeypatch):
    cfg = _ready(
        tmp_path,
        mode=OperatingMode.REVIEW_BEFORE_SUBMIT.value,
        dry_run=True,
        auto_submit=False,
    )
    job = _job()
    path = _approve(cfg, job)
    approved_bytes = path.read_bytes()
    mgr, captured = _mgr(cfg, monkeypatch)

    def _other(*_args, **_kwargs):
        return CoverLetterResult(ok=True, text="Ganz anderer automatisch erzeugter Brief.\n")

    monkeypatch.setattr("apply.manager.compose_cover_letter", _other)
    result = mgr.prepare_and_apply(job)
    assert captured["calls"] == 1
    assert captured["cover"].encode("utf-8") == approved_bytes
    assert captured["cover"] != "Ganz anderer automatisch erzeugter Brief.\n"
    assert path.read_bytes() == approved_bytes
    assert result.needs_review or result.success


def test_changed_profile_keeps_approved_bytes_and_needs_review(tmp_path: Path, monkeypatch):
    cfg = _ready(
        tmp_path,
        mode=OperatingMode.FULLY_AUTOMATIC.value,
        dry_run=False,
        auto_submit=True,
    )
    job = _job("job-stale")
    path = _approve(cfg, job)
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    cfg.profile.qualifications.skills.append(SourcedText(value="Origami", source="manual"))
    mgr, captured = _mgr(cfg, monkeypatch)
    result = mgr.prepare_and_apply(job)
    assert result.needs_review is True
    assert result.submitted is False
    assert "profile_changed_evidence_lost" in (result.error_message or "")
    assert captured["calls"] == 0
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before
    assert not (tmp_path / "cover_letters" / "drafts" / f"{job.id}.txt").exists()


def test_no_approval_fully_automatic_does_not_submit(tmp_path: Path, monkeypatch):
    cfg = _ready(
        tmp_path,
        mode=OperatingMode.FULLY_AUTOMATIC.value,
        dry_run=False,
        auto_submit=True,
    )
    job = _job("job-open")
    mgr, captured = _mgr(cfg, monkeypatch)
    result = mgr.prepare_and_apply(job)
    approved = tmp_path / "cover_letters" / f"{job.id}.txt"
    assert result.needs_review is True
    assert result.submitted is False
    assert "needs_confirmation: cover_not_approved" in (result.error_message or "")
    assert captured["calls"] == 0
    assert captured["submit"] is None
    assert not approved.exists()
    assert not approved.with_name(f"{job.id}.meta.json").exists()


def test_unapproved_draft_is_only_written_under_drafts(tmp_path: Path, monkeypatch):
    cfg = _ready(
        tmp_path,
        mode=OperatingMode.REVIEW_BEFORE_SUBMIT.value,
        dry_run=True,
        auto_submit=False,
    )
    job = _job("job-draft")
    mgr, captured = _mgr(cfg, monkeypatch)
    draft_text = "Entwurf ohne Freigabe.\n"

    def _draft(*_args, **_kwargs):
        return CoverLetterResult(ok=True, text=draft_text)

    monkeypatch.setattr("apply.manager.compose_cover_letter", _draft)
    result = mgr.prepare_and_apply(job)
    approved = tmp_path / "cover_letters" / f"{job.id}.txt"
    draft = tmp_path / "cover_letters" / "drafts" / f"{job.id}.txt"
    assert result.needs_review is True
    assert captured["calls"] == 0
    assert not approved.exists()
    assert draft.is_file()
    raw = draft.read_bytes()
    assert raw == draft_text.encode("utf-8")
    assert b"\r" not in raw
    letters = [
        p.relative_to(tmp_path / "cover_letters")
        for p in (tmp_path / "cover_letters").rglob("*.txt")
    ]
    assert letters == [Path("drafts") / f"{job.id}.txt"]
