"""force_submit must never override dry_run safety."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from apply.base import ApplyResult
from apply.manager import ApplicationManager
from core.config import empty_app_config
from core.database import Database
from core.models import Job, JobStatus, OperatingMode


def test_force_submit_true_with_dry_run_stays_dry(tmp_path: Path, monkeypatch):
    cfg = empty_app_config(root=tmp_path)
    cfg.application.first_name = "Erika"
    cfg.application.last_name = "Musterfrau"
    cfg.application.email = "erika@example.org"
    cfg.application.phone = "+491701111111"
    cfg.application.cv_path = str(tmp_path / "cv.pdf")
    (tmp_path / "cv.pdf").write_bytes(b"%PDF")
    cfg.settings.mode = OperatingMode.FULLY_AUTOMATIC.value
    cfg.settings.dry_run = True
    cfg.settings.automatic_submission = True
    db = Database(tmp_path / "data" / "jobs.db")
    mgr = ApplicationManager(cfg, db, MagicMock())
    captured = {}

    class Stub:
        def __init__(self, page, *, dry_run=True, submit=False):
            captured["dry_run"] = dry_run
            captured["submit"] = submit

        def apply(self, *a, **k):
            return ApplyResult(success=True, dry_run_stopped=True)

    monkeypatch.setattr("apply.manager.APPLIERS", {"greenhouse": Stub})
    monkeypatch.setattr("apply.manager.ATSDetector.detect", staticmethod(lambda url: "greenhouse"))
    job = Job(
        id="jf1",
        source="indeed",
        title="Role",
        company="Co",
        url="https://boards.greenhouse.io/x/jobs/1",
        application_url="https://boards.greenhouse.io/x/jobs/1",
        status=JobStatus.NEW.value,
        ats_type="greenhouse",
        match_score=99,
    )
    mgr.prepare_and_apply(job, force_submit=True)
    assert captured.get("submit") is False
    assert captured.get("dry_run") is True
