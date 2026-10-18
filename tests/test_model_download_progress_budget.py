"""Retry budget counts only attempts without saved progress, under a hard cap.

Offline: ``urlopen`` is replaced by the fake server from the resume tests.
"""
import logging
import re
import ssl
import urllib.error

import pytest

from guenther import model_manager as models
from tests.test_model_download_resume_interrupted import (
    MIB,
    FakeResponse,
    FakeServer,
    make_manager,
    pattern,
    run,
    stream_sha256,
)

EOF_ERR = lambda: ssl.SSLEOFError(8, "EOF occurred in violation of protocol")


@pytest.fixture(autouse=True)
def fast_retry(monkeypatch):
    monkeypatch.setattr(models, "DOWNLOAD_RETRY_DELAY", 0)


def _start(rng):
    return int(rng[len("bytes="):-1]) if rng else 0


def _retry_flags(caplog):
    out = []
    for r in caplog.records:
        msg = r.getMessage()
        if "model_download_retry" in msg or "model_download_failed" in msg:
            m = re.search(r"'counted': (True|False)", msg)
            out.append(m.group(1) == "True" if m else None)
    return out


def _install(manager, mid, caplog, **kw):
    with caplog.at_level(logging.INFO, logger="karrierekrake"):
        return run(manager, mid, **kw)


def test_many_drops_with_progress_finish_the_download(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(models, "DOWNLOAD_MIN_PROGRESS_BYTES", 100_000)
    size = 3 * MIB + 17
    manager, mid, final, _part = make_manager(tmp_path, size, stream_sha256(size))
    step = 512 * 1024  # each attempt saves 512 KiB, then the line drops

    def handler(call, rng):
        start = _start(rng)
        fail = start + step if start + step < size else None
        return FakeResponse(206 if rng else 200, start, size, size, fail_at=fail, failure=EOF_ERR())
    server = FakeServer(monkeypatch, handler)
    result, _stages = _install(manager, mid, caplog)
    assert (result.status, result.message) == ("done", "installed")
    assert len(server.ranges) == 7 > models.DOWNLOAD_ATTEMPTS
    assert _retry_flags(caplog) == [False] * 6
    assert final.read_bytes() == pattern(0, size)


def test_drops_without_progress_give_up_after_budget(tmp_path, monkeypatch, caplog):
    size = 3 * MIB + 17
    manager, mid, final, _part = make_manager(tmp_path, size, stream_sha256(size))

    def handler(call, rng):
        start = _start(rng)  # 10 bytes per attempt is below the progress minimum
        return FakeResponse(206 if rng else 200, start, size, size, fail_at=start + 10, failure=EOF_ERR())
    server = FakeServer(monkeypatch, handler)
    result, _ = _install(manager, mid, caplog)
    assert (result.status, result.message) == ("error", "connection_interrupted")
    assert len(server.ranges) == models.DOWNLOAD_ATTEMPTS
    assert _retry_flags(caplog) == [True] * models.DOWNLOAD_ATTEMPTS
    assert not final.exists()


def test_hard_cap_stops_steady_small_progress(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(models, "DOWNLOAD_MIN_PROGRESS_BYTES", 5)
    size = 3 * MIB + 17
    manager, mid, final, part = make_manager(tmp_path, size, stream_sha256(size))

    def handler(call, rng):
        start = _start(rng)  # every attempt counts as progress, but only 10 bytes
        return FakeResponse(206 if rng else 200, start, size, size, fail_at=start + 10, failure=EOF_ERR())
    server = FakeServer(monkeypatch, handler)
    result, _ = _install(manager, mid, caplog)
    assert (result.status, result.message) == ("error", "connection_interrupted")
    assert len(server.ranges) == models.DOWNLOAD_MAX_TOTAL_ATTEMPTS
    assert _retry_flags(caplog) == [False] * models.DOWNLOAD_MAX_TOTAL_ATTEMPTS
    assert part.stat().st_size == 10 * models.DOWNLOAD_MAX_TOTAL_ATTEMPTS
    assert not final.exists()


def test_alternating_progress_only_counts_attempts_without_progress(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(models, "DOWNLOAD_MIN_PROGRESS_BYTES", 100_000)
    size = 3 * MIB + 17
    manager, mid, _final, _part = make_manager(tmp_path, size, stream_sha256(size))

    def handler(call, rng):
        start = _start(rng)
        step = 200_000 if call % 2 else 10  # progress, no progress, progress, ...
        return FakeResponse(206 if rng else 200, start, size, size, fail_at=start + step, failure=EOF_ERR())
    server = FakeServer(monkeypatch, handler)
    result, _ = _install(manager, mid, caplog)
    assert (result.status, result.message) == ("error", "connection_interrupted")
    assert len(server.ranges) == 2 * models.DOWNLOAD_ATTEMPTS
    assert _retry_flags(caplog) == [False, True] * models.DOWNLOAD_ATTEMPTS


def test_200_restart_mid_download_does_not_reset_the_budget(tmp_path, monkeypatch, caplog):
    size = 3 * MIB + 17
    manager, mid, _final, part = make_manager(tmp_path, size, stream_sha256(size))
    part.write_bytes(pattern(0, 2 * MIB))  # earlier progress

    def handler(call, rng):
        start = _start(rng)
        if call == 1:   # server ignores Range: 200 from zero, saves only 1 MiB
            return FakeResponse(200, 0, size, size, fail_at=MIB, failure=EOF_ERR())
        return FakeResponse(206, start, size, size, fail_at=start + 10, failure=EOF_ERR())
    server = FakeServer(monkeypatch, handler)
    result, _ = _install(manager, mid, caplog)
    assert (result.status, result.message) == ("error", "connection_interrupted")
    assert server.ranges[:2] == [f"bytes={2 * MIB}-", f"bytes={MIB}-"]
    assert len(server.ranges) == models.DOWNLOAD_ATTEMPTS
    assert _retry_flags(caplog) == [True] * models.DOWNLOAD_ATTEMPTS


def test_tls_certificate_error_is_never_retried_even_after_progress(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(models, "DOWNLOAD_MIN_PROGRESS_BYTES", 100_000)
    size = 3 * MIB + 17
    manager, mid, final, _part = make_manager(tmp_path, size, stream_sha256(size))

    def handler(call, rng):
        if call == 1:
            return FakeResponse(200, 0, size, size, fail_at=MIB, failure=EOF_ERR())
        raise urllib.error.URLError(ssl.SSLCertVerificationError(1, "certificate verify failed"))
    server = FakeServer(monkeypatch, handler)
    result, _ = _install(manager, mid, caplog)
    assert (result.status, result.message) == ("error", "tls_failed")
    assert len(server.ranges) == 2
    assert not final.exists()


def test_cancel_during_retries_stops_at_once(tmp_path, monkeypatch):
    monkeypatch.setattr(models, "DOWNLOAD_MIN_PROGRESS_BYTES", 100_000)
    size = 3 * MIB + 17
    manager, mid, final, _part = make_manager(tmp_path, size, stream_sha256(size))
    calls = []

    def handler(call, rng):
        calls.append(call)
        start = _start(rng)
        return FakeResponse(206 if rng else 200, start, size, size, fail_at=start + 200_000, failure=EOF_ERR())
    FakeServer(monkeypatch, handler)
    result, _ = run(manager, mid, cancel_check=lambda: len(calls) >= 2)
    assert (result.status, result.message) == ("cancelled", "cancelled")
    assert len(calls) == 2 and not final.exists()


def test_backoff_is_capped(monkeypatch):
    assert models.DOWNLOAD_RETRY_DELAY_MAX_STEPS >= 1
    assert models.DOWNLOAD_MAX_TOTAL_ATTEMPTS > models.DOWNLOAD_ATTEMPTS
    assert models.DOWNLOAD_MIN_PROGRESS_BYTES > 0
