"""Real failure paths from the Windows/Intel macOS acceptance jobs."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import time
import pytest

from core import cv_docpick_import as cv
from core.cv_import_deadline import ImportDeadlineWatch
from scripts.ci_cv_import_exe_offline_e2e import _run_child_import


def test_repair_budget_accounts_for_time_already_spent(monkeypatch):
    monkeypatch.delenv("KARRIEREKRAKE_CV_IMPORT_TIMEOUT_S", raising=False)
    cv.reset_import_timeout()
    monkeypatch.setattr(cv, "_import_started_at", 0.0)
    monkeypatch.setattr(cv.time, "monotonic", lambda: 0.0)
    first = cv.choose_import_timeout_s(prompt_tokens=1000, max_tokens=2000,
                                     n_threads_batch=3, physical=4, reserve=1)
    monkeypatch.setattr(cv.time, "monotonic", lambda: 600.0)
    second = cv.choose_import_timeout_s(prompt_tokens=100, max_tokens=500,
                                      n_threads_batch=3, physical=4, reserve=1)
    assert second == 900
    assert second >= first
    cv._enforce_timeout(0, stage="after_model")
    monkeypatch.setattr(cv.time, "monotonic", lambda: 901.0)
    with pytest.raises(cv.CvImportError, match="llm_timeout"):
        cv._enforce_timeout(0, stage="after_model")
    cv.reset_import_timeout()


def test_explicit_import_limit_is_not_extended(monkeypatch):
    monkeypatch.setenv("KARRIEREKRAKE_CV_IMPORT_TIMEOUT_S", "123")
    cv.reset_import_timeout()
    for _ in range(2):
        assert cv.choose_import_timeout_s(prompt_tokens=100, max_tokens=500) == 123
    cv.reset_import_timeout()


def test_repair_resets_parent_progress_without_resetting_import_clock():
    watch = ImportDeadlineWatch(initial_s=700, started_at=0, env_locked=False,
                                buffer_s=60, ceiling_s=900)
    watch.note_max_tokens(2000)
    watch.note_n_prompt(1000)
    watch.note_prompt(1000, now=50, t_mono=50, block_s=50)
    watch.note_tokens(1000, now=500, t_mono=500)
    watch.begin_repair(900)
    watch.note_max_tokens(500)
    watch.note_n_prompt(100)
    watch.note_prompt(100, now=600, t_mono=600, block_s=10)
    watch.note_tokens(1, now=610, t_mono=610)
    assert watch.tokens_done == 1
    assert watch.max_tokens == 500
    assert watch.failure(620) is None
    assert watch.failure(671) == "stall"
    assert watch.started_at == 0
    locked = ImportDeadlineWatch(initial_s=123, started_at=0, env_locked=True,
                                 buffer_s=60, ceiling_s=900)
    locked.begin_repair(900)
    assert locked.limit_s == 123


def test_supervisor_receives_repair_event():
    from desktop.cv_import_supervisor import _note_phase_budget

    watch = ImportDeadlineWatch(initial_s=700, started_at=0, env_locked=False,
                                buffer_s=60, ceiling_s=900)
    watch.note_max_tokens(2000)
    watch.tokens_done = 1000
    _note_phase_budget(watch, {"phase": "generation_start", "timeout_s": 900}, None)
    assert watch.tokens_done == 0
    assert watch.max_tokens is None
    assert watch.limit_s == 900


def test_windows_timeout_targets_only_started_process_tree(monkeypatch):
    from scripts import ci_cv_import_exe_offline_e2e as acceptance

    commands = []
    monkeypatch.setattr(acceptance.os, "name", "nt")
    monkeypatch.setattr(acceptance.subprocess, "run", lambda cmd, **kw: commands.append(cmd))
    class Process:
        pid = 4321
        waited = False
        def poll(self):
            return 1
        def wait(self, timeout):
            self.waited = True
    proc = Process()
    acceptance._stop_import_tree(proc)
    assert commands == [["taskkill", "/PID", "4321", "/T", "/F"]]
    assert proc.waited


def test_corrupt_pdf_rejected_before_model_preflight(tmp_path, monkeypatch):
    path = tmp_path / "corrupt.pdf"
    path.write_bytes(b"%PDF-not-a-real-file\x00\x01\x02")
    def forbidden():
        pytest.fail("corrupt document must not load the model")
    monkeypatch.setattr("core.cv_llm_runtime.ensure_cv_llm_ready", forbidden)
    with pytest.raises(cv.CvImportError, match="unreadable_cv"):
        cv.import_cv_docpick(path)


@pytest.mark.skipif(os.name == "nt", reason="Unix executable fixture; Windows runs actual frozen EXE")
def test_timeout_reaps_bootloader_descendant_and_releases_stderr(tmp_path):
    executable = tmp_path / "worker"
    pidfile = tmp_path / "child.pid"
    survived = tmp_path / "survived"
    child_code = f"import time; time.sleep(2); open({str(survived)!r},'w').write('alive'); time.sleep(60)"
    executable.write_text(
        f"#!{sys.executable}\nimport subprocess,time\n"
        f"p=subprocess.Popen([{sys.executable!r},'-c',{child_code!r}])\n"
        f"open({str(pidfile)!r},'w').write(str(p.pid))\n"
        "time.sleep(60)\n"
    )
    executable.chmod(0o755)
    with pytest.raises(RuntimeError, match="timed out"):
        _run_child_import(executable, tmp_path / "cv.pdf", tmp_path / "out.json",
                          local_appdata=tmp_path, timeout_s=1)
    assert int(pidfile.read_text()) > 0
    time.sleep(1.5)
    assert not survived.exists()
    (tmp_path / "out.json.stderr.txt").unlink()


def test_worker_exit_without_report_fails_immediately(tmp_path, monkeypatch):
    real_popen = subprocess.Popen
    monkeypatch.setattr(subprocess, "Popen", lambda _cmd, **kw: real_popen(
        [sys.executable, "-c", "raise SystemExit(7)"], **kw))
    with pytest.raises(RuntimeError, match="exit=7"):
        _run_child_import(Path(sys.executable), tmp_path / "cv.pdf", tmp_path / "out.json",
                          local_appdata=tmp_path, timeout_s=30)
