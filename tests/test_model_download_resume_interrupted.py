"""A connection drop mid-file resumes safely instead of aborting the setup.

Regression for a real setup download that broke twice at byte 472,695,563
with TLS "unexpected eof". Everything is offline: ``urlopen`` is replaced by a
fake server that streams deterministic bytes lazily, so no 470 MB buffer is
ever allocated and no network is touched.
"""
import hashlib
import http.client
import os
import shutil
import ssl
import urllib.error
from pathlib import Path

import pytest
import requests
import urllib3

from guenther import model_manager as models
from guenther import setup_models as setup

DROP_AT = 472_695_563
MIB = 1024 * 1024
_TABLE = bytes((i * 7 + 3) % 251 for i in range(251))


@pytest.fixture(autouse=True)
def fast_retry(monkeypatch):
    monkeypatch.setattr(models, "DOWNLOAD_RETRY_DELAY", 0)


def pattern(offset: int, length: int, zero_until: int = 0) -> bytes:
    """Deterministic content at absolute file offsets; zeros below zero_until."""
    zeros = max(0, min(length, zero_until - offset))
    start = offset + zeros
    rest = length - zeros
    shift = start % 251
    body = (_TABLE * (rest // 251 + 2))[shift:shift + rest]
    return b"\0" * zeros + body


def stream_sha256(total: int, zero_until: int = 0) -> str:
    digest = hashlib.sha256()
    pos = 0
    while pos < total:
        step = min(8 * MIB, total - pos)
        digest.update(pattern(pos, step, zero_until))
        pos += step
    return digest.hexdigest()


class FakeResponse:
    """Streams [start, end) of the simulated file; optionally breaks at fail_at."""

    def __init__(self, status, start, end, total, *, fail_at=None, failure=None,
                 content=None, headers=None):
        self.status = status
        self.pos, self.end = start, end
        self.fail_at, self.failure = fail_at, failure
        self.content = content or (lambda off, n: pattern(off, n))
        self.headers = {"Content-Length": str(end - start), **(headers or {})}
        if status == 206:
            self.headers.setdefault("Content-Range", f"bytes {start}-{end - 1}/{total}")
        self.closed = False

    def read(self, size=-1):
        if self.fail_at is not None and self.pos >= self.fail_at:
            raise self.failure
        limit = self.end if self.fail_at is None else min(self.end, self.fail_at)
        n = min(size if size > 0 else limit - self.pos, limit - self.pos)
        if n <= 0:
            return b""
        data = self.content(self.pos, n)
        self.pos += n
        return data

    def close(self):
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


class FakeServer:
    """Replaces urlopen; records every Range header and TLS context."""

    def __init__(self, monkeypatch, handler):
        self.handler = handler
        self.ranges, self.contexts = [], []
        monkeypatch.setattr(models.urllib.request, "urlopen", self)

    def __call__(self, req, **kwargs):
        assert "verify" not in kwargs
        self.contexts.append(kwargs.get("context"))
        self.ranges.append(req.get_header("Range"))
        return self.handler(len(self.ranges), req.get_header("Range"))


def make_manager(tmp_path, total, sha, *, exact=True):
    mid = models.PRODUCTION_MODEL_ID
    entry = {"filename": "model.gguf", "url": "https://example.test/model.gguf",
             "sha256": sha, "approx_bytes": total}
    if exact:
        entry["size_exact"] = True
    manager = models.ModelManager(tmp_path / "models", catalog={mid: entry})
    manager.disk_free_bytes = lambda: 10**13  # never depend on the shared box's disk
    final = manager.model_path(mid)
    final.parent.mkdir(parents=True, exist_ok=True)
    return manager, mid, final, final.with_suffix(".gguf.part")


@pytest.fixture
def hashed(monkeypatch):
    """Spy on the from-disk SHA-256 so tests can prove what was hashed."""
    seen = []
    real = models.sha256_file
    def spy(path, **kwargs):
        seen.append((Path(path).name, Path(path).stat().st_size))
        return real(path, **kwargs)
    monkeypatch.setattr(models, "sha256_file", spy)
    return seen


def run(manager, mid, **kwargs):
    stages = []
    result = manager.install(mid, allow_download=True,
                             progress_cb=lambda p: stages.append((p.status, p.message)), **kwargs)
    return result, stages


# (a) literal offset 472,695,563 --------------------------------------------

def test_tls_eof_at_byte_472695563_resumes_with_206_and_hashes_whole_file(tmp_path, monkeypatch, hashed):
    if shutil.disk_usage(tmp_path).free < 2 * 1024**3:
        pytest.skip("needs room for a sparse ~480 MB fixture")
    lead = 2 * MIB           # bytes the first (simulated) attempt still delivers
    total = DROP_AT + 3 * MIB + 17
    sha = stream_sha256(total, zero_until=DROP_AT - lead)
    manager, mid, final, part = make_manager(tmp_path, total, sha)
    with part.open("wb") as out:   # earlier progress, sparse zeros on disk
        out.truncate(DROP_AT - lead)
    # st_blocks only exists on POSIX; on Windows the 2 GiB free-space check above
    # already bounds the fixture, so the test still runs there.
    blocks = getattr(part.stat(), "st_blocks", None)
    if blocks is not None and blocks * 512 > 64 * MIB:
        pytest.skip("filesystem without sparse files")
    content = lambda off, n: pattern(off, n, zero_until=DROP_AT - lead)
    eof = ssl.SSLError(1, "[SSL: UNEXPECTED_EOF_WHILE_READING] unexpected eof while reading")
    def handler(call, rng):
        start = int(rng[len("bytes="):-1])
        if call == 1:
            return FakeResponse(206, start, total, total, fail_at=DROP_AT, failure=eof, content=content)
        return FakeResponse(206, start, total, total, content=content)
    server = FakeServer(monkeypatch, handler)
    result, stages = run(manager, mid)
    assert (result.status, result.message) == ("done", "installed")
    assert server.ranges == [f"bytes={DROP_AT - lead}-", "bytes=472695563-"]
    assert ("retrying", "connection_interrupted") in stages
    assert final.stat().st_size == total and not part.exists()
    # The digest was taken from disk over the complete file, prefix included.
    assert hashed == [("model.gguf.part", total)]


def test_resume_logic_for_offset_472695563():
    total = 4_124_161_376
    good = f"bytes 472695563-{total - 1}/{total}"
    assert models._resume_problem(206, good, DROP_AT, total) == (None, total)
    assert models._resume_problem(206, good, DROP_AT, None) == (None, total)
    assert models._resume_problem(206, f"bytes 472695562-{total - 1}/{total}", DROP_AT, total)[0] == "invalid_download_range"
    assert models._resume_problem(206, f"bytes 0-{total - 1}/{total}", DROP_AT, total)[0] == "invalid_download_range"
    assert models._resume_problem(206, good, DROP_AT, total + 1)[0] == "invalid_download_range"
    assert models._resume_problem(206, f"bytes 472695563-{total - 2}/{total}", DROP_AT, total)[0] == "invalid_download_range"
    assert models._resume_problem(206, "", DROP_AT, total)[0] == "invalid_download_range"
    assert models._resume_problem(200, "", DROP_AT, total) == (None, None)
    assert models._resume_problem(204, "", DROP_AT, total)[0] == "invalid_download_response"


def test_200_after_drop_at_472695563_truncates_the_part_file(tmp_path, monkeypatch):
    total = DROP_AT + 5 * MIB
    manager, mid, final, part = make_manager(tmp_path, total, "a" * 64)
    with part.open("wb") as out:
        out.truncate(DROP_AT)
    server = FakeServer(monkeypatch, lambda call, rng: FakeResponse(200, 0, total, total))
    chunks = []
    result = manager.install(mid, allow_download=True,
                             progress_cb=lambda p: chunks.append(p.bytes_done),
                             cancel_check=lambda: len(chunks) >= 2)
    assert server.ranges == ["bytes=472695563-"]
    assert result.status == "cancelled"
    # Only the new body's first MiB is on disk: the old 472 MB were dropped.
    assert part.stat().st_size == MIB
    assert part.read_bytes() == pattern(0, MIB)
    assert not final.exists()


# small simulated files for the full flows ------------------------------------

SIZE = 3 * MIB + 17
PAYLOAD_SHA = stream_sha256(SIZE)


def drop_then(second):
    """First request breaks after 1 MiB + 5 bytes with TLS EOF; then `second`."""
    eof = ssl.SSLEOFError(8, "EOF occurred in violation of protocol (_ssl.c:2427)")
    def handler(call, rng):
        if call == 1:
            return FakeResponse(200, 0, SIZE, SIZE, fail_at=MIB + 5, failure=eof)
        return second(call, rng)
    return handler


def test_resumed_206_hashes_prefix_and_tail_from_disk(tmp_path, monkeypatch, hashed):
    manager, mid, final, part = make_manager(tmp_path, SIZE, PAYLOAD_SHA)
    server = FakeServer(monkeypatch, drop_then(
        lambda call, rng: FakeResponse(206, MIB + 5, SIZE, SIZE)))
    result, stages = run(manager, mid)
    assert result.status == "done"
    assert server.ranges == [None, f"bytes={MIB + 5}-"]
    assert final.read_bytes() == pattern(0, SIZE)
    assert hashed == [("model.gguf.part", SIZE)]


def test_200_on_resume_restarts_and_old_bytes_never_reach_the_hash(tmp_path, monkeypatch, hashed):
    manager, mid, final, part = make_manager(tmp_path, SIZE, PAYLOAD_SHA)
    eof = ssl.SSLEOFError(8, "EOF occurred in violation of protocol")
    # The broken first attempt delivers garbage; if any of it survived the
    # restart (appended or hashed) the pinned SHA-256 could not match.
    garbage = lambda off, n: b"\xee" * n
    def handler(call, rng):
        if call == 1:
            return FakeResponse(200, 0, SIZE, SIZE, fail_at=MIB + 5, failure=eof, content=garbage)
        return FakeResponse(200, 0, SIZE, SIZE)
    server = FakeServer(monkeypatch, handler)
    result, stages = run(manager, mid)
    assert (result.status, result.message) == ("done", "installed")
    assert server.ranges == [None, f"bytes={MIB + 5}-"]
    assert final.read_bytes() == pattern(0, SIZE)
    assert hashed == [("model.gguf.part", SIZE)]


@pytest.mark.parametrize("bad_range", [
    lambda n: f"bytes {n - 1}-{SIZE - 1}/{SIZE}",          # wrong start
    lambda n: f"bytes {n + 1}-{SIZE - 1}/{SIZE}",          # wrong start
    lambda n: f"bytes {n}-{SIZE}/{SIZE + 1}",              # total != pinned size
])
def test_206_with_unusable_content_range_restarts_from_zero(tmp_path, monkeypatch, hashed, bad_range):
    manager, mid, final, part = make_manager(tmp_path, SIZE, PAYLOAD_SHA)
    part.write_bytes(b"\xee" * 1000)
    def handler(call, rng):
        if rng:
            return FakeResponse(206, 1000, SIZE, SIZE, headers={"Content-Range": bad_range(1000)})
        return FakeResponse(200, 0, SIZE, SIZE)
    server = FakeServer(monkeypatch, handler)
    result, _ = run(manager, mid)
    assert result.status == "done"
    assert server.ranges == ["bytes=1000-", None]
    assert final.read_bytes() == pattern(0, SIZE)
    assert hashed == [("model.gguf.part", SIZE)]


def test_unusable_answers_restart_only_once_then_fail_clearly(tmp_path, monkeypatch):
    manager, mid, final, part = make_manager(tmp_path, SIZE, PAYLOAD_SHA)
    part.write_bytes(b"\xee" * 1000)
    server = FakeServer(monkeypatch, lambda call, rng: FakeResponse(204, 0, 0, SIZE))
    result, _ = run(manager, mid)
    assert (result.status, result.message) == ("error", "invalid_download_response")
    assert server.ranges == ["bytes=1000-", None]
    assert not final.exists()


def test_second_416_after_a_restart_fails_with_http_416(tmp_path, monkeypatch):
    manager, mid, final, part = make_manager(tmp_path, SIZE, PAYLOAD_SHA)
    part.write_bytes(b"\xee" * 1000)
    eof = ssl.SSLEOFError(8, "EOF occurred in violation of protocol")
    def handler(call, rng):
        if rng:
            raise urllib.error.HTTPError("https://example.test", 416, "range", {}, None)
        return FakeResponse(200, 0, SIZE, SIZE, fail_at=MIB + 5, failure=eof)
    server = FakeServer(monkeypatch, handler)
    result, _ = run(manager, mid)
    assert (result.status, result.message) == ("error", "http_416")
    assert server.ranges == ["bytes=1000-", None, f"bytes={MIB + 5}-"]
    assert not final.exists()


# (e) classification: mid-body interruption vs. TLS policy failure -----------

def _wrapped_requests_ssl():
    try:
        try:
            raise ssl.SSLEOFError(8, "EOF occurred in violation of protocol")
        except ssl.SSLError as inner:
            raise urllib3.exceptions.SSLError(inner) from inner
    except urllib3.exceptions.SSLError as mid:
        try:
            raise requests.exceptions.SSLError(mid)
        except requests.exceptions.SSLError as outer:
            return outer


def _chunked():
    try:
        try:
            raise http.client.IncompleteRead(b"", 10)
        except http.client.IncompleteRead as inner:
            raise urllib3.exceptions.ProtocolError("Connection broken", inner)
    except urllib3.exceptions.ProtocolError as mid:
        try:
            raise requests.exceptions.ChunkedEncodingError(mid)
        except requests.exceptions.ChunkedEncodingError as outer:
            return outer


@pytest.mark.parametrize("failure", [
    lambda: ssl.SSLEOFError(8, "EOF occurred in violation of protocol (_ssl.c:2427)"),
    lambda: ssl.SSLError(1, "[SSL: UNEXPECTED_EOF_WHILE_READING] unexpected eof while reading"),
    lambda: http.client.IncompleteRead(b"", 100),
    lambda: ConnectionResetError(104, "Connection reset by peer"),
    _wrapped_requests_ssl,
    _chunked,
], ids=["sslEOF", "unexpected_eof", "IncompleteRead", "reset", "requests_SSLError", "ChunkedEncoding"])
def test_mid_body_interruption_is_connection_interrupted_and_retried(tmp_path, monkeypatch, failure):
    manager, mid, final, part = make_manager(tmp_path, SIZE, PAYLOAD_SHA)
    def handler(call, rng):
        if call == 1:
            return FakeResponse(200, 0, SIZE, SIZE, fail_at=MIB, failure=failure())
        return FakeResponse(206, MIB, SIZE, SIZE)
    server = FakeServer(monkeypatch, handler)
    result, stages = run(manager, mid)
    assert result.status == "done"
    assert ("retrying", "connection_interrupted") in stages
    assert server.ranges == [None, f"bytes={MIB}-"]
    assert final.read_bytes() == pattern(0, SIZE)


def test_interruption_retries_stay_bounded(tmp_path, monkeypatch):
    manager, mid, final, part = make_manager(tmp_path, SIZE, PAYLOAD_SHA)
    eof = ssl.SSLEOFError(8, "EOF occurred in violation of protocol")
    def handler(call, rng):
        start = int(rng[6:-1]) if rng else 0
        return FakeResponse(206 if rng else 200, start, SIZE, SIZE, fail_at=start + 10, failure=eof)
    server = FakeServer(monkeypatch, handler)
    result, _ = run(manager, mid)
    assert (result.status, result.message) == ("error", "connection_interrupted")
    assert len(server.ranges) == models.DOWNLOAD_ATTEMPTS
    assert part.stat().st_size == 30 and not final.exists()


def test_tls_eof_before_any_body_byte_stays_tls_failed(tmp_path, monkeypatch):
    manager, mid, final, part = make_manager(tmp_path, SIZE, PAYLOAD_SHA)
    eof = ssl.SSLEOFError(8, "EOF occurred in violation of protocol")
    server = FakeServer(monkeypatch, lambda call, rng: FakeResponse(200, 0, SIZE, SIZE, fail_at=0, failure=eof))
    result, _ = run(manager, mid)
    assert (result.status, result.message) == ("error", "tls_failed")
    assert len(server.ranges) == 1


@pytest.mark.parametrize("where", ["handshake", "read"])
def test_certificate_error_is_tls_failed_with_exactly_one_attempt(tmp_path, monkeypatch, where):
    manager, mid, final, part = make_manager(tmp_path, SIZE, PAYLOAD_SHA)
    cert = ssl.SSLCertVerificationError(1, "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed")
    def handler(call, rng):
        if where == "handshake":
            raise urllib.error.URLError(cert)
        return FakeResponse(200, 0, SIZE, SIZE, fail_at=MIB, failure=cert)
    server = FakeServer(monkeypatch, handler)
    result, stages = run(manager, mid)
    assert (result.status, result.message) == ("error", "tls_failed")
    assert len(server.ranges) == 1
    assert not any(stage == "retrying" for stage, _ in stages)
    assert not final.exists()


def test_every_request_verifies_certificates_and_no_bypass_exists(tmp_path, monkeypatch):
    manager, mid, final, part = make_manager(tmp_path, SIZE, PAYLOAD_SHA)
    server = FakeServer(monkeypatch, drop_then(lambda call, rng: FakeResponse(206, MIB + 5, SIZE, SIZE)))
    assert run(manager, mid)[0].status == "done"
    assert len(server.contexts) == 2
    for context in server.contexts:
        assert isinstance(context, ssl.SSLContext)
        assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname
    root = Path(models.__file__).resolve().parent.parent
    for rel in ("guenther/model_manager.py", "guenther/setup_models.py", "core/native_model_download.py"):
        source = (root / rel).read_text(encoding="utf-8")
        for needle in ("verify=False", "CERT_NONE", "_create_unverified_context",
                       "check_hostname = False", "check_hostname=False"):
            assert needle not in source, (rel, needle)


def test_failure_codes_walk_the_exception_chain():
    eof = ssl.SSLEOFError(8, "EOF occurred in violation of protocol")
    assert models.download_failure_code(eof) == "tls_failed"          # no body yet
    assert not models._retryable_download_error(eof)
    try:
        raise models.DownloadInterruptedError("connection_interrupted") from eof
    except models.DownloadInterruptedError as wrapped:
        assert models.download_failure_code(wrapped) == "connection_interrupted"
        assert models._retryable_download_error(wrapped)
    assert models._is_body_interruption(_wrapped_requests_ssl())
    assert models._is_body_interruption(_chunked())
    cert = ssl.SSLCertVerificationError(1, "certificate verify failed")
    assert not models._is_body_interruption(cert)
    assert not models._is_body_interruption(urllib.error.URLError(cert))
    assert models.download_failure_code(urllib.error.URLError(cert)) == "tls_failed"
    assert not models._retryable_download_error(urllib.error.URLError(cert))


# (d)/(f) activation through the real setup entry point -----------------------

@pytest.fixture
def setup_flow(tmp_path, monkeypatch):
    mid = "qwen3.5-4b-gsq"
    def configure(sha):
        entry = dict(setup.SETUP_MODEL_CATALOG[mid], approx_bytes=SIZE, sha256=sha)
        assert entry["size_exact"] is True
        monkeypatch.setattr(setup, "SETUP_MODEL_CATALOG", {mid: entry})
        monkeypatch.setenv("KARRIEREKRAKE_MODELS_DIR", str(tmp_path))
        monkeypatch.setattr(models.ModelManager, "disk_free_bytes", lambda self: 10**13)
        FakeServer(monkeypatch, drop_then(lambda call, rng: FakeResponse(206, MIB + 5, SIZE, SIZE)))
        final = tmp_path / mid / entry["filename"]
        return mid, final, final.with_suffix(final.suffix + ".part")
    return configure


def test_sha_mismatch_after_resume_leaves_no_model_and_no_activation(setup_flow, tmp_path, monkeypatch):
    from core import model_probe
    mid, final, part = setup_flow("0" * 64)
    monkeypatch.setattr(model_probe, "probe_in_subprocess", lambda *a, **k: pytest.fail("corrupt load"))
    with pytest.raises(RuntimeError, match="checksum_mismatch"):
        setup.install_recommended_model(mid, cancelled=lambda: False, progress=lambda _: None)
    assert not (tmp_path / "active-model.json").exists()
    assert not final.exists() and not part.exists()


def test_activation_waits_for_hash_and_probe_after_resume(setup_flow, tmp_path, monkeypatch):
    from core import model_probe
    mid, final, part = setup_flow(PAYLOAD_SHA)
    probed = []
    def probe(model_id, **_):
        assert not (tmp_path / "active-model.json").exists()
        assert final.read_bytes() == pattern(0, SIZE) and not part.exists()
        probed.append(model_id)
    monkeypatch.setattr(model_probe, "probe_in_subprocess", probe)
    path = setup.install_recommended_model(mid, cancelled=lambda: False, progress=lambda _: None)
    assert probed == [mid] and path == final
    assert setup.selected_model_id() == mid
    assert not list(tmp_path.glob(".active-model-*"))


def test_failed_probe_after_resume_never_writes_active_model(setup_flow, tmp_path, monkeypatch):
    from core import model_probe
    mid, final, part = setup_flow(PAYLOAD_SHA)
    def probe(*a, **k):
        raise RuntimeError("model_probe_failed")
    monkeypatch.setattr(model_probe, "probe_in_subprocess", probe)
    with pytest.raises(RuntimeError, match="model_probe_failed"):
        setup.install_recommended_model(mid, cancelled=lambda: False, progress=lambda _: None)
    assert not (tmp_path / "active-model.json").exists()


# Teamlead decision: TLS EOF before the current attempt's first body byte ----
# counts as an interruption only while the .part holds bytes from earlier
# attempts; certificate errors are never retried.

def _eof_before_first_byte(where, start, total):
    eof = ssl.SSLEOFError(8, "EOF occurred in violation of protocol (_ssl.c:2427)")
    if where == "handshake":
        raise urllib.error.URLError(eof)
    return FakeResponse(206 if start else 200, start, total, total, fail_at=start, failure=eof)


@pytest.mark.parametrize("where", ["handshake", "read"])
def test_tls_eof_before_first_byte_with_saved_part_is_retried(tmp_path, monkeypatch, hashed, where):
    manager, mid, final, part = make_manager(tmp_path, SIZE, PAYLOAD_SHA)
    part.write_bytes(pattern(0, MIB + 5))      # saved by an earlier attempt
    def handler(call, rng):
        if call == 1:
            return _eof_before_first_byte(where, MIB + 5, SIZE)
        return FakeResponse(206, MIB + 5, SIZE, SIZE)
    server = FakeServer(monkeypatch, handler)
    result, stages = run(manager, mid)
    assert (result.status, result.message) == ("done", "installed")
    assert ("retrying", "connection_interrupted") in stages
    assert server.ranges == [f"bytes={MIB + 5}-", f"bytes={MIB + 5}-"]
    assert final.read_bytes() == pattern(0, SIZE)
    assert hashed == [("model.gguf.part", SIZE)]


def test_tls_eof_before_first_byte_with_saved_part_stays_bounded(tmp_path, monkeypatch):
    manager, mid, final, part = make_manager(tmp_path, SIZE, PAYLOAD_SHA)
    part.write_bytes(pattern(0, 1000))
    server = FakeServer(monkeypatch, lambda call, rng: _eof_before_first_byte("read", 1000, SIZE))
    result, _ = run(manager, mid)
    assert (result.status, result.message) == ("error", "connection_interrupted")
    assert len(server.ranges) == models.DOWNLOAD_ATTEMPTS
    assert part.read_bytes() == pattern(0, 1000) and not final.exists()


@pytest.mark.parametrize("where", ["handshake", "read"])
@pytest.mark.parametrize("partial", ["missing", "empty"])
def test_tls_eof_before_first_byte_without_saved_bytes_is_tls_failed(tmp_path, monkeypatch, where, partial):
    manager, mid, final, part = make_manager(tmp_path, SIZE, PAYLOAD_SHA)
    if partial == "empty":
        part.write_bytes(b"")
    server = FakeServer(monkeypatch, lambda call, rng: _eof_before_first_byte(where, 0, SIZE))
    result, stages = run(manager, mid)
    assert (result.status, result.message) == ("error", "tls_failed")
    assert len(server.ranges) == 1
    assert not any(stage == "retrying" for stage, _ in stages)


@pytest.mark.parametrize("where", ["handshake", "read"])
def test_certificate_error_with_saved_part_is_tls_failed_once(tmp_path, monkeypatch, where):
    manager, mid, final, part = make_manager(tmp_path, SIZE, PAYLOAD_SHA)
    part.write_bytes(pattern(0, MIB + 5))
    cert = ssl.SSLCertVerificationError(1, "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed")
    def handler(call, rng):
        if where == "handshake":
            raise urllib.error.URLError(cert)
        return FakeResponse(206, MIB + 5, SIZE, SIZE, fail_at=MIB + 5, failure=cert)
    server = FakeServer(monkeypatch, handler)
    result, stages = run(manager, mid)
    assert (result.status, result.message) == ("error", "tls_failed")
    assert server.ranges == [f"bytes={MIB + 5}-"]
    assert not any(stage == "retrying" for stage, _ in stages)
    assert part.read_bytes() == pattern(0, MIB + 5) and not final.exists()


def test_tls_eof_helper_ignores_certificate_errors():
    eof = ssl.SSLEOFError(8, "EOF occurred in violation of protocol")
    assert models._is_tls_eof(eof) and models._is_tls_eof(urllib.error.URLError(eof))
    assert models._is_tls_eof(_wrapped_requests_ssl())
    assert models._is_tls_eof(ssl.SSLError(1, "[SSL: UNEXPECTED_EOF_WHILE_READING] unexpected eof while reading"))
    assert not models._is_tls_eof(ConnectionResetError(104, "reset"))
    cert = ssl.SSLCertVerificationError(1, "certificate verify failed")
    assert not models._is_tls_eof(cert) and not models._is_tls_eof(urllib.error.URLError(cert))
    try:
        raise ssl.SSLEOFError(8, "EOF") from cert
    except ssl.SSLEOFError as mixed:
        assert not models._is_tls_eof(mixed)


def test_tls_eof_on_first_read_of_a_200_restart_still_counts_saved_bytes(tmp_path, monkeypatch):
    # .part held bytes when the attempt started; the 200 truncates it, then EOF.
    manager, mid, final, part = make_manager(tmp_path, SIZE, PAYLOAD_SHA)
    part.write_bytes(pattern(0, 1000))
    eof = ssl.SSLEOFError(8, "EOF occurred in violation of protocol")
    def handler(call, rng):
        if call == 1:
            return FakeResponse(200, 0, SIZE, SIZE, fail_at=0, failure=eof)
        return FakeResponse(200, 0, SIZE, SIZE)
    server = FakeServer(monkeypatch, handler)
    result, stages = run(manager, mid)
    assert result.status == "done"
    assert ("retrying", "connection_interrupted") in stages
    assert server.ranges == ["bytes=1000-", None]
    assert final.read_bytes() == pattern(0, SIZE)


# Size cap for catalog entries with a pinned exact size ------------------------

def _size_case(kind):
    if kind == "200_without_length":
        response = FakeResponse(200, 0, SIZE, SIZE)
        del response.headers["Content-Length"]
        return None, response
    if kind == "200_wrong_length":
        return None, FakeResponse(200, 0, SIZE, SIZE, headers={"Content-Length": str(SIZE - 1)})
    if kind == "200_oversend":
        return None, FakeResponse(200, 0, SIZE + 10, SIZE, headers={"Content-Length": str(SIZE)})
    # 206 with a valid Content-Range whose body runs past the pinned size.
    return 1000, FakeResponse(206, 1000, SIZE + 10, SIZE,
                              headers={"Content-Range": f"bytes 1000-{SIZE - 1}/{SIZE}"})


@pytest.mark.parametrize("kind", ["200_without_length", "200_wrong_length", "200_oversend", "206_oversend"])
def test_pinned_size_is_enforced_and_part_is_deleted(tmp_path, monkeypatch, kind):
    manager, mid, final, part = make_manager(tmp_path, SIZE, PAYLOAD_SHA)
    saved, response = _size_case(kind)
    if saved:
        part.write_bytes(pattern(0, saved))
    written = []
    server = FakeServer(monkeypatch, lambda call, rng: response)
    result = manager.install(mid, allow_download=True,
                             progress_cb=lambda p: written.append(p.bytes_done))
    assert (result.status, result.message) == ("error", "download_size_mismatch")
    assert len(server.ranges) == 1                      # fixed code, no retry
    assert not part.exists() and not final.exists()
    assert max(written) <= SIZE                         # nothing beyond the pin hit the disk


def test_size_cap_needs_a_pinned_size(tmp_path, monkeypatch):
    # Legacy entries without size_exact keep the old behaviour (SHA is the guard).
    manager, mid, final, part = make_manager(tmp_path, SIZE, PAYLOAD_SHA, exact=False)
    response = FakeResponse(200, 0, SIZE, SIZE)
    del response.headers["Content-Length"]
    FakeServer(monkeypatch, lambda call, rng: response)
    result, _ = run(manager, mid)
    assert result.status == "done"


def test_setup_text_understands_size_mismatch():
    from desktop.i18n import tr
    from desktop.widgets.model_setup_panel import model_failure_text
    assert model_failure_text(RuntimeError("download_size_mismatch")) == tr("setup.model.error.response")
    assert models.download_failure_code(ValueError("download_size_mismatch")) == "download_size_mismatch"
    assert not models._retryable_download_error(ValueError("download_size_mismatch"))
