"""automatic_submission must gate fully_automatic submit decisions."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from apply.base import ApplyResult
from apply.manager import ApplicationManager
from core.config import empty_app_config
from core.database import Database
from core.models import Job, JobStatus, OperatingMode


def _mgr(tmp_path: Path, *, mode: str, dry_run: bool, auto_submit: bool) -> ApplicationManager:
    cfg = empty_app_config(root=tmp_path)
    cfg.application.first_name = "Erika"
    cfg.application.last_name = "Musterfrau"
    cfg.application.email = "erika@example.org"
    cfg.application.phone = "+491701111111"
    cfg.application.street = "Testweg 1"
    cfg.application.postal_code = "10115"
    cfg.application.city = "Berlin"
    cfg.application.cv_path = str(tmp_path / "cv.pdf")
    (tmp_path / "cv.pdf").write_bytes(b"%PDF-1.4")
    cfg.settings.mode = mode
    cfg.settings.dry_run = dry_run
    cfg.settings.automatic_submission = auto_submit
    db = Database(tmp_path / "data" / "jobs.db")
    return ApplicationManager(cfg, db, MagicMock())


def test_fully_automatic_without_auto_submit_stays_dry(tmp_path: Path, monkeypatch):
    mgr = _mgr(
        tmp_path,
        mode=OperatingMode.FULLY_AUTOMATIC.value,
        dry_run=False,
        auto_submit=False,
    )
    captured = {}

    class _StubApplier:
        def __init__(self, page, *, dry_run=True, submit=False):
            captured["dry_run"] = dry_run
            captured["submit"] = submit

        def apply(self, job, resume_pdf_path, cover_letter_text, profile):
            return ApplyResult(success=True, dry_run_stopped=True)

    monkeypatch.setattr("apply.manager.APPLIERS", {"greenhouse": _StubApplier})
    monkeypatch.setattr(
        "apply.manager.ATSDetector.detect",
        staticmethod(lambda url: "greenhouse"),
    )
    job = Job(
        id="j1",
        source="indeed",
        title="Buchhalter",
        company="ACME",
        url="https://boards.greenhouse.io/acme/jobs/1",
        application_url="https://boards.greenhouse.io/acme/jobs/1",
        status=JobStatus.NEW.value,
        ats_type="greenhouse",
        match_score=90,
    )
    mgr.prepare_and_apply(job)
    assert captured.get("submit") is False
    assert captured.get("dry_run") is True


def test_fully_automatic_with_auto_submit_can_request_submit(tmp_path: Path, monkeypatch):
    mgr = _mgr(
        tmp_path,
        mode=OperatingMode.FULLY_AUTOMATIC.value,
        dry_run=False,
        auto_submit=True,
    )
    captured = {}

    class _StubApplier:
        def __init__(self, page, *, dry_run=True, submit=False):
            captured["dry_run"] = dry_run
            captured["submit"] = submit

        def apply(self, job, resume_pdf_path, cover_letter_text, profile):
            return ApplyResult(success=True, submitted=True)

    monkeypatch.setattr("apply.manager.APPLIERS", {"greenhouse": _StubApplier})
    monkeypatch.setattr(
        "apply.manager.ATSDetector.detect",
        staticmethod(lambda url: "greenhouse"),
    )
    job = Job(
        id="j2",
        source="indeed",
        title="Buchhalter",
        company="ACME",
        url="https://boards.greenhouse.io/acme/jobs/2",
        application_url="https://boards.greenhouse.io/acme/jobs/2",
        status=JobStatus.NEW.value,
        ats_type="greenhouse",
        match_score=90,
    )
    mgr.prepare_and_apply(job)
    assert captured.get("submit") is True
    assert captured.get("dry_run") is False


def test_partial_ats_never_gets_submit_under_full_auto(tmp_path: Path, monkeypatch):
    """Personio/partial ATS must not receive submit=True even with auto submission."""
    mgr = _mgr(
        tmp_path,
        mode=OperatingMode.FULLY_AUTOMATIC.value,
        dry_run=False,
        auto_submit=True,
    )
    captured = {}

    class _StubApplier:
        def __init__(self, page, *, dry_run=True, submit=False):
            captured["dry_run"] = dry_run
            captured["submit"] = submit

        def apply(self, job, resume_pdf_path, cover_letter_text, profile):
            return ApplyResult(success=True, needs_review=True, dry_run_stopped=True)

    monkeypatch.setattr("apply.manager.APPLIERS", {"personio": _StubApplier})
    monkeypatch.setattr(
        "apply.manager.ATSDetector.detect",
        staticmethod(lambda url: "personio"),
    )
    job = Job(
        id="j-partial",
        source="indeed",
        title="Buchhalter",
        company="ACME",
        url="https://acme.jobs.personio.de/job/1",
        application_url="https://acme.jobs.personio.de/job/1",
        status=JobStatus.NEW.value,
        ats_type="personio",
        match_score=90,
    )
    mgr.prepare_and_apply(job)
    assert captured.get("submit") is False
    assert captured.get("dry_run") is True
