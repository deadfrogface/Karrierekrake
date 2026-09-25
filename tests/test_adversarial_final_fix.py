"""Adversarial final-fix regressions: safety escalate, CV path, pause, status API."""

from __future__ import annotations

import inspect
import threading
from copy import deepcopy
from pathlib import Path
from unittest.mock import MagicMock

from apply.base import ApplyResult
from apply.manager import ApplicationManager
from core.config import empty_app_config
from core.database import Database
from core.models import Job, JobStatus, OperatingMode


def _cfg(tmp_path: Path, *, dry_run: bool, auto_submit: bool, mode: str) -> object:
    cfg = empty_app_config(root=tmp_path)
    cfg.application.first_name = "Ada"
    cfg.application.last_name = "Tester"
    cfg.application.email = "ada.tester@example.com"
    cfg.application.phone = "+491701234567"
    cfg.application.cv_path = str(tmp_path / "cv.pdf")
    (tmp_path / "cv.pdf").write_bytes(b"%PDF-1.4")
    (tmp_path / "cover_letters").mkdir(exist_ok=True)
    cfg.settings.mode = mode
    cfg.settings.dry_run = dry_run
    cfg.settings.automatic_submission = auto_submit
    cfg.settings.minimum_match_for_auto_apply = 50
    cfg.settings.database_path = "data/jobs.db"
    (tmp_path / "data").mkdir(exist_ok=True)
    return cfg


def _job(n: int = 1) -> Job:
    return Job(
        id=f"adv-{n}",
        source="indeed",
        title=f"Sachbearbeiter {n}",
        company=f"Fiktiv GmbH {n}",
        url=f"https://boards.greenhouse.io/fiktiv/jobs/{n}",
        application_url=f"https://boards.greenhouse.io/fiktiv/jobs/{n}",
        status=JobStatus.NEW.value,
        ats_type="greenhouse",
        match_score=90,
    )


def test_mid_run_safety_escalate_does_not_open_submit(tmp_path: Path, monkeypatch):
    """Chaotic user flips dry_run off + auto-submit on between jobs — fail closed."""
    cfg = _cfg(
        tmp_path,
        dry_run=True,
        auto_submit=False,
        mode=OperatingMode.FULLY_AUTOMATIC.value,
    )
    db = Database(cfg.db_path, recover=False)
    captured: list[dict] = []

    class Stub:
        def __init__(self, page, *, dry_run=True, submit=False):
            captured.append({"dry_run": dry_run, "submit": submit})

        def apply(self, *a, **k):
            return ApplyResult(success=True, dry_run_stopped=True, submitted=False)

    monkeypatch.setattr("apply.manager.APPLIERS", {"greenhouse": Stub})
    monkeypatch.setattr(
        "apply.manager.ATSDetector.detect",
        staticmethod(lambda url: "greenhouse"),
    )
    mgr = ApplicationManager(cfg, db, MagicMock())
    mgr.prepare_and_apply(_job(1))
    cfg.settings.dry_run = False
    cfg.settings.automatic_submission = True
    mgr.prepare_and_apply(_job(2))
    assert captured[0]["submit"] is False
    assert captured[1]["submit"] is False
    assert captured[1]["dry_run"] is True


def test_live_dry_run_tightening_still_closes_open_gate(tmp_path: Path, monkeypatch):
    """If run started with submit open, enabling dry_run mid-flight must close it."""
    cfg = _cfg(
        tmp_path,
        dry_run=False,
        auto_submit=True,
        mode=OperatingMode.FULLY_AUTOMATIC.value,
    )
    db = Database(cfg.db_path, recover=False)
    captured: list[dict] = []

    class Stub:
        def __init__(self, page, *, dry_run=True, submit=False):
            self.dry_run = dry_run
            self.submit = submit
            captured.append({"dry_run": dry_run, "submit": submit})

        def apply(self, *a, **k):
            return ApplyResult(
                success=True,
                dry_run_stopped=not self.submit,
                submitted=self.submit,
            )

    monkeypatch.setattr("apply.manager.APPLIERS", {"greenhouse": Stub})
    monkeypatch.setattr(
        "apply.manager.ATSDetector.detect",
        staticmethod(lambda url: "greenhouse"),
    )
    mgr = ApplicationManager(cfg, db, MagicMock())
    assert mgr._submit_gate_open is True
    mgr.prepare_and_apply(_job(1))
    assert captured[0]["submit"] is True
    cfg.settings.dry_run = True  # user enables safety mid-run
    mgr.prepare_and_apply(_job(2))
    assert captured[1]["submit"] is False
    assert captured[1]["dry_run"] is True


def test_schedule_service_safe_without_schtasks(tmp_path: Path):
    """Pause/save must not crash on Linux or when schtasks is missing."""
    from desktop.services.schedule_service import ScheduleService

    cfg = empty_app_config(root=tmp_path)
    cfg.settings.run_automatically = True
    cfg.settings.automation_paused = True
    ok, msg = ScheduleService(cfg).sync_from_config()
    assert ok is True
    assert isinstance(msg, str) and msg

    cfg.settings.automation_paused = False
    cfg.settings.run_automatically = True
    ok2, msg2 = ScheduleService(cfg).sync_from_config()
    # Non-Windows: create path returns False with a clear message (no crash).
    assert isinstance(msg2, str) and msg2


def test_missing_cv_file_blocks_can_auto_apply(tmp_path: Path):
    cfg = _cfg(
        tmp_path,
        dry_run=True,
        auto_submit=False,
        mode=OperatingMode.REVIEW_BEFORE_SUBMIT.value,
    )
    cfg.application.cv_path = str(tmp_path / "does-not-exist.pdf")
    db = Database(cfg.db_path, recover=False)
    mgr = ApplicationManager(cfg, db, MagicMock())
    ok, reason = mgr.can_auto_apply(_job())
    assert ok is False
    assert "CV" in reason or "cv" in reason.lower()


def test_whitespace_profile_fields_block_auto_apply(tmp_path: Path):
    cfg = _cfg(
        tmp_path,
        dry_run=True,
        auto_submit=False,
        mode=OperatingMode.REVIEW_BEFORE_SUBMIT.value,
    )
    cfg.application.email = "   \t  "
    cfg.application.first_name = "Ada"
    db = Database(cfg.db_path, recover=False)
    mgr = ApplicationManager(cfg, db, MagicMock())
    ok, reason = mgr.can_auto_apply(_job())
    assert ok is False
    assert "email" in reason


def test_update_job_status_refuses_wipe_of_applied(tmp_path: Path):
    db = Database(tmp_path / "jobs.db", recover=False)
    db.upsert_job(
        Job(
            id="prot",
            source="t",
            title="T",
            company="C",
            status=JobStatus.APPLIED.value,
        )
    )
    db.update_job_status("prot", JobStatus.NEW.value)
    assert db.get_job("prot").status == JobStatus.APPLIED.value
    db.update_job_status("prot", JobStatus.IGNORED.value)
    assert db.get_job("prot").status == JobStatus.APPLIED.value
    # APPLIED is terminal — even FAILED must not demote via this API.
    db.update_job_status("prot", JobStatus.FAILED.value)
    assert db.get_job("prot").status == JobStatus.APPLIED.value


def test_blocked_reapply_does_not_demote_applied(tmp_path: Path):
    cfg = _cfg(
        tmp_path,
        dry_run=False,
        auto_submit=True,
        mode=OperatingMode.FULLY_AUTOMATIC.value,
    )
    db = Database(cfg.db_path, recover=False)
    db.upsert_job(
        Job(
            id="kept",
            source="indeed",
            title="Sachbearbeiter",
            company="Fiktiv GmbH",
            url="https://boards.greenhouse.io/fiktiv/jobs/9",
            status=JobStatus.APPLIED.value,
            match_score=90,
            ats_type="greenhouse",
        )
    )
    from core.models import ApplicationRecord

    db.save_application(
        ApplicationRecord(
            job_id="kept",
            company="Fiktiv GmbH",
            position="Sachbearbeiter",
            status="applied",
            result="submitted",
        )
    )
    mgr = ApplicationManager(cfg, db, MagicMock())
    result = mgr.prepare_and_apply(
        Job(
            id="kept",
            source="indeed",
            title="Sachbearbeiter",
            company="Fiktiv GmbH",
            url="https://boards.greenhouse.io/fiktiv/jobs/9",
            match_score=90,
            ats_type="greenhouse",
            status=JobStatus.NEW.value,
        )
    )
    assert "already applied" in (result.error_message or "")
    assert db.get_job("kept").status == JobStatus.APPLIED.value


def test_review_mode_missing_cv_does_not_open_applier(tmp_path: Path, monkeypatch):
    cfg = _cfg(
        tmp_path,
        dry_run=True,
        auto_submit=False,
        mode=OperatingMode.REVIEW_BEFORE_SUBMIT.value,
    )
    cfg.application.cv_path = str(tmp_path / "missing.pdf")
    db = Database(cfg.db_path, recover=False)
    called = {"n": 0}

    class Stub:
        def __init__(self, page, *, dry_run=True, submit=False):
            pass

        def apply(self, *a, **k):
            called["n"] += 1
            return ApplyResult(success=True, dry_run_stopped=True)

    monkeypatch.setattr("apply.manager.APPLIERS", {"greenhouse": Stub})
    monkeypatch.setattr(
        "apply.manager.ATSDetector.detect",
        staticmethod(lambda url: "greenhouse"),
    )
    mgr = ApplicationManager(cfg, db, MagicMock())
    result = mgr.prepare_and_apply(_job())
    assert called["n"] == 0
    assert result.needs_review is True
    assert "CV" in (result.error_message or "")


def test_upsert_never_demotes_applied_to_needs_review(tmp_path: Path):
    db = Database(tmp_path / "jobs.db", recover=False)
    db.upsert_job(
        Job(id="a", source="t", title="T", company="C", status=JobStatus.APPLIED.value)
    )
    db.upsert_job(
        Job(id="a", source="t", title="T", company="C", status=JobStatus.NEEDS_REVIEW.value)
    )
    assert db.get_job("a").status == JobStatus.APPLIED.value


def test_start_pipeline_always_deepcopies_config():
    import desktop.main_window as mw

    src = inspect.getsource(mw.MainWindow._start_pipeline)
    assert "deepcopy" in src


def test_pipeline_worker_pause_stops_should_stop():
    from desktop.workers import PipelineWorker

    cfg = empty_app_config()
    worker = PipelineWorker(cfg, mode="search_only")
    assert worker._cancel.is_set() is False
    assert worker._pause.is_set() is False
    worker.set_paused(True)
    assert worker._pause.is_set() is True
    worker.set_paused(False)
    assert worker._pause.is_set() is False


def test_run_pipeline_pause_flag_mid_search_stops(tmp_path: Path, monkeypatch):
    from app.main import run_pipeline

    cfg = empty_app_config(root=tmp_path)
    cfg.settings.database_path = "data/jobs.db"
    cfg.settings.logs_dir = "logs"
    (tmp_path / "data").mkdir()
    (tmp_path / "logs").mkdir()
    cfg.profile.jobs.desired_titles = ["Tester"]
    cfg.profile.location.home_address = "Berlin"
    cfg.settings.enabled_sources = ["company_sites"]
    cfg.settings.automation_paused = False

    def should_stop():
        return bool(cfg.settings.automation_paused)

    # Flip pause after pipeline has started (shared config mutation in tests).
    calls = {"n": 0}

    def fake_sources(enabled):
        calls["n"] += 1

        class Src:
            source_id = "company_sites"

            def safe_search(self, queries):
                cfg.settings.automation_paused = True
                return [], None, None

        return [Src()]

    monkeypatch.setattr("app.main.build_sources", fake_sources)
    stats = run_pipeline(cfg, mode="search_only", should_stop=should_stop)
    assert stats.get("cancelled") is True or stats.get("paused") is True


def test_deepcopy_isolates_gui_config_mutations(tmp_path: Path, monkeypatch):
    """Simulate _start_pipeline snapshot vs ConfigService cache mutation."""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    from desktop.services import ConfigService

    svc = ConfigService()
    cfg = svc.load()
    cfg.profile.jobs.desired_titles = ["Tester"]
    cfg.profile.location.home_address = "Berlin"
    cfg.settings.dry_run = True
    cfg.settings.mode = "search_only"
    cfg.settings.automatic_submission = False
    svc.save(cfg)

    run_cfg = deepcopy(svc.load())
    # GUI-side mutation of cached config must not touch the worker snapshot.
    svc.config.settings.dry_run = False
    svc.config.settings.mode = OperatingMode.FULLY_AUTOMATIC.value
    svc.config.settings.automatic_submission = True
    assert run_cfg.settings.dry_run is True
    assert run_cfg.settings.automatic_submission is False


def test_pause_resume_spam_on_worker_is_idempotent():
    from desktop.workers import PipelineWorker

    worker = PipelineWorker(empty_app_config(), mode="search_only")
    for _ in range(20):
        worker.set_paused(True)
        worker.set_paused(False)
        worker.request_cancel()
    assert worker._cancel.is_set() is True
    # cancel stays set; pause cleared on last resume
    assert worker._pause.is_set() is False


def test_overlapping_start_guard_uses_thread_is_running():
    from desktop.workers import thread_is_running

    assert thread_is_running(None) is False
    # Rapid spam: deleted / None thread must never look "running"
    class Dead:
        def isRunning(self) -> bool:
            raise RuntimeError("already deleted")

    assert thread_is_running(Dead()) is False  # type: ignore[arg-type]
