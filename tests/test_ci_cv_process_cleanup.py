"""Acceptance timeouts must not leave a onefile worker holding the model."""
import os
import signal
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest

from scripts.ci_cv_import_exe_offline_e2e import _terminate_child_tree


def test_windows_cleanup_targets_only_this_pid_tree(monkeypatch):
    calls = []
    waited = []
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(subprocess, "run", lambda argv, **kwargs: calls.append((argv, kwargs)))
    proc = SimpleNamespace(pid=12345, wait=lambda **kwargs: waited.append(kwargs))
    _terminate_child_tree(proc)
    assert calls[0][0] == ["taskkill", "/F", "/T", "/PID", "12345"]
    assert calls[0][1]["timeout"] == 30
    assert waited == [{"timeout": 30}]


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX process-group regression")
def test_timeout_reaps_root_and_stops_grandchild(tmp_path):
    import select
    ready = tmp_path / "grandchild.pid"
    script = (
        "import subprocess,sys,time; from pathlib import Path; "
        "child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(300)']); "
        "Path(sys.argv[1]).write_text(str(child.pid)); time.sleep(300)"
    )
    proc = subprocess.Popen([sys.executable, "-c", script, str(ready)], start_new_session=True,
                            stdout=subprocess.PIPE)
    try:
        deadline = time.monotonic() + 5
        while not ready.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert ready.exists()
        _terminate_child_tree(proc)
        assert proc.returncode is not None
        # The grandchild inherited stdout. EOF proves it closed its handle;
        # observing only the root's exit would miss an orphaned worker.
        assert select.select([proc.stdout], [], [], 5)[0]
        assert proc.stdout.read(1) == b""
    finally:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.wait(timeout=5)
        proc.stdout.close()
