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
    _parent_anon_over_limit,
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


def test_extract_spawn_does_not_arm_job_memory_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict = {}

    def launch(argv, **kwargs):
        seen["kwargs"] = kwargs
        return object()

    monkeypatch.setattr("desktop.cv_import_supervisor.launch_contained", launch)
    default_spawn(Path("cv.pdf"), Path("out.json"))
    assert seen["kwargs"].get("enforce_memory_bytes") is None


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
        assert _parent_anon_over_limit(_Pid()) is False
    assert "unmeasured" in caplog.text
    assert "not a pass" in caplog.text
