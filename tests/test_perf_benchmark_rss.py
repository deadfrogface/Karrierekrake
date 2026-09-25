"""RSS reader of the manual benchmark, without running the benchmark.

The benchmark itself stays out of CI. These tests only simulate the
non-/proc path (Windows-shaped) and check that an unread sample is None
and that the peak abort still trips.
"""

from __future__ import annotations

import importlib.util
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
    monkeypatch.setattr(bench, "_process_group_id", lambda _pid: None)
    monkeypatch.setattr(
        bench,
        "_group_rss",
        lambda _pid, pgid=None: bench.PEAK_ABORT_BYTES,
    )
    proc = _ExitingProc()
    peak, aborted = bench._watch_process_rss(proc, 0.0)
    assert aborted is True
    assert proc.killed is True
    assert peak == bench.PEAK_ABORT_BYTES


def test_watch_with_only_unread_samples_reports_none(monkeypatch):
    monkeypatch.setattr(bench, "_process_group_id", lambda _pid: None)
    monkeypatch.setattr(bench, "_group_rss", lambda _pid, pgid=None: None)
    proc = _ExitingProc()
    peak, aborted = bench._watch_process_rss(proc, 0.0)
    assert peak is None
    assert aborted is False
    assert proc.killed is False
    assert bench._fmt_bytes(peak) == "n/a"


def test_proc_read_failure_is_none_not_zero(monkeypatch):
    def _unreadable(self, encoding="utf-8", errors=None):
        raise OSError("no /proc")

    monkeypatch.setattr(bench.Path, "read_text", _unreadable)
    assert bench._rss_pair_proc(123) == (None, None)
