"""Cancel during a blocked child must end the process tree, once."""

from __future__ import annotations

import inspect
import json
import os
import sys
import threading
import time
from pathlib import Path

import pytest

from desktop.cv_import_supervisor import (
    CvImportSupervisor,
    _parent_memory_code,
    default_spawn,
)
from devops.peak_rss_harness import ContainedProcess, launch_contained
from devops.win_job_object import JOB_OBJECT_LIMIT_JOB_MEMORY, containment_limit_flags


def _blocker_source(ready: Path) -> str:
    return (
        "import os, pathlib, time\n"
        "pid = os.fork()\n"
        "if pid == 0:\n"
        "    time.sleep(180)\n"
        "    os._exit(0)\n"
        f"pathlib.Path({str(ready)!r}).write_text(str(pid), encoding='utf-8')\n"
        "time.sleep(180)\n"
    )


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def test_job_memory_limit_flag_is_off_without_a_cap() -> None:
    flags = containment_limit_flags(enforce_memory_bytes=None)
    assert flags & JOB_OBJECT_LIMIT_JOB_MEMORY == 0


def test_extract_spawn_arms_job_limit_at_the_child_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The Windows job limit is the child budget, the same number as the gate."""
    from core.cv_docpick_import import child_budget_for_app_private, job_enforce_memory_bytes

    seen: dict = {}

    def launch(argv, **kwargs):
        seen["kwargs"] = kwargs
        return object()

    app_private = 400_000_000
    budget = child_budget_for_app_private(app_private)
    monkeypatch.setenv("KARRIEREKRAKE_CV_APP_PRIVATE_BYTES", str(app_private))
    monkeypatch.setenv("KARRIEREKRAKE_CV_CHILD_BUDGET_BYTES", str(budget))
    monkeypatch.setattr("desktop.cv_import_supervisor.launch_contained", launch)
    default_spawn(Path("cv.pdf"), Path("out.json"))
    assert seen["kwargs"]["enforce_memory_bytes"] == budget
    assert seen["kwargs"]["enforce_memory_bytes"] == job_enforce_memory_bytes(
        child_budget=budget, app_private=app_private
    )
    assert seen["kwargs"]["enforce_memory_bytes"] == 3_300_000_000 - app_private


def test_terminate_mentions_job_object_and_killpg() -> None:
    src = inspect.getsource(ContainedProcess.terminate)
    assert "TerminateJobObject" in src
    assert "killpg" in src


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX killpg timing; Windows path is TerminateJobObject")
def test_cancel_during_blocked_call_kills_process_tree(tmp_path: Path) -> None:
    ready = tmp_path / "ready"
    proc = launch_contained([sys.executable, "-c", _blocker_source(ready)])
    try:
        deadline = time.monotonic() + 5
        while not ready.is_file():
            assert proc.poll() is None
            assert time.monotonic() < deadline
            time.sleep(0.01)
        grand = int(ready.read_text(encoding="utf-8"))
        assert proc.contains_pid(proc.pid)
        assert os.getpgid(grand) == proc.pgid
        t0 = time.monotonic()
        proc.terminate()
        while _alive(proc.pid) or _alive(grand):
            assert time.monotonic() - t0 < 3
            time.sleep(0.01)
        elapsed = time.monotonic() - t0
    finally:
        proc.close()
    assert elapsed < 2.0
    print(f"CANCEL_TREE_ELAPSED_S={elapsed:.4f}")


def _gguf_path() -> Path | None:
    candidate = Path("/tmp/karrierekrake-models/qwen3.5-4b/Qwen3.5-4B-Q4_K_M.gguf")
    if candidate.is_file():
        return candidate
    try:
        from core.cv_llm_runtime import resolve_cv_model_path

        return resolve_cv_model_path()
    except Exception:  # noqa: BLE001
        return None


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX killpg timing; Windows path is TerminateJobObject")
def test_cancel_during_inprocess_model_kills_child(tmp_path: Path) -> None:
    """Abort while llama-cpp is inside the process, not only during sleep."""
    model = _gguf_path()
    if model is None:
        pytest.skip("Qwen GGUF is not installed")
    ready = tmp_path / "started"
    script = (
        "import pathlib\n"
        "pathlib.Path(r'''"
        + str(ready)
        + "''').write_text('1', encoding='utf-8')\n"
        "from pathlib import Path\n"
        "from core.cv_llm_runtime import chat_completion_inprocess\n"
        "chat_completion_inprocess(\n"
        "    [{'role': 'user', 'content': 'Say hi in one word.'}],\n"
        f"    model_path=Path({str(model)!r}),\n"
        ")\n"
    )
    proc = launch_contained([sys.executable, "-c", script], cwd=str(Path(__file__).resolve().parents[1]))
    try:
        deadline = time.monotonic() + 180
        while not ready.is_file():
            assert proc.poll() is None, "child exited before the model call"
            assert time.monotonic() < deadline
            time.sleep(0.05)
        # Wait until anonymous RSS shows the weights are resident.
        from core.cv_docpick_import import _linux_rss_anon_bytes

        while _linux_rss_anon_bytes(proc.pid) < 1_500_000_000:
            assert proc.poll() is None
            assert time.monotonic() < deadline
            time.sleep(0.2)
        t0 = time.monotonic()
        proc.terminate()
        while _alive(proc.pid):
            assert time.monotonic() - t0 < 3
            time.sleep(0.01)
        elapsed = time.monotonic() - t0
    finally:
        if proc.poll() is None:
            proc.terminate()
        proc.close()
    assert elapsed < 2.0
    print(f"CANCEL_DURING_MODEL_ELAPSED_S={elapsed:.4f}")


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX killpg timing; Windows path is TerminateJobObject")
def test_supervisor_cancel_kills_contained_child(tmp_path: Path) -> None:
    ready = tmp_path / "ready"
    script = _blocker_source(ready)

    def spawn(_cv: Path, _out: Path):
        return launch_contained([sys.executable, "-c", script])

    sup = CvImportSupervisor(tmp_path / "cv.txt", spawn=spawn, timeout_s=30)
    holder: dict[str, float] = {}

    def cancel_when_blocked() -> None:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            proc = sup._proc
            if ready.is_file() and proc is not None:
                holder["t0"] = time.monotonic()
                sup.request_cancel()
                return
            time.sleep(0.01)

    threading.Thread(target=cancel_when_blocked, daemon=True).start()
    result = sup.run_once()
    assert result.kind == "cancelled"
    assert result.attempts == 1
    assert "t0" in holder
    elapsed = time.monotonic() - holder["t0"]
    grand = int(ready.read_text(encoding="utf-8"))
    assert not _alive(grand)
    assert elapsed < 3.0
    print(f"SUPERVISOR_CANCEL_ELAPSED_S={elapsed:.4f}")


@pytest.mark.parametrize(
    "kind",
    ["llm_prompt_too_long", "llm_output_truncated", "llm_timeout"],
)
def test_llm_fail_codes_spawn_once_without_auto_retry(tmp_path: Path, kind: str) -> None:
    """No automatic retry for any of the three codes.

    ``llm_prompt_too_long`` and ``llm_output_truncated`` are input-conditioned.
    ``llm_timeout`` depends on the machine and is not deterministic. A manual
    retry for that code is the UI PR.
    """
    calls: list[int] = []

    class _Done:
        def poll(self):
            return 1

        def terminate(self) -> None:
            return None

        def wait(self, timeout=None):
            return 1

        def close(self) -> None:
            return None

    def spawn(_cv: Path, out: Path):
        calls.append(1)
        out.write_text(
            json.dumps({"ok": False, "kind": kind, "message": kind, "parsed": None}),
            encoding="utf-8",
        )
        return _Done()

    sup = CvImportSupervisor(tmp_path / "cv.txt", spawn=spawn, timeout_s=5)
    result = sup.run_once()
    assert result.kind == kind
    assert result.attempts == 1
    assert result.message == kind
    assert calls == [1]


def test_child_stores_code_only_and_does_not_label_timeout_deterministic(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    from desktop.cv_import_child import _fail

    with caplog.at_level("WARNING"):
        assert (
            _fail(
                tmp_path / "timeout.json",
                kind="llm_timeout",
                message="elapsed",
                decision=None,
            )
            == 1
        )
    text = (tmp_path / "timeout.json").read_text(encoding="utf-8")
    payload = json.loads(text)
    assert payload["kind"] == "llm_timeout"
    assert payload["message"] == "llm_timeout"
    assert "machine_dependent" in caplog.text
    assert "deterministic" not in caplog.text

    caplog.clear()
    with caplog.at_level("WARNING"):
        _fail(
            tmp_path / "long.json",
            kind="llm_prompt_too_long",
            message="room",
            decision=None,
        )
        _fail(
            tmp_path / "trunc.json",
            kind="llm_output_truncated",
            message="length",
            decision=None,
        )
    assert caplog.text.count("input_conditioned") == 2
    assert "deterministic" not in caplog.text


def test_parent_zero_anon_sample_is_not_over_and_not_a_pass(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    class _Pid:
        pid = os.getpid()

    monkeypatch.setattr("desktop.cv_import_supervisor.sys.platform", "linux")
    monkeypatch.setattr("core.cv_docpick_import._linux_rss_anon_bytes", lambda pid: 0)
    with caplog.at_level("ERROR"):
        assert _parent_memory_code(_Pid(), child_budget=1_000) is None
    assert "unmeasured" in caplog.text
    assert "not a pass" in caplog.text


def test_high_app_share_does_not_start_the_child(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    spawned: list[int] = []

    def spawn(*_args, **_kwargs):
        spawned.append(1)
        raise AssertionError("child started")

    monkeypatch.setattr(
        "desktop.cv_import_supervisor._read_app_private_bytes",
        lambda: 3_300_000_000,
    )
    with caplog.at_level("INFO"):
        result = CvImportSupervisor(Path("cv.pdf"), spawn=spawn).run_once()
    assert result.kind == "memory_budget_app_share"
    assert result.attempts == 1
    assert spawned == []
    assert "app_private=3300000000" in caplog.text
    assert "child_budget=0" in caplog.text


def test_unmeasured_app_private_does_not_start_the_child(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "desktop.cv_import_supervisor._read_app_private_bytes",
        lambda: 0,
    )
    result = CvImportSupervisor(Path("cv.pdf"), spawn=lambda *_a, **_k: None).run_once()
    assert result.kind == "peak_rss_unmeasured"
    assert result.attempts == 1


def test_parent_sample_over_current_budget_is_app_share(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from core.cv_docpick_import import (
        CV_IMPORT_CHILD_MIN_AFTER_LOAD_BYTES,
        fresh_app_child_budget_bytes,
    )

    sample = CV_IMPORT_CHILD_MIN_AFTER_LOAD_BYTES + 1
    assert sample < fresh_app_child_budget_bytes()

    class _Pid:
        pid = os.getpid()

    monkeypatch.setattr("desktop.cv_import_supervisor.sys.platform", "linux")
    monkeypatch.setattr(
        "core.cv_docpick_import._linux_rss_anon_bytes",
        lambda pid: sample,
    )
    assert (
        _parent_memory_code(_Pid(), child_budget=CV_IMPORT_CHILD_MIN_AFTER_LOAD_BYTES)
        == "memory_budget_app_share"
    )


def test_parent_sample_over_fresh_budget_is_peak_rss(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from core.cv_docpick_import import fresh_app_child_budget_bytes

    fresh = fresh_app_child_budget_bytes()

    class _Pid:
        pid = os.getpid()

    monkeypatch.setattr("desktop.cv_import_supervisor.sys.platform", "linux")
    monkeypatch.setattr(
        "core.cv_docpick_import._linux_rss_anon_bytes",
        lambda pid: fresh + 1,
    )
    assert _parent_memory_code(_Pid(), child_budget=fresh) == "peak_rss_exceeded"


def test_spawn_inherits_budget_and_parent_does_not_keep_it(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, str | None] = {}

    def spawn(cv_path: Path, out_path: Path):
        seen["app"] = os.environ.get("KARRIEREKRAKE_CV_APP_PRIVATE_BYTES")
        seen["budget"] = os.environ.get("KARRIEREKRAKE_CV_CHILD_BUDGET_BYTES")

        class _Done:
            pid = os.getpid()

            def poll(self):
                return 0

            def terminate(self):
                return None

        return _Done()

    monkeypatch.setattr(
        "desktop.cv_import_supervisor._read_app_private_bytes",
        lambda: 200_000_000,
    )
    monkeypatch.setattr(
        "desktop.cv_import_supervisor._read_payload",
        lambda _path: {"ok": True, "parsed": {"personal": {}}},
    )
    os.environ.pop("KARRIEREKRAKE_CV_APP_PRIVATE_BYTES", None)
    os.environ.pop("KARRIEREKRAKE_CV_CHILD_BUDGET_BYTES", None)
    result = CvImportSupervisor(Path("cv.pdf"), spawn=spawn).run_once()
    assert result.ok is True
    assert seen["app"] == "200000000"
    assert seen["budget"] == str(3_300_000_000 - 200_000_000)
    assert os.environ.get("KARRIEREKRAKE_CV_APP_PRIVATE_BYTES") is None
    assert os.environ.get("KARRIEREKRAKE_CV_CHILD_BUDGET_BYTES") is None


def test_memory_codes_log_without_new_user_copy(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    from desktop.cv_import_child import _fail

    with caplog.at_level("WARNING"):
        assert (
            _fail(
                tmp_path / "share.json",
                kind="memory_budget_app_share",
                message="detail",
                decision=None,
            )
            == 1
        )
    payload = json.loads((tmp_path / "share.json").read_text(encoding="utf-8"))
    assert payload["kind"] == "memory_budget_app_share"
    assert payload["message"] == "memory_budget_app_share"
    assert "app_share" in caplog.text
    assert "deterministic" not in caplog.text

    caplog.clear()
    with caplog.at_level("WARNING"):
        _fail(
            tmp_path / "peak.json",
            kind="peak_rss_exceeded",
            message="detail",
            decision=None,
        )
    peak = json.loads((tmp_path / "peak.json").read_text(encoding="utf-8"))
    assert peak["kind"] == "peak_rss_exceeded"
    assert peak["message"] != "memory_budget_app_share"
    assert "input_conditioned" in caplog.text
    assert "deterministic" not in caplog.text


def _limit_death(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    *,
    app_private: int,
    code: int,
    port_hit: bool,
) -> str:
    monkeypatch.setattr(
        "desktop.cv_import_supervisor._read_app_private_bytes",
        lambda: app_private,
    )

    class _Done:
        def poll(self):
            return code

        def terminate(self) -> None:
            return None

        def close(self) -> None:
            return None

        def job_memory_limit_signaled(self) -> bool:
            return port_hit

    def spawn(_cv: Path, out: Path):
        out.write_text(
            json.dumps(
                {
                    "ok": False,
                    "kind": "llm_extract_failed",
                    "message": "llm_extract_failed",
                }
            ),
            encoding="utf-8",
        )
        return _Done()

    with caplog.at_level("ERROR"):
        result = CvImportSupervisor(tmp_path / "cv.pdf", spawn=spawn, timeout_s=30).run_once()
    return result.kind


def test_job_memory_limit_maps_like_the_gate(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Completion-port hit and the exit-code fallback use the gate's split."""
    from core.cv_docpick_import import CV_IMPORT_FRESH_APP_PRIVATE_BYTES
    from devops.win_job_object import (
        JOB_OBJECT_MSG_JOB_MEMORY_LIMIT,
        is_job_memory_limit_message,
    )

    assert is_job_memory_limit_message(JOB_OBJECT_MSG_JOB_MEMORY_LIMIT) is True
    assert is_job_memory_limit_message(1) is False

    fresh_app = CV_IMPORT_FRESH_APP_PRIVATE_BYTES
    kind = _limit_death(
        monkeypatch,
        tmp_path,
        caplog,
        app_private=fresh_app,
        code=1,
        port_hit=True,
    )
    assert kind == "peak_rss_exceeded"

    caplog.clear()
    smaller_budget = 2_000_000_000
    kind = _limit_death(
        monkeypatch,
        tmp_path,
        caplog,
        app_private=3_300_000_000 - smaller_budget,
        code=1,
        port_hit=True,
    )
    assert kind == "memory_budget_app_share"
    assert "job_memory_limit_hit" not in caplog.text

    caplog.clear()
    kind = _limit_death(
        monkeypatch,
        tmp_path,
        caplog,
        app_private=fresh_app,
        code=0xC0000005,
        port_hit=False,
    )
    assert kind == "peak_rss_exceeded"
    assert "job_memory_limit_hit" in caplog.text

    caplog.clear()
    kind = _limit_death(
        monkeypatch,
        tmp_path,
        caplog,
        app_private=3_300_000_000 - smaller_budget,
        code=-1073741801,  # signed 0xC0000017
        port_hit=False,
    )
    assert kind == "memory_budget_app_share"
    assert "job_memory_limit_hit" in caplog.text

    caplog.clear()
    kind = _limit_death(
        monkeypatch,
        tmp_path,
        caplog,
        app_private=fresh_app,
        code=1,
        port_hit=False,
    )
    assert kind == "llm_extract_failed"
    assert "job_memory_limit_hit" not in caplog.text


def test_generation_timeout_event_matches_supervisor_once(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from core.cv_phase_events import emit_generation_timeout, reset_generation_phase_events

    monkeypatch.setattr(
        "desktop.cv_import_supervisor._read_app_private_bytes",
        lambda: 200_000_000,
    )
    monkeypatch.setattr(
        "desktop.cv_import_supervisor._parent_anon_sample",
        lambda *_a, **_k: None,
    )
    reset_generation_phase_events()
    seen: dict[str, object] = {}
    progress_lines: list[str] = []

    def spawn(_cv: Path, out: Path):
        seen["timeout_env"] = os.environ.get("KARRIEREKRAKE_CV_IMPORT_TIMEOUT_S")
        seen["first"] = emit_generation_timeout()
        seen["second"] = emit_generation_timeout()
        out.write_text(
            json.dumps({"ok": True, "parsed": {"personal": {}}}),
            encoding="utf-8",
        )

        class _Done:
            def poll(self):
                return 0

            def terminate(self) -> None:
                return None

            def close(self) -> None:
                return None

        return _Done()

    supervisor = CvImportSupervisor(tmp_path / "cv.pdf", spawn=spawn, timeout_s=95)
    result = supervisor.run_once(progress=progress_lines.append)
    assert result.ok is True
    assert seen["timeout_env"] == str(supervisor.timeout_s)
    assert seen["second"] is None
    timeouts = []
    for line in progress_lines:
        if not line.startswith("{"):
            continue
        event = json.loads(line)
        if "timeout_s" in event:
            timeouts.append(event["timeout_s"])
    assert timeouts == [int(supervisor.timeout_s)]
    from core.cv_phase_events import absorb_phase_message

    timeout_s = None
    tokens_done = None
    timeout_s_final = None
    for line in progress_lines:
        timeout_s, tokens_done, timeout_s_final = absorb_phase_message(
            line,
            timeout_s=timeout_s,
            tokens_done=tokens_done,
            timeout_s_final=timeout_s_final,
        )
    assert timeout_s == int(supervisor.timeout_s)
    assert tokens_done is None
    assert timeout_s_final is None


def test_supervisor_adopts_the_child_timeout_event(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The formula event tightens the outer ceiling. No second token count."""
    monkeypatch.delenv("KARRIEREKRAKE_CV_IMPORT_TIMEOUT_S", raising=False)
    monkeypatch.setattr("core.cv_docpick_import.CV_IMPORT_TIMEOUT_CEILING_S", 3.0)
    monkeypatch.setattr(
        "desktop.cv_import_supervisor._read_app_private_bytes",
        lambda: 200_000_000,
    )
    monkeypatch.setattr(
        "desktop.cv_import_supervisor._parent_anon_sample",
        lambda *_a, **_k: None,
    )

    def spawn(_cv: Path, _out: Path):
        path = os.environ["KARRIEREKRAKE_CV_PHASE_EVENTS"]
        Path(path).write_text(
            '{"phase":"generation","timeout_s":1}\n',
            encoding="utf-8",
        )

        class _Hang:
            def poll(self):
                return None

            def terminate(self) -> None:
                return None

            def close(self) -> None:
                return None

            def job_memory_limit_signaled(self) -> bool:
                return False

        return _Hang()

    t0 = time.monotonic()
    result = CvImportSupervisor(tmp_path / "cv.pdf", spawn=spawn).run_once()
    elapsed = time.monotonic() - t0
    assert result.kind == "llm_timeout"
    assert elapsed < 2.0


def _fresh_app_log(tmp_path: Path):
    """Point the app logger at a new file and return ``(logger, restore)``."""
    import logging

    from core.logging import setup_logging

    log = logging.getLogger("karrierekrake")
    saved_handlers = list(log.handlers)
    saved_level = log.level
    for handler in saved_handlers:
        log.removeHandler(handler)
    setup_logging(tmp_path)

    def restore() -> None:
        for handler in list(log.handlers):
            handler.flush()
            log.removeHandler(handler)
            handler.close()
        log.setLevel(saved_level)
        for handler in saved_handlers:
            log.addHandler(handler)

    return log, restore


def test_fake_model_import_writes_each_diagnostic_once(tmp_path: Path, monkeypatch):
    """Child diagnostics arrive in the app log, one line each, via the phase pipe."""
    from core.cv_docpick_import import note_import_started, reset_import_timeout
    from core.cv_llm_runtime import chat_completion_inprocess

    _log, restore = _fresh_app_log(tmp_path)
    try:
        monkeypatch.delenv("KARRIEREKRAKE_CV_IMPORT_TIMEOUT_S", raising=False)
        monkeypatch.setattr(
            "desktop.cv_import_supervisor._read_app_private_bytes",
            lambda: 167_272_448,
        )
        monkeypatch.setattr(
            "desktop.cv_import_supervisor._parent_anon_sample",
            lambda *_a, **_k: None,
        )
        monkeypatch.setattr("core.cv_docpick_import._self_rss_bytes", lambda: 50_000_000)
        reset_import_timeout()
        note_import_started(time.monotonic())

        class _Fake:
            def __init__(self, *args, **kwargs):
                self.prompt_tokens = 100

            def count_chat_tokens(self, messages):
                assert messages
                return self.prompt_tokens

            def create_chat_completion(self, **kwargs):
                raise RuntimeError("stop after the diagnostic lines")

        monkeypatch.setattr("core.cv_llm_runtime._llama_cls", lambda: _Fake)
        progress: list[str] = []

        def spawn(_cv: Path, out: Path):
            try:
                chat_completion_inprocess(
                    [{"role": "user", "content": "x"}],
                    model_path=Path("unused.gguf"),
                )
            except RuntimeError:
                pass
            out.write_text(
                json.dumps(
                    {
                        "ok": False,
                        "kind": "llm_extract_failed",
                        "message": "llm_extract_failed",
                        "parsed": None,
                    }
                ),
                encoding="utf-8",
            )

            class _Done:
                def poll(self):
                    return 1

                def terminate(self) -> None:
                    return None

                def close(self) -> None:
                    return None

                def job_memory_limit_signaled(self) -> bool:
                    return False

            return _Done()

        result = CvImportSupervisor(
            tmp_path / "cv.pdf", spawn=spawn, timeout_s=30
        ).run_once(progress=progress.append)
        assert result.kind == "llm_extract_failed"
        for handler in _log.handlers:
            handler.flush()
        text = (tmp_path / "karrierekrake.log").read_text(encoding="utf-8")
        lines = text.splitlines()
        assert len([ln for ln in lines if "cv_llm_load" in ln]) == 1
        assert len([ln for ln in lines if "memory_shares" in ln]) == 1
        assert len([ln for ln in lines if "cv_llm_inprocess" in ln and "n_threads=" in ln]) == 1
        assert len([ln for ln in lines if "cv_llm_rates " in ln]) == 1
        assert all("cv_llm_load" not in ln and "memory_shares" not in ln for ln in progress)
    finally:
        restore()


def test_timeout_and_cancel_write_the_app_log(tmp_path: Path, monkeypatch):
    import subprocess

    _log, restore = _fresh_app_log(tmp_path)
    try:
        monkeypatch.setattr(
            "desktop.cv_import_supervisor._read_app_private_bytes",
            lambda: 167_272_448,
        )
        monkeypatch.setattr(
            "desktop.cv_import_supervisor._parent_anon_sample",
            lambda *_a, **_k: None,
        )

        def spawn_sleep(_cv: Path, _out: Path):
            return subprocess.Popen(["sleep", "30"])

        timed = CvImportSupervisor(
            tmp_path / "cv.pdf", spawn=spawn_sleep, timeout_s=0.25
        ).run_once()
        assert timed.kind == "llm_timeout"

        started = threading.Event()

        def spawn_hang(_cv: Path, _out: Path):
            proc = subprocess.Popen(["sleep", "30"])
            started.set()
            return proc

        supervisor = CvImportSupervisor(
            tmp_path / "cv.pdf", spawn=spawn_hang, timeout_s=30
        )

        def _run() -> None:
            supervisor.run_once()

        thread = threading.Thread(target=_run)
        thread.start()
        assert started.wait(3)
        time.sleep(0.15)
        supervisor.request_cancel()
        thread.join(5)
        assert not thread.is_alive()
        for handler in _log.handlers:
            handler.flush()
        text = (tmp_path / "karrierekrake.log").read_text(encoding="utf-8")
        assert len([ln for ln in text.splitlines() if "llm_timeout" in ln]) == 1
        cancel_lines = [ln for ln in text.splitlines() if "cv_import cancelled at=" in ln]
        assert len(cancel_lines) == 1
        assert "child_ended_ms=" in cancel_lines[0]
    finally:
        restore()


def _fake_clock(monkeypatch: pytest.MonkeyPatch) -> dict[str, float]:
    """Advance one second per supervisor wake. No wall-clock wait."""
    clock = {"t": 0.0}
    monkeypatch.setattr("desktop.cv_import_supervisor._monotonic", lambda: clock["t"])
    monkeypatch.setattr(
        CvImportSupervisor,
        "_pause",
        lambda _self, _timeout: clock.__setitem__("t", clock["t"] + 1.0),
    )
    monkeypatch.setattr(
        "desktop.cv_import_supervisor._read_app_private_bytes",
        lambda: 167_272_448,
    )
    monkeypatch.delenv("KARRIEREKRAKE_CV_IMPORT_TIMEOUT_S", raising=False)
    return clock


class _ScriptedChild:
    """Phase events follow the fake clock. ``poll`` does not sleep."""

    def __init__(
        self,
        out: Path,
        clock: dict[str, float],
        *,
        timeout_s: int,
        max_tokens: int,
        first_token_at: float,
        token_every: float,
        done_at: float | None,
        last_token_at: float | None,
        n_prompt: int = 10,
        prompt_at: float | None = None,
        prompt_every: float = 1.0,
        prompt_block_s: float = 1.0,
        prompt_batch: int = 512,
    ) -> None:
        self._out = out
        self._clock = clock
        self._timeout_s = timeout_s
        self._max_tokens = max_tokens
        self._every = token_every
        self._done_at = done_at
        self._last_token_at = last_token_at
        self._n_prompt = n_prompt
        self._prompt_at = prompt_at
        self._prompt_every = prompt_every
        self._prompt_block_s = prompt_block_s
        self._prompt_batch = prompt_batch
        self._phase = Path(os.environ["KARRIEREKRAKE_CV_PHASE_EVENTS"])
        self._header = False
        self._tokens = 0
        self._prompt_done = 0
        self._next = first_token_at
        self._next_prompt = prompt_at if prompt_at is not None else 0.0

    def poll(self):
        now = self._clock["t"]
        if now > 2000:
            return 1
        if not self._header:
            diag = (
                "cv_llm_inprocess n_ctx=4096 n_threads=4 n_threads_batch=4 "
                "n_prompt=%s max_tokens=%s" % (self._n_prompt, self._max_tokens)
            )
            self._phase.write_text(
                json.dumps({"diag": diag, "level": "info"}, separators=(",", ":"))
                + "\n"
                + json.dumps(
                    {"phase": "generation", "timeout_s": self._timeout_s},
                    separators=(",", ":"),
                )
                + "\n",
                encoding="utf-8",
            )
            self._header = True
        if self._prompt_at is not None:
            while self._prompt_done < self._n_prompt and now >= self._next_prompt:
                step = min(self._prompt_batch, self._n_prompt - self._prompt_done)
                self._prompt_done += step
                with self._phase.open("a", encoding="utf-8") as handle:
                    handle.write(
                        json.dumps(
                            {
                                "phase": "prompt",
                                "prompt_tokens_done": self._prompt_done,
                                "t_mono": self._next_prompt,
                                "block_s": self._prompt_block_s,
                            },
                            separators=(",", ":"),
                        )
                        + "\n"
                    )
                self._next_prompt += self._prompt_every
        while self._tokens < self._max_tokens and now >= self._next:
            if self._last_token_at is not None and self._next > self._last_token_at:
                break
            self._tokens += 1
            with self._phase.open("a", encoding="utf-8") as handle:
                handle.write(
                    json.dumps(
                        {"phase": "generation", "tokens_done": self._tokens},
                        separators=(",", ":"),
                    )
                    + "\n"
                )
            self._next += self._every
        if self._done_at is not None and now >= self._done_at:
            self._out.write_text(
                json.dumps({"ok": True, "parsed": {"personal": {}}}),
                encoding="utf-8",
            )
            return 0
        return None

    def terminate(self) -> None:
        return None

    def close(self) -> None:
        return None

    def job_memory_limit_signaled(self) -> bool:
        return False


def _finals(lines: list[str]) -> list[int]:
    found = []
    for line in lines:
        if not line.startswith("{"):
            continue
        event = json.loads(line)
        if "timeout_s_final" in event:
            found.append(int(event["timeout_s_final"]))
    return found


def test_deadline_changes_once_and_never_shrinks() -> None:
    """The measured rate may raise the deadline once. It cannot lower it."""
    from core.cv_import_deadline import ImportDeadlineWatch

    watch = ImportDeadlineWatch(
        initial_s=180,
        started_at=0,
        env_locked=False,
        buffer_s=60,
        ceiling_s=900,
    )
    watch.note_max_tokens(1000)
    assert watch.note_tokens(1, 10) is None
    # 64 tokens one second into generation recalculates under the initial 180 s.
    # The generation step is the last recalculation, so the current deadline
    # is still announced once.
    assert watch.note_tokens(64, 11) == 180
    assert watch.limit_s == 180
    assert watch.revisions == 1
    assert watch.timeout_s_final == 180
    assert watch.note_tokens(65, 80) is None
    assert watch.limit_s == 180
    assert watch.revisions == 1

    raised = ImportDeadlineWatch(
        initial_s=180,
        started_at=0,
        env_locked=False,
        buffer_s=60,
        ceiling_s=900,
    )
    raised.note_max_tokens(400)
    assert raised.note_tokens(1, 20) is None
    assert raised.note_tokens(10, 25) is None
    assert raised.limit_s == 180
    final = raised.note_tokens(11, 35)
    assert final is not None
    assert raised.revisions == 1
    assert 180 < raised.limit_s <= 900
    assert final >= 180
    assert raised.note_tokens(12, 36) is None
    assert raised.revisions == 1
    assert raised.timeout_s_final == final


def test_env_override_skips_deadline_refinement() -> None:
    from core.cv_import_deadline import ImportDeadlineWatch

    watch = ImportDeadlineWatch(
        initial_s=50,
        started_at=0,
        env_locked=True,
        buffer_s=60,
        ceiling_s=900,
    )
    watch.note_max_tokens(500)
    watch.note_tokens(1, 1)
    assert watch.note_tokens(80, 20) is None
    assert watch.limit_s == 50
    assert watch.timeout_s_final is None
    assert watch.revisions == 0
    assert watch.failure(50) is None
    assert watch.failure(50.01) == "deadline"


def test_stall_after_first_token_and_deadline_before_it() -> None:
    from core.cv_import_deadline import ImportDeadlineWatch

    stall = ImportDeadlineWatch(
        initial_s=500,
        started_at=0,
        env_locked=False,
        buffer_s=60,
        ceiling_s=900,
    )
    assert stall.failure(100) is None
    stall.note_tokens(1, 10)
    assert stall.failure(69.9) is None
    assert stall.failure(70) == "stall"

    waiting = ImportDeadlineWatch(
        initial_s=180,
        started_at=0,
        env_locked=False,
        buffer_s=60,
        ceiling_s=900,
    )
    assert waiting.failure(180) is None
    assert waiting.failure(180.01) == "deadline"


def test_slow_fake_child_past_the_initial_deadline_is_not_killed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Steady tokens past the formula deadline and under 900 s finish."""
    clock = _fake_clock(monkeypatch)
    progress: list[str] = []

    def spawn(_cv: Path, out: Path):
        return _ScriptedChild(
            out,
            clock,
            timeout_s=180,
            max_tokens=200,
            first_token_at=20,
            token_every=1,
            done_at=220,
            last_token_at=None,
        )

    result = CvImportSupervisor(tmp_path / "cv.pdf", spawn=spawn).run_once(
        progress=progress.append
    )
    assert result.ok is True
    assert clock["t"] > 180
    assert clock["t"] < 900
    finals = _finals(progress)
    assert len(finals) == 1
    assert 180 <= finals[0] <= 900


def test_token_stall_is_llm_timeout_in_the_parent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    clock = _fake_clock(monkeypatch)
    progress: list[str] = []

    def spawn(_cv: Path, out: Path):
        return _ScriptedChild(
            out,
            clock,
            timeout_s=500,
            max_tokens=200,
            first_token_at=10,
            token_every=1,
            done_at=None,
            last_token_at=10,
        )

    with caplog.at_level("ERROR", logger="desktop.cv_import_supervisor"):
        result = CvImportSupervisor(tmp_path / "cv.pdf", spawn=spawn).run_once(
            progress=progress.append
        )
    assert result.kind == "llm_timeout"
    assert result.message == "llm_timeout"
    assert result.reason == "stall"
    assert clock["t"] < 500
    assert "reason=stall" in caplog.text
    assert "reason=deadline" not in caplog.text
    assert _finals(progress) == []


def test_deadline_before_the_first_token(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    clock = _fake_clock(monkeypatch)

    def spawn(_cv: Path, out: Path):
        return _ScriptedChild(
            out,
            clock,
            timeout_s=180,
            max_tokens=200,
            first_token_at=10_000,
            token_every=1,
            done_at=None,
            last_token_at=None,
        )

    with caplog.at_level("ERROR", logger="desktop.cv_import_supervisor"):
        result = CvImportSupervisor(tmp_path / "cv.pdf", spawn=spawn).run_once()
    assert result.kind == "llm_timeout"
    assert result.message == "llm_timeout"
    assert result.reason == "deadline"
    assert clock["t"] > 180
    assert clock["t"] < 200
    assert "reason=deadline" in caplog.text
    assert "reason=stall" not in caplog.text


def test_env_timeout_is_not_recalculated(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    clock = _fake_clock(monkeypatch)
    monkeypatch.setenv("KARRIEREKRAKE_CV_IMPORT_TIMEOUT_S", "40")
    progress: list[str] = []

    def spawn(_cv: Path, out: Path):
        return _ScriptedChild(
            out,
            clock,
            timeout_s=40,
            max_tokens=400,
            first_token_at=1,
            token_every=1,
            done_at=None,
            last_token_at=None,
        )

    with caplog.at_level("ERROR", logger="desktop.cv_import_supervisor"):
        result = CvImportSupervisor(tmp_path / "cv.pdf", spawn=spawn).run_once(
            progress=progress.append
        )
    assert result.kind == "llm_timeout"
    assert result.message == "llm_timeout"
    assert result.reason == "deadline"
    assert clock["t"] > 40
    assert clock["t"] < 80
    assert "reason=deadline" in caplog.text
    assert _finals(progress) == []


def test_prompt_stall_threshold_scales_with_the_first_block() -> None:
    """A long first block raises the prompt stall gap above 60 s."""
    from core.cv_import_deadline import ImportDeadlineWatch

    watch = ImportDeadlineWatch(
        initial_s=900,
        started_at=0,
        env_locked=False,
        buffer_s=60,
        ceiling_s=900,
    )
    assert watch.failure(100) is None
    watch.note_max_tokens(100)
    watch.note_n_prompt(2048)
    watch.note_prompt(512, 25, t_mono=25, block_s=25)
    assert watch.failure(25 + 60) is None
    assert watch.failure(25 + 74.9) is None
    assert watch.failure(25 + 75) == "stall"

    after_token = ImportDeadlineWatch(
        initial_s=900,
        started_at=0,
        env_locked=False,
        buffer_s=60,
        ceiling_s=900,
    )
    after_token.note_prompt(512, 10, block_s=30)
    after_token.note_tokens(1, 20)
    assert after_token.failure(20 + 59.9) is None
    assert after_token.failure(20 + 60) == "stall"


def test_two_recalculations_emit_timeout_s_final_once() -> None:
    """Prompt raises the deadline quietly. Generation announces it once."""
    from core.cv_import_deadline import ImportDeadlineWatch

    watch = ImportDeadlineWatch(
        initial_s=180,
        started_at=0,
        env_locked=False,
        buffer_s=60,
        ceiling_s=900,
    )
    watch.note_max_tokens(1000)
    watch.note_n_prompt(1024)
    watch.note_prompt(512, 10, t_mono=10, block_s=10)
    assert watch.revisions == 1
    assert watch.timeout_s_final is None
    assert watch.limit_s > 180
    prompt_limit = watch.limit_s
    assert watch.note_tokens(1, 30) is None
    final = watch.note_tokens(64, 90)
    assert final is not None
    assert watch.revisions == 2
    assert watch.limit_s >= prompt_limit
    assert watch.timeout_s_final == final
    assert watch.note_tokens(65, 91) is None
    assert watch.revisions == 2
    assert watch.timeout_s_final == final


def test_throttled_token_stamp_is_not_a_stall_after_59s() -> None:
    """Tokens 0.9 s apart, then 59 s, use the real token time."""
    from core.cv_import_deadline import ImportDeadlineWatch
    from core.cv_phase_events import TokenProgressThrottle

    throttle = TokenProgressThrottle()
    first = throttle.consider(tokens_done=1, now=0.0, t_mono=0.0)
    assert first is not None
    assert throttle.consider(tokens_done=2, now=0.9, t_mono=0.9) is None
    assert throttle.flush(0.99) is None
    flushed = throttle.flush(1.0)
    assert flushed is not None
    assert flushed["tokens_done"] == 2
    assert flushed["t_mono"] == 0.9

    watch = ImportDeadlineWatch(
        initial_s=900,
        started_at=0,
        env_locked=False,
        buffer_s=60,
        ceiling_s=900,
    )
    watch.note_tokens(int(first["tokens_done"]), 0.0, t_mono=float(first["t_mono"]))
    watch.note_tokens(
        int(flushed["tokens_done"]), 1.0, t_mono=float(flushed["t_mono"])
    )
    assert watch.failure(0.9 + 59) is None
    assert watch.failure(60.0) is None
    assert watch.failure(0.9 + 60) == "stall"


def test_slow_prompt_blocks_are_not_aborted(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Steady prompt blocks and no tokens pass the initial deadline."""
    clock = _fake_clock(monkeypatch)
    progress: list[str] = []

    def spawn(_cv: Path, out: Path):
        return _ScriptedChild(
            out,
            clock,
            timeout_s=180,
            max_tokens=2000,
            first_token_at=10_000,
            token_every=1,
            done_at=200,
            last_token_at=None,
            n_prompt=2048,
            prompt_at=30,
            prompt_every=40,
            prompt_block_s=30,
            prompt_batch=512,
        )

    result = CvImportSupervisor(tmp_path / "cv.pdf", spawn=spawn).run_once(
        progress=progress.append
    )
    assert result.ok is True
    assert clock["t"] > 180
    assert clock["t"] < 900
    assert _finals(progress) == []


def test_timeout_s_final_once_after_prompt_and_generation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    clock = _fake_clock(monkeypatch)
    progress: list[str] = []

    def spawn(_cv: Path, out: Path):
        return _ScriptedChild(
            out,
            clock,
            timeout_s=180,
            max_tokens=400,
            first_token_at=40,
            token_every=1,
            done_at=160,
            last_token_at=None,
            n_prompt=1024,
            prompt_at=10,
            prompt_every=10,
            prompt_block_s=10,
            prompt_batch=512,
        )

    result = CvImportSupervisor(tmp_path / "cv.pdf", spawn=spawn).run_once(
        progress=progress.append
    )
    assert result.ok is True
    finals = _finals(progress)
    assert len(finals) == 1
    assert 180 <= finals[0] <= 900
    final_at = next(i for i, line in enumerate(progress) if "timeout_s_final" in line)
    assert any("prompt_tokens_done" in line for line in progress[:final_at])
    assert any("tokens_done" in line for line in progress[:final_at])


def test_cancel_is_noticed_within_100ms(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A fake child is cancelled in under 100 ms. The event wakes the wait."""
    monkeypatch.setattr(
        "desktop.cv_import_supervisor._read_app_private_bytes",
        lambda: 167_272_448,
    )
    monkeypatch.setattr(
        "desktop.cv_import_supervisor._parent_anon_sample",
        lambda *_a, **_k: None,
    )
    monkeypatch.delenv("KARRIEREKRAKE_CV_IMPORT_TIMEOUT_S", raising=False)
    entered = threading.Event()

    class _Hang:
        def poll(self):
            entered.set()
            return None

        def terminate(self) -> None:
            return None

        def wait(self, timeout=None):
            return None

        def close(self) -> None:
            return None

    holder: dict = {}
    supervisor = CvImportSupervisor(tmp_path / "cv.pdf", spawn=lambda _c, _o: _Hang())

    def _run() -> None:
        holder["result"] = supervisor.run_once()

    thread = threading.Thread(target=_run)
    thread.start()
    assert entered.wait(2)
    time.sleep(0.02)
    started = time.perf_counter()
    supervisor.request_cancel()
    thread.join(1)
    elapsed = time.perf_counter() - started
    assert not thread.is_alive()
    assert holder["result"].kind == "cancelled"
    assert elapsed < 0.1


def test_wait_loop_stays_under_five_iterations_per_second(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A running child wakes the parent at most five times a second."""
    clock = {"t": 0.0}
    waits: list[float] = []
    polls: list[float] = []
    monkeypatch.setattr("desktop.cv_import_supervisor._monotonic", lambda: clock["t"])
    monkeypatch.setattr(
        "desktop.cv_import_supervisor._read_app_private_bytes",
        lambda: 167_272_448,
    )
    monkeypatch.setattr(
        "desktop.cv_import_supervisor._parent_anon_sample",
        lambda *_a, **_k: None,
    )
    monkeypatch.delenv("KARRIEREKRAKE_CV_IMPORT_TIMEOUT_S", raising=False)

    def _pause(_self, timeout: float) -> None:
        waits.append(float(timeout))
        clock["t"] += float(timeout)

    monkeypatch.setattr(CvImportSupervisor, "_pause", _pause)

    class _Hang:
        def poll(self):
            polls.append(clock["t"])
            if clock["t"] >= 1.0:
                return 0
            return None

        def terminate(self) -> None:
            return None

        def wait(self, timeout=None):
            return 0

        def close(self) -> None:
            return None

    CvImportSupervisor(tmp_path / "cv.pdf", spawn=lambda _c, _o: _Hang()).run_once()
    running = [t for t in polls if t < 1.0]
    assert running
    assert len(running) <= 5
    assert waits
    assert max(waits) <= 0.25
    assert min(waits) > 0


def test_smaps_interval_stretches_only_above_one_percent_of_a_core() -> None:
    from desktop.cv_import_supervisor import _anon_interval_s

    # Fewer than three reads do not decide, including one slow read.
    assert _anon_interval_s([35e-6], elapsed_s=2.0, current_s=2.0) == 2.0
    assert _anon_interval_s([0.036], elapsed_s=2.0, current_s=2.0) == 2.0
    # Median 14 ms at 2 s is 0.7% of one core.
    assert (
        _anon_interval_s([0.014, 0.014, 0.036], elapsed_s=4.0, current_s=2.0) == 2.0
    )
    # Median 30 ms at 2 s is 1.5% of one core.
    assert (
        _anon_interval_s([0.030, 0.030, 0.030], elapsed_s=6.0, current_s=2.0) == 5.0
    )
    assert (
        _anon_interval_s([0.060, 0.060, 0.060], elapsed_s=15.0, current_s=5.0) == 5.0
    )


def test_smaps_rollup_cost_is_logged_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    clock = _fake_clock(monkeypatch)
    monkeypatch.setattr(
        "core.cv_docpick_import._linux_rss_anon_bytes",
        lambda _pid: 4096,
    )

    class _Pid:
        pid = 4242

        def poll(self):
            if clock["t"] >= 5:
                return 0
            return None

        def terminate(self) -> None:
            return None

        def wait(self, timeout=None):
            return 0

        def close(self) -> None:
            return None

    with caplog.at_level("INFO", logger="desktop.cv_import_supervisor"):
        CvImportSupervisor(tmp_path / "cv.pdf", spawn=lambda _c, _o: _Pid()).run_once()
    records = [
        rec
        for rec in caplog.records
        if rec.name == "desktop.cv_import_supervisor" and "smaps_rollup" in rec.message
    ]
    assert len(records) == 1
    assert "median_s=" in records[0].message
    assert "max_s=" in records[0].message
    assert "reads=3" in records[0].message


def test_one_pass_drains_twenty_events_and_stall_follows_the_last(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """One drain reads every pending event. Stall uses the last real token."""
    from core.cv_import_deadline import ImportDeadlineWatch
    from desktop.cv_import_supervisor import CvLlmRates, _drain_phase_events

    monkeypatch.setattr("desktop.cv_import_supervisor._monotonic", lambda: 100.0)
    path = tmp_path / "phase.jsonl"
    lines = [
        json.dumps(
            {"phase": "generation", "tokens_done": i, "t_mono": i * 0.9},
            separators=(",", ":"),
        )
        for i in range(1, 21)
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    watch = ImportDeadlineWatch(
        initial_s=900,
        started_at=0,
        env_locked=True,
        buffer_s=60,
        ceiling_s=900,
    )
    seen: list[str] = []
    rates = CvLlmRates()
    offset = _drain_phase_events(path, 0, seen.append, watch, rates)
    assert offset == path.stat().st_size
    assert len(seen) == 20
    assert watch.tokens_done == 20
    # Parent now is 100. First t_mono is 0.9, last is 18.0.
    assert watch.last_progress_at == pytest.approx(117.1)
    assert watch.failure(117.1 + 59.9) is None
    assert watch.failure(117.1 + 60.0) == "stall"
    assert rates.n_gen == 20
    assert rates.gen_duration_s == pytest.approx(17.1)
    # A second pass on the same tail does not apply the events again.
    again = _drain_phase_events(path, offset, seen.append, watch, rates)
    assert again == offset
    assert len(seen) == 20
    assert rates.n_gen == 20


def test_timeout_logs_one_cv_llm_rates_line_with_partial_progress(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    clock = _fake_clock(monkeypatch)
    monkeypatch.delenv("KARRIEREKRAKE_CV_LLM_N_THREADS", raising=False)
    monkeypatch.delenv("KARRIEREKRAKE_CV_LLM_N_THREADS_BATCH", raising=False)

    class _Partial:
        def __init__(self, _out: Path) -> None:
            self._phase = Path(os.environ["KARRIEREKRAKE_CV_PHASE_EVENTS"])
            self._wrote = False

        def poll(self):
            if not self._wrote:
                diag = (
                    "cv_llm_inprocess n_ctx=4096 n_threads=3 n_threads_batch=3 "
                    "physical=4 logical=4 reserve=1 source=rule "
                    "n_prompt=1763 max_tokens=2325"
                )
                events = [
                    {"diag": diag, "level": "info"},
                    {
                        "phase": "prompt",
                        "prompt_tokens_done": 512,
                        "t_mono": 4.0,
                        "block_s": 4.0,
                    },
                    {"phase": "generation", "tokens_done": 10, "t_mono": 1.0},
                    {"phase": "generation", "tokens_done": 40, "t_mono": 5.0},
                ]
                self._phase.write_text(
                    "".join(
                        json.dumps(event, separators=(",", ":")) + "\n"
                        for event in events
                    ),
                    encoding="utf-8",
                )
                self._wrote = True
            if clock["t"] > 5000:
                return 1
            return None

        def terminate(self) -> None:
            return None

        def close(self) -> None:
            return None

        def job_memory_limit_signaled(self) -> bool:
            return False

    with caplog.at_level("INFO", logger="desktop.cv_import_supervisor"):
        result = CvImportSupervisor(
            tmp_path / "cv.pdf", spawn=lambda _c, out: _Partial(out)
        ).run_once()
    assert result.kind == "llm_timeout"
    assert result.reason == "stall"
    records = [
        rec
        for rec in caplog.records
        if rec.name == "desktop.cv_import_supervisor" and rec.message.startswith("cv_llm_rates ")
    ]
    assert len(records) == 1
    line = records[0].message
    assert "n_threads=3 n_threads_batch=3 physical=4 logical=4 reserve=1 source=rule" in line
    assert "n_prompt=512 prompt_s=4.000" in line
    assert "n_gen=40 gen_s=4.000" in line
    assert "prompt_tps=128.000" in line
    assert "gen_tps=10.000" in line


def test_free_diag_and_fd2_do_not_reach_app_sinks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A free child message and a write to fd 2 stay out of the app log."""
    import logging

    sentinel = "KK_SENTINEL_7f3a"
    user = "KKSentinelUser"
    cv = tmp_path / "Users" / user / "cv.txt"
    cv.parent.mkdir(parents=True)
    cv.write_text(sentinel, encoding="utf-8")

    class _Done:
        def __init__(self, out: Path) -> None:
            phase = Path(os.environ["KARRIEREKRAKE_CV_PHASE_EVENTS"])
            phase.write_text(
                json.dumps({"diag": f"note {sentinel} {user}"}) + "\n"
                + json.dumps(
                    {
                        "diag": (
                            "cv_llm_config timeout_s=300 timeout_source=formula "
                            "timeout_formula=300"
                        )
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            out.write_text(
                json.dumps(
                    {"ok": False, "kind": "timeout", "message": sentinel, "parsed": None}
                ),
                encoding="utf-8",
            )
            self.returncode = 1

        def poll(self):
            return self.returncode

        def wait(self, timeout=None):
            return self.returncode

        def terminate(self) -> None:
            return None

        def close(self) -> None:
            return None

        def job_memory_limit_signaled(self) -> bool:
            return False

    with caplog.at_level(logging.DEBUG):
        result = CvImportSupervisor(cv, spawn=lambda _c, out: _Done(out), timeout_s=30).run_once()
    assert result.kind == "llm_timeout"
    blob = caplog.text
    assert sentinel not in blob
    assert user not in blob
    assert "cv_llm_config" in blob
    assert any(rec.message.startswith("cv_llm_rates ") for rec in caplog.records)
    for rec in caplog.records:
        if rec.message.startswith("cv_llm_rates ") or rec.message.startswith("cv_llm_config "):
            assert sentinel not in rec.message
            assert user not in rec.message

    captured = tmp_path / "fd2.bin"
    side = tmp_path / "attempted"
    saved = os.dup(2)
    raw = os.open(str(captured), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    os.dup2(raw, 2)
    os.close(raw)
    try:
        from core.cv_llm_runtime import _construct_llama
        from desktop.cv_import_child import discard_child_stderr

        class _Fd2Llama:
            """Stub that writes the sentinel straight to file descriptor 2."""

            def __init__(self, *args, **kwargs):
                os.write(2, f"{sentinel} {user}\n".encode())
                self.kwargs = kwargs

        discard_child_stderr()
        side.write_bytes(b"wrote")
        llm, load_log = _construct_llama(_Fd2Llama, model_path="unused.gguf", verbose=True)
    finally:
        os.dup2(saved, 2)
        os.close(saved)
    assert side.read_bytes() == b"wrote"
    assert llm.kwargs["verbose"] is False
    assert sentinel not in load_log
    assert user not in load_log
    assert sentinel.encode() not in captured.read_bytes()
    assert user.encode() not in captured.read_bytes()
    assert sentinel not in caplog.text
    assert user not in caplog.text
