"""In-app memory gate counts private commit, not file-backed RSS."""

from __future__ import annotations

import sys

import pytest

from core.cv_docpick_import import (
    _linux_rss_anon_bytes,
    _peak_pagefile_via_get_info,
    _rss_anon_bytes_from_smaps,
    _self_rss_bytes,
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


def test_windows_branch_uses_peak_pagefile(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(
        "core.cv_docpick_import._windows_peak_pagefile_bytes",
        lambda: 3_200_000_000,
    )
    assert _self_rss_bytes() == 3_200_000_000


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
