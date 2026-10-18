"""Adversarial final-fix regressions: safety escalate, CV path, pause, status API."""

from __future__ import annotations

import inspect
import os
import subprocess
import sys
import threading
from copy import deepcopy
from pathlib import Path
from unittest.mock import MagicMock

import hashlib
import json

import pytest

from apply.base import ApplyResult
from apply.manager import ApplicationManager
from core.config import empty_app_config
from core.cover_letter import cover_profile_fingerprint
from core.database import Database
from core.models import Job, JobStatus, OperatingMode


def _seed_approval(cfg, job: Job) -> None:
    text = "Guten Tag.\n"
    folder = Path(cfg.root) / "cover_letters"
    folder.mkdir(parents=True, exist_ok=True)
    raw = text.encode("utf-8")
    (folder / f"{job.id}.txt").write_bytes(raw)
    (folder / f"{job.id}.meta.json").write_text(
        json.dumps(
            {
                "job_id": job.id,
                "edited": False,
                "generated_sha256": hashlib.sha256(raw).hexdigest(),
                "profile_fingerprint": cover_profile_fingerprint(cfg, job),
            }
        ),
        encoding="utf-8",
        newline="",
    )


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
    _seed_approval(cfg, _job(1))
    mgr.prepare_and_apply(_job(1))
    cfg.settings.dry_run = False
    cfg.settings.automatic_submission = True
    _seed_approval(cfg, _job(2))
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
    _seed_approval(cfg, _job(1))
    mgr.prepare_and_apply(_job(1))
    assert captured[0]["submit"] is True
    cfg.settings.dry_run = True  # user enables safety mid-run
    _seed_approval(cfg, _job(2))
    mgr.prepare_and_apply(_job(2))
    assert captured[1]["submit"] is False
    assert captured[1]["dry_run"] is True


def test_schedule_service_safe_without_schtasks(tmp_path: Path, monkeypatch):
    """Pause/save must not crash on Linux or when schtasks is missing."""
    from desktop.services import native_schedule as ns
    from desktop.services import schedule_service as ss
    from desktop.services.schedule_service import ScheduleService

    # Isolation: never read/write scheduler files (systemd units, LaunchAgents)
    # in the real HOME of the machine running the tests.
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("USERPROFILE", str(fake_home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(fake_home / ".config"))
    monkeypatch.setattr(Path, "home", lambda: fake_home)

    # systemctl/launchctl/schtasks act on the task NAME, not on HOME: a real call
    # would disable/delete a developer's or runner's real autorun. Every launcher
    # is mocked on every platform and simulates a missing scheduler binary.
    commands: list[list[str]] = []

    def scheduler_missing(args, *a, **k):
        commands.append(list(args))
        raise FileNotFoundError(2, "scheduler not available (test)", args[0])

    def no_real_process(*a, **k):
        raise AssertionError(f"real process started: {a!r}")

    monkeypatch.setattr(ns, "run", scheduler_missing)
    monkeypatch.setattr(ss.subprocess, "run", scheduler_missing)
    monkeypatch.setattr(subprocess, "Popen", no_real_process)

    # Orphaned scheduler files from an earlier failed activation (fake HOME only).
    if sys.platform != "win32":
        for file in ns.paths():
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text("orphan\n", encoding="utf-8")

    cfg = empty_app_config(root=tmp_path)
    cfg.settings.run_automatically = True
    cfg.settings.automation_paused = True
    ok, msg = ScheduleService(cfg).sync_from_config()
    assert ok is True
    assert isinstance(msg, str) and msg
    if sys.platform == "win32":
        assert commands == [["schtasks", "/Delete", "/TN", ss.TASK_NAME, "/F"]]
    elif sys.platform == "darwin":
        assert commands == [["launchctl", "bootout", f"gui/{ns.os.getuid()}/{ns.LABEL}"]]
    else:
        assert commands == [
            ["systemctl", "--user", "disable", "--now", f"{ns.UNIT}.timer", f"{ns.UNIT}.service"]
        ]
    if sys.platform != "win32":
        assert not any(file.exists() for file in ns.paths())

    commands.clear()
    cfg.settings.automation_paused = False
    cfg.settings.run_automatically = True
    ok2, msg2 = ScheduleService(cfg).sync_from_config()
    # Non-Windows: create path returns False with a clear message (no crash).
    assert isinstance(msg2, str) and msg2
    assert ok2 is False
    if sys.platform == "win32":
        assert commands[0] == ["schtasks", "/Delete", "/TN", ss.TASK_NAME, "/F"]
        create = commands[1]
        assert create[:4] == ["schtasks", "/Create", "/TN", ss.TASK_NAME]
        assert "--once" in create[create.index("/TR") + 1]
        assert len(commands) == 2
    elif sys.platform == "darwin":
        # unload by name (no files left), then the activation attempt; a missing
        # launchctl cannot have loaded anything, so the rollback does not unload again
        assert commands == [
            ["launchctl", "bootout", f"gui/{ns.os.getuid()}/{ns.LABEL}"],
            ["launchctl", "bootstrap", f"gui/{ns.os.getuid()}", str(ns.paths()[0])],
        ]
    else:
        # unload by name (no files left), activation attempt, then best-effort
        # rollback reload (missing systemctl: nothing loaded, no second unload)
        assert commands == [
            ["systemctl", "--user", "disable", "--now", f"{ns.UNIT}.timer", f"{ns.UNIT}.service"],
            ["systemctl", "--user", "daemon-reload"],
            ["systemctl", "--user", "daemon-reload"],
        ]
    if sys.platform != "win32":
        assert not any(file.exists() for file in ns.paths())


def _real_scheduler_files() -> dict[str, tuple[bool, int, int]]:
    """stat() (read-only) of every scheduler file the app could own in the real HOME."""
    home = Path.home()
    candidates = [
        home / ".config" / "systemd" / "user" / "karrierekrake-autorun.service",
        home / ".config" / "systemd" / "user" / "karrierekrake-autorun.timer",
        home / "Library" / "LaunchAgents" / "com.karrierekrake.autorun.plist",
    ]
    xdg = os.environ.get("XDG_CONFIG_HOME", "")
    if xdg and Path(xdg).is_absolute():
        candidates += [
            Path(xdg) / "systemd" / "user" / "karrierekrake-autorun.service",
            Path(xdg) / "systemd" / "user" / "karrierekrake-autorun.timer",
        ]
    result = {}
    for file in candidates:
        try:
            st = file.stat()
            result[str(file)] = (True, st.st_mtime_ns, st.st_size)
        except OSError:
            result[str(file)] = (False, 0, 0)
    return result


@pytest.mark.parametrize("platform", ["linux", "darwin", "win32"])
def test_isolated_schedule_test_writes_nothing_outside_tmp_path(tmp_path: Path, monkeypatch, platform):
    """Running the isolated test above must not write outside tmp_path or run a real scheduler."""
    before = _real_scheduler_files()
    root = tmp_path.resolve()
    outside: list[tuple[str, str]] = []

    def _check(op: str, target) -> None:
        resolved = Path(os.fspath(target)).resolve()
        if resolved != root and root not in resolved.parents:
            outside.append((op, str(resolved)))

    def _spy(op: str, original):
        def wrapper(self, *args, **kwargs):
            _check(op, self)
            return original(self, *args, **kwargs)

        return wrapper

    for name in ("write_text", "write_bytes", "mkdir", "touch", "unlink", "chmod", "rename", "replace", "rmdir"):
        monkeypatch.setattr(Path, name, _spy(name, getattr(Path, name)))
    real_open = Path.open

    def spy_open(self, mode="r", *args, **kwargs):
        if any(flag in mode for flag in "wax+"):
            _check("open:" + mode, self)
        return real_open(self, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", spy_open)
    for name in ("replace", "rename", "remove", "unlink", "mkdir", "makedirs", "rmdir"):
        real = getattr(os, name)
        monkeypatch.setattr(os, name, lambda target, *a, _n=name, _r=real, **k: (_check("os." + _n, target), _r(target, *a, **k))[1])

    commands: list[list[str]] = []

    def no_real_scheduler(args, *a, **k):
        commands.append(list(args))
        raise FileNotFoundError(2, "scheduler not available (test)", args[0])

    def no_real_process(*a, **k):
        raise AssertionError(f"real subprocess started: {a!r}")

    monkeypatch.setattr(subprocess, "run", no_real_scheduler)
    monkeypatch.setattr(subprocess, "Popen", no_real_process)
    monkeypatch.setattr(sys, "platform", platform)
    monkeypatch.setattr(os, "getuid", lambda: 501, raising=False)

    test_schedule_service_safe_without_schtasks(tmp_path, monkeypatch)

    assert outside == []
    # The test mocks every scheduler launcher itself (and asserts the recorded
    # commands); nothing may fall through to subprocess.run or Popen.
    assert commands == []
    monkeypatch.undo()
    assert _real_scheduler_files() == before


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
