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
        lambda _proc: None,
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
    for line in progress_lines:
        timeout_s, tokens_done = absorb_phase_message(
            line,
            timeout_s=timeout_s,
            tokens_done=tokens_done,
        )
    assert timeout_s == int(supervisor.timeout_s)
    assert tokens_done is None


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
        lambda _proc: None,
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
