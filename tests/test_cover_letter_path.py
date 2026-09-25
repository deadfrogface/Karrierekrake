"""Cover letters must land under AppData cover_letters/, not private/."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from apply.base import ApplyResult
from apply.manager import ApplicationManager
from core.config import SourcedText, empty_app_config
from core.database import Database
from core.models import Job, JobStatus, OperatingMode


def test_prepare_writes_cover_letter_to_appdata_dir(tmp_path: Path, monkeypatch):
    cfg = empty_app_config(root=tmp_path)
    cfg.application.first_name = "Erika"
    cfg.application.last_name = "Musterfrau"
    cfg.application.email = "erika@example.org"
    cfg.application.phone = "+491701111111"
    cfg.profile.qualifications.skills.append(
        SourcedText(value="Buchhaltung", source="manual")
    )
    cfg.application.cv_path = str(tmp_path / "cv.pdf")
    (tmp_path / "cv.pdf").write_bytes(b"%PDF-1.4")
    cfg.settings.mode = OperatingMode.REVIEW_BEFORE_SUBMIT.value
    cfg.settings.dry_run = True
    cfg.settings.automatic_submission = False

    db = Database(tmp_path / "data" / "jobs.db")
    job = Job(
        id="job-cl-1",
        source="test",
        title="Buchhalter",
        company="ACME",
        url="https://boards.greenhouse.io/acme/jobs/1",
        application_url="https://boards.greenhouse.io/acme/jobs/1",
        status=JobStatus.NEW.value,
        ats_type="greenhouse",
        match_score=90,
        description="Buchhaltung und Monatsabschlüsse für den Mandantenstamm.",
    )
    mgr = ApplicationManager(cfg, db, MagicMock())

    class _StubApplier:
        def __init__(self, page, *, dry_run=True, submit=False):
            self.dry_run = dry_run
            self.submit = submit

        def apply(self, job, resume_pdf_path, cover_letter_text, profile):
            return ApplyResult(success=True, needs_review=True, dry_run_stopped=True)

    monkeypatch.setattr("apply.manager.APPLIERS", {"greenhouse": _StubApplier})
    monkeypatch.setattr(
        "apply.manager.ATSDetector.detect",
        staticmethod(lambda url: "greenhouse"),
    )

    result = mgr.prepare_and_apply(job)
    assert result.success or result.needs_review
    expected = tmp_path / "cover_letters" / f"{job.id}.txt"
    assert expected.is_file(), f"missing cover letter at {expected}"
    assert not (tmp_path / "private" / "cover_letters" / f"{job.id}.txt").exists()
