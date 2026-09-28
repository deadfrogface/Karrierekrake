"""In-app memory gate counts private commit, not file-backed RSS."""

from __future__ import annotations

import sys

import pytest

from core.cv_docpick_import import (
    _enforce_peak_rss,
    _linux_rss_anon_bytes,
    _peak_job_memory_via_query,
    _peak_pagefile_via_get_info,
    _rss_anon_bytes_from_smaps,
    _self_rss_bytes,
    app_private_commit_bytes,
    bind_import_measure_job,
    fresh_app_child_budget_bytes,
    reset_import_measure_job,
    reset_private_commit_high_water,
    CvImportError,
    CV_IMPORT_FRESH_APP_PRIVATE_BYTES,
    CV_IMPORT_PEAK_RSS_BYTES_MAX,
)


_SMAPS = """\
Rss:             5000000 kB
Pss_File:        4000000 kB
Anonymous:         1800000 kB
RssFile:           2770000 kB
"""


def test_smaps_anonymous_ignores_file_backed_pages() -> None:
    assert _rss_anon_bytes_from_smaps(_SMAPS) == 1_800_000 * 1024


def test_smaps_prefers_rss_anon_key_when_present() -> None:
    text = _SMAPS + "Rss_Anon:            42 kB\n"
    assert _rss_anon_bytes_from_smaps(text) == 42 * 1024


def test_smaps_missing_anon_is_zero() -> None:
    assert _rss_anon_bytes_from_smaps("Rss: 10 kB\n") == 0


def test_linux_branch_reads_smaps_not_ru_maxrss(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(
        "core.cv_docpick_import._linux_rss_anon_bytes",
        lambda pid="self": 1234,
    )

    def boom(*_a, **_k):
        raise AssertionError("ru_maxrss must not be consulted")

    monkeypatch.setitem(sys.modules, "resource", type("R", (), {"getrusage": staticmethod(boom)}))
    assert _self_rss_bytes() == 1234


def test_fresh_child_budget_is_group_cap_minus_measured_app() -> None:
    assert CV_IMPORT_PEAK_RSS_BYTES_MAX == 3_300_000_000
    assert fresh_app_child_budget_bytes() == (
        3_300_000_000 - CV_IMPORT_FRESH_APP_PRIVATE_BYTES
    )
    assert fresh_app_child_budget_bytes() == 3_132_727_552


def test_windows_gate_reads_job_peak_not_pagefile(monkeypatch: pytest.MonkeyPatch) -> None:
    """A file-sized pagefile reading must not reach the gate."""
    reset_import_measure_job()
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(
        "core.cv_docpick_import._windows_peak_pagefile_bytes",
        lambda: 4_400_000_000,
    )
    bind_import_measure_job(7, lambda handle: 1_800_000_000 if handle == 7 else 0)
    try:
        assert _self_rss_bytes() == 1_800_000_000
        assert app_private_commit_bytes() == 4_400_000_000
    finally:
        reset_import_measure_job()


def test_null_job_handle_is_not_the_outer_job() -> None:
    calls: list[int] = []

    def query(handle: int) -> int:
        calls.append(handle)
        return 9_000_000_000

    assert _peak_job_memory_via_query(query, None) == 0
    assert _peak_job_memory_via_query(query, 0) == 0
    assert calls == []


def test_job_peak_over_fresh_budget_names_the_counter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reset_import_measure_job()
    reset_private_commit_high_water()
    monkeypatch.setattr(sys, "platform", "win32")
    fresh = fresh_app_child_budget_bytes()
    bind_import_measure_job(7, lambda _handle: fresh + 1)
    monkeypatch.setattr(
        "core.cv_docpick_import._windows_peak_pagefile_bytes",
        lambda: 1,
    )
    try:
        with pytest.raises(CvImportError) as ei:
            _enforce_peak_rss(stage="after_load", include_llama_server=False)
    finally:
        reset_import_measure_job()
        reset_private_commit_high_water()
    assert ei.value.code == "peak_rss_exceeded"
    assert ei.value.detail["stage"] == "after_load"
    assert ei.value.detail["peak_bytes"] == fresh + 1
    assert ei.value.detail["budget_bytes"] == fresh
    assert ei.value.detail["counter"] == "PeakJobMemoryUsed"


def test_peak_pagefile_reader_returns_counter_not_working_set() -> None:
    def get_info(_handle, ptr, _cb):
        import ctypes

        from core.cv_docpick_import import _process_memory_counters_ex_type

        cls = _process_memory_counters_ex_type()
        counters = ctypes.cast(ptr, ctypes.POINTER(cls)).contents
        counters.PeakWorkingSetSize = 9_000_000_000
        counters.PeakPagefileUsage = 2_500_000_000
        counters.PagefileUsage = 1
        return 1

    assert _peak_pagefile_via_get_info(get_info, lambda: 0) == 2_500_000_000


def test_peak_pagefile_reader_zero_when_call_fails() -> None:
    assert _peak_pagefile_via_get_info(lambda *_a: 0, lambda: 0) == 0


def test_linux_reader_reads_smaps_rollup(monkeypatch: pytest.MonkeyPatch) -> None:
    body = "Anonymous:           7 kB\nRss: 99 kB\n"

    class _FakePath:
        def __init__(self, raw):
            self.raw = str(raw)

        def read_text(self, encoding="utf-8", errors="replace"):
            assert self.raw == "/proc/self/smaps_rollup"
            return body

    monkeypatch.setattr("core.cv_docpick_import.Path", _FakePath)
    assert _linux_rss_anon_bytes("self") == 7 * 1024
