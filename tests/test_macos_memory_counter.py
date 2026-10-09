"""Darwin memory accounting must fail closed without Linux /proc."""
import ctypes
import pytest

from core import cv_docpick_import as imp


def test_darwin_uses_footprint_for_child_and_app(monkeypatch):
    monkeypatch.setattr(imp.sys, 'platform', 'darwin')
    monkeypatch.setattr(imp, '_macos_physical_footprint_bytes', lambda: 123456)
    monkeypatch.setattr(imp, '_linux_rss_anon_bytes', lambda *a: pytest.fail('Linux counter used'))
    assert imp._self_rss_bytes() == 123456
    assert imp.app_private_commit_bytes() == 123456
    assert imp.peak_counter_name() == 'PhysicalFootprint'


@pytest.mark.parametrize('status,expected', [(0, 123456), (-1, 0)])
def test_libproc_abi_reads_footprint_instead_of_resident(monkeypatch, status, expected):
    class Query:
        def __call__(self, pid, flavor, pointer):
            assert flavor == 0
            usage = pointer._obj
            assert ctypes.sizeof(usage) == 96
            assert type(usage).phys_footprint.offset == 72
            usage.resident_size = 4000000000
            usage.phys_footprint = 123456
            return status
    class Lib:
        proc_pid_rusage = Query()
    monkeypatch.setattr(ctypes, 'CDLL', lambda *a, **kw: Lib())
    assert imp._macos_physical_footprint_bytes() == expected


def test_libproc_unavailable_is_unmeasured(monkeypatch):
    def unavailable(*a, **kw):
        raise OSError('unavailable')
    monkeypatch.setattr(ctypes, 'CDLL', unavailable)
    assert imp._macos_physical_footprint_bytes() == 0
