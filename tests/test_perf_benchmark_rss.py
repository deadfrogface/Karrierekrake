"""RSS reader of the manual benchmark, without running the benchmark.

The benchmark itself stays out of CI. These tests only simulate the
non-/proc path (Windows-shaped) and check that an unread sample is None
and that the peak abort still trips.
"""

from __future__ import annotations

import importlib.util
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "kk_perf_benchmark",
    Path(__file__).resolve().parents[1] / "tools" / "perf" / "benchmark.py",
)
assert _SPEC is not None and _SPEC.loader is not None
bench = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(bench)


class _MemInfo:
    def __init__(self, rss, peak_wset=None, peak_pagefile=None):
        self.rss = rss
        if peak_wset is not None:
            self.peak_wset = peak_wset
        if peak_pagefile is not None:
            self.peak_pagefile = peak_pagefile


class _Proc:
    def __init__(self, rss, children=None, peak_wset=None, peak_pagefile=None, fail_mem=False):
        self.rss = rss
        self._children = list(children or [])
        self.peak_wset = peak_wset
        self.peak_pagefile = peak_pagefile
        self.fail_mem = fail_mem

    def memory_info(self):
        if self.fail_mem:
            raise RuntimeError("memory_info unreadable")
        return _MemInfo(self.rss, self.peak_wset, self.peak_pagefile)

    def children(self, recursive=False):
        if not recursive:
            return list(self._children)
        out = []
        for child in self._children:
            out.append(child)
            out.extend(child.children(recursive=True))
        return out


class _Psutil:
    def __init__(self, processes):
        self._processes = processes

    def Process(self, pid):
        try:
            return self._processes[pid]
        except KeyError as exc:
            raise RuntimeError(f"no process {pid}") from exc


class _ExitingProc:
    def __init__(self, polls_before_exit: int = 2):
        self.pid = 42
        self.killed = False
        self._polls = 0
        self._limit = polls_before_exit

    def poll(self):
        self._polls += 1
        if self._polls >= self._limit:
            return 0
        return None

    def kill(self):
        self.killed = True


def _force_psutil(monkeypatch, psutil):
    monkeypatch.setattr(bench, "_proc_available", lambda: False)
    monkeypatch.setattr(bench, "_load_psutil", lambda: psutil)


def test_neither_proc_nor_psutil_raises_instead_of_zero(monkeypatch, capsys):
    monkeypatch.setattr(bench, "_proc_available", lambda: False)
    monkeypatch.setattr(bench, "_load_psutil", lambda: None)
    with pytest.raises(bench.MemoryReadError, match="psutil"):
        bench._rss_pair(7)
    with pytest.raises(bench.MemoryReadError, match="psutil"):
        bench._group_rss(7, None)
    with pytest.raises(SystemExit) as caught:
        bench._ensure_memory_reader()
    assert caught.value.code == 2
    assert "psutil" in capsys.readouterr().err


def test_psutil_path_reads_rss_and_windows_peak(monkeypatch):
    _force_psutil(
        monkeypatch,
        _Psutil({7: _Proc(rss=4096, peak_wset=8192, peak_pagefile=16384)}),
    )
    rss, peak = bench._rss_pair(7)
    assert rss == 4096
    assert peak == 8192


def test_psutil_uses_peak_pagefile_when_wset_missing(monkeypatch):
    _force_psutil(monkeypatch, _Psutil({7: _Proc(rss=100, peak_pagefile=250)}))
    rss, peak = bench._rss_pair(7)
    assert rss == 100
    assert peak == 250


def test_psutil_missing_peak_and_failed_read_are_none(monkeypatch):
    _force_psutil(monkeypatch, _Psutil({7: _Proc(rss=100)}))
    rss, peak = bench._rss_pair(7)
    assert rss == 100
    assert peak is None

    _force_psutil(monkeypatch, _Psutil({8: _Proc(rss=100, fail_mem=True)}))
    assert bench._rss_pair(8) == (None, None)
    assert bench._group_rss(8, None) is None

    _force_psutil(monkeypatch, _Psutil({}))
    assert bench._group_rss(99, None) is None
    assert bench._rss_pair(99) == (None, None)


def test_psutil_children_sum_trips_abort(monkeypatch):
    child = _Proc(rss=1_000)
    grandchild = _Proc(rss=bench.PEAK_ABORT_BYTES)
    parent = _Proc(rss=2_000, children=[child])
    child._children = [grandchild]
    _force_psutil(monkeypatch, _Psutil({42: parent}))
    sample = bench._group_rss(42, pgid=None)
    assert sample == 2_000 + 1_000 + bench.PEAK_ABORT_BYTES
    peak, abort = bench._note_rss_sample(None, sample)
    assert abort is True
    assert peak == sample
    assert peak != 0


def test_unread_sample_stays_none_and_does_not_abort():
    peak, abort = bench._note_rss_sample(None, None)
    assert peak is None
    assert abort is False
    kept, abort_again = bench._note_rss_sample(123, None)
    assert kept == 123
    assert abort_again is False


def test_watch_aborts_when_psutil_sample_crosses_limit(monkeypatch):
    killed: list[tuple[int, int | None]] = []
    monkeypatch.setattr(bench, "_process_group_id", lambda _pid: None)
    monkeypatch.setattr(
        bench,
        "_group_rss",
        lambda _pid, pgid=None: bench.PEAK_ABORT_BYTES,
    )
    monkeypatch.setattr(
        bench,
        "_kill_process_tree",
        lambda proc, pgid: killed.append((proc.pid, pgid)),
    )
    proc = _ExitingProc()
    peak, aborted = bench._watch_process_rss(proc, 0.0)
    assert aborted is True
    assert killed == [(proc.pid, None)]
    assert peak == bench.PEAK_ABORT_BYTES


def test_watch_without_any_sample_raises(monkeypatch):
    monkeypatch.setattr(bench, "_process_group_id", lambda _pid: None)
    monkeypatch.setattr(bench, "_group_rss", lambda _pid, pgid=None: None)
    proc = _ExitingProc()
    with pytest.raises(bench.NoRssSampleError, match="Kein RSS-Messwert"):
        bench._watch_process_rss(proc, 0.0)


def test_main_exits_nonzero_when_no_rss_sample(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(bench, "_ensure_memory_reader", lambda: None)

    def _no_sample(*_args, **_kwargs):
        raise bench.NoRssSampleError(
            "Kein RSS-Messwert gelesen: alle Stichproben waren leer"
        )

    monkeypatch.setattr(bench, "_run_worker", _no_sample)
    code = bench.main(
        ["--runs", "5", "--out", str(tmp_path / "out"), "--sections", "ui", "--skip-trace"]
    )
    assert code != 0
    assert code == bench.NO_SAMPLE_EXIT
    assert "Kein RSS-Messwert" in capsys.readouterr().err


def test_linux_accounting_names_vmrss_and_vmhwm():
    fields = bench._limit_metric_fields()
    assert fields["limit_metric"] == "VmRSS"
    assert fields["process_high_water_metric"] == "VmHWM"
    accounting = bench._memory_accounting(0.05)
    assert accounting["peak_is_sampled"] is True
    assert accounting["sample_interval_ms"] == 50
    assert "VmRSS" in accounting["limit_metric_note"]
    assert "VmHWM" in accounting["limit_metric_note"]


def test_windows_accounting_uses_peak_job_memory(monkeypatch):
    monkeypatch.setattr(bench.sys, "platform", "win32")
    fields = bench._limit_metric_fields()
    assert fields["limit_metric"] == "PeakJobMemoryUsed"
    assert "PeakProcessMemoryUsed" in fields["limit_metric_note"]
    assert "Working Set" in fields["limit_metric_note"]
    assert "Peak-Gate" in fields["limit_metric_note"]


def test_job_object_kill_does_not_stop_at_the_root(monkeypatch):
    calls: list[object] = []
    monkeypatch.setattr(bench, "_terminate_windows_job", lambda job: calls.append(job))

    def _no_killpg(_pgid: int | None) -> bool:
        raise AssertionError("killpg must not run when a job handle is set")

    monkeypatch.setattr(bench, "_posix_killpg", _no_killpg)
    proc = type("P", (), {"job": "JOB", "pid": 5})()
    bench._kill_process_tree(proc, 5)
    assert calls == ["JOB"]


def test_windows_kill_hits_children_then_root(monkeypatch):
    killed: list[int] = []

    class _Node:
        def __init__(self, pid, kids):
            self.pid = pid
            self._kids = kids

        def children(self, recursive=False):
            assert recursive is True
            return list(self._kids)

        def kill(self):
            killed.append(self.pid)

    grand = _Node(3, [])
    child = _Node(2, [grand])
    root = _Node(1, [child, grand])

    class _Ps:
        def Process(self, pid):
            assert pid == 1
            return root

    monkeypatch.setattr(bench, "_load_psutil", lambda: _Ps())
    bench._kill_psutil_tree(1)
    assert killed == [2, 3, 1]


def test_abort_kills_child_and_grandchild(tmp_path, monkeypatch):
    pidfile = tmp_path / "pids.txt"
    script = tmp_path / "child.py"
    script.write_text(
        "import os, subprocess, sys, time\n"
        "from pathlib import Path\n"
        "grand = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])\n"
        "Path(sys.argv[1]).write_text(f'{os.getpid()}\\n{grand.pid}\\n')\n"
        "time.sleep(120)\n",
        encoding="utf-8",
    )
    proc = subprocess.Popen(
        [sys.executable, str(script), str(pidfile)],
        start_new_session=True,
    )
    try:
        deadline = time.time() + 5
        while time.time() < deadline and not pidfile.exists():
            assert proc.poll() is None
            time.sleep(0.02)
        child_pid_s, grand_pid_s = pidfile.read_text(encoding="utf-8").split()
        child_pid = int(child_pid_s)
        grand_pid = int(grand_pid_s)
        assert child_pid == proc.pid
        assert os.getpgid(child_pid) == proc.pid
        assert os.getpgid(grand_pid) == proc.pid
        monkeypatch.setattr(bench, "_group_rss", lambda *_a, **_k: bench.PEAK_ABORT_BYTES)
        _peak, aborted = bench._watch_process_rss(proc, 0.0)
        assert aborted is True
        proc.wait(timeout=3)
        deadline = time.time() + 2
        while time.time() < deadline and (_running(child_pid) or _running(grand_pid)):
            time.sleep(0.05)
        assert _running(child_pid) is False
        assert _running(grand_pid) is False
    finally:
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait(timeout=3)


def _running(pid: int) -> bool:
    try:
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
    except OSError:
        return False
    state = stat[stat.rfind(")") + 2 :].split()[0]
    return state not in {"Z", "X"}


def test_proc_read_failure_is_none_not_zero(monkeypatch):
    def _unreadable(self, encoding="utf-8", errors=None):
        raise OSError("no /proc")

    monkeypatch.setattr(bench.Path, "read_text", _unreadable)
    assert bench._rss_pair_proc(123) == (None, None)
