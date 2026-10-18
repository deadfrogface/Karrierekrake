"""A restart decision empties the .part at once, so a retry starts at byte 0.

Regression: after a 416 or an unusable 206 Content-Range the stale .part was
only truncated once the next response was opened for writing. A short
transient failure of the restarted request in between (timeout, TLS EOF,
503) made the next attempt send Range from the old offset again; with the
restart budget already spent that ended in http_416/invalid_download_range.

Offline: ``urlopen`` is replaced by a fake that records every Range header.
"""
import hashlib
import ssl
import urllib.error
from pathlib import Path

import pytest

from guenther import model_manager as models

MIB = 1024 * 1024
SIZE = 2 * MIB + 33
DATA = bytes((i * 13 + 5) % 251 for i in range(SIZE))
SHA = hashlib.sha256(DATA).hexdigest()
STALE = 1000


@pytest.fixture(autouse=True)
def fast_retry(monkeypatch):
    monkeypatch.setattr(models, "DOWNLOAD_RETRY_DELAY", 0)


class Resp:
    def __init__(self, status, start, *, headers=None, fail_at=None, failure=None):
        self.status, self.pos = status, start
        self.fail_at, self.failure = fail_at, failure
        self.headers = {"Content-Length": str(SIZE - start), **(headers or {})}
        if status == 206:
            self.headers.setdefault("Content-Range", f"bytes {start}-{SIZE - 1}/{SIZE}")

    def read(self, size=-1):
        if self.fail_at is not None and self.pos >= self.fail_at:
            raise self.failure
        limit = SIZE if self.fail_at is None else self.fail_at
        chunk = DATA[self.pos:min(limit, self.pos + size)]
        self.pos += len(chunk)
        return chunk

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def make_manager(tmp_path):
    mid = models.PRODUCTION_MODEL_ID
    entry = {"filename": "model.gguf", "url": "https://example.test/model.gguf",
             "sha256": SHA, "approx_bytes": SIZE, "size_exact": True}
    manager = models.ModelManager(tmp_path / "models", catalog={mid: entry})
    manager.disk_free_bytes = lambda: 10**13
    final = manager.model_path(mid)
    final.parent.mkdir(parents=True, exist_ok=True)
    part = final.with_suffix(".gguf.part")
    part.write_bytes(b"\xee" * STALE)  # stale bytes the server will not resume
    return manager, mid, final, part


@pytest.fixture
def watch(monkeypatch):
    """Records each request's Range plus .part sizes at request and restart time."""
    state = {"ranges": [], "part_at_request": [], "part_at_restart": [], "restarts": [],
             "hashed": [], "part": None, "handler": None}

    def urlopen(req, **kwargs):
        part = state["part"]
        state["ranges"].append(req.get_header("Range"))
        state["part_at_request"].append(part.stat().st_size if part.is_file() else None)
        return state["handler"](len(state["ranges"]), req.get_header("Range"))

    real_log = models.log_event

    def log_event(event, **fields):
        if event == "model_download_restart":
            part = state["part"]
            state["restarts"].append(fields.get("reason"))
            state["part_at_restart"].append(part.stat().st_size if part.is_file() else None)
        return real_log(event, **fields)

    real_sha = models.sha256_file

    def sha256_file(path, **kwargs):
        state["hashed"].append((Path(path).name, Path(path).stat().st_size))
        return real_sha(path, **kwargs)

    monkeypatch.setattr(models.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(models, "log_event", log_event)
    monkeypatch.setattr(models, "sha256_file", sha256_file)
    return state


def _http(code):
    return urllib.error.HTTPError("https://example.test", code, "x", {}, None)


TRANSIENT = {
    "timeout": lambda: urllib.error.URLError(TimeoutError("timed out")),
    "ssl_eof": lambda: urllib.error.URLError(
        ssl.SSLEOFError(8, "EOF occurred in violation of protocol (_ssl.c:2427)")),
    "http_503": lambda: _http(503),
}

UNUSABLE_FIRST = {
    "http_416": (lambda: (_ for _ in ()).throw(_http(416)), "http_416"),
    "bad_content_range": (lambda: Resp(206, STALE, headers={
        "Content-Range": f"bytes {STALE + 1}-{SIZE - 1}/{SIZE}"}), "invalid_download_range"),
}


@pytest.mark.parametrize("first", list(UNUSABLE_FIRST))
@pytest.mark.parametrize("transient", list(TRANSIENT))
def test_restart_truncates_part_before_a_transient_failure(tmp_path, watch, first, transient):
    manager, mid, final, part = make_manager(tmp_path)
    watch["part"] = part
    answer, reason = UNUSABLE_FIRST[first]

    def handler(call, rng):
        if call == 1:
            assert rng == f"bytes={STALE}-"
            return answer()
        if call == 2:   # restarted request fails briefly before any body byte
            raise TRANSIENT[transient]()
        return Resp(200, 0)

    watch["handler"] = handler
    stages = []
    result = manager.install(mid, allow_download=True,
                             progress_cb=lambda p: stages.append((p.status, p.message)))
    assert (result.status, result.message) == ("done", "installed")
    # Only the first request resumes; every request after the restart starts at 0.
    assert watch["ranges"] == [f"bytes={STALE}-", None, None]
    assert watch["restarts"] == [reason]
    # The .part is empty right at the restart decision, not only once rewritten.
    assert watch["part_at_restart"] == [0]
    assert watch["part_at_request"] == [STALE, 0, 0]
    assert any(status == "retrying" for status, _ in stages)
    assert final.read_bytes() == DATA and not part.exists()
    assert watch["hashed"] == [("model.gguf.part", SIZE)]


@pytest.mark.parametrize("first", list(UNUSABLE_FIRST))
def test_restart_budget_still_ends_after_a_second_unusable_answer(tmp_path, watch, first):
    """Truncation does not widen the budget: a fresh download that later breaks
    and is answered unusably again still fails clearly."""
    manager, mid, final, part = make_manager(tmp_path)
    watch["part"] = part
    reason = UNUSABLE_FIRST[first][1]
    eof = ssl.SSLEOFError(8, "EOF occurred in violation of protocol")

    def handler(call, rng):
        if rng is None:
            return Resp(200, 0, fail_at=MIB + 5, failure=eof)
        if first == "http_416":
            raise _http(416)
        start = int(rng[len("bytes="):-1])
        return Resp(206, start, headers={"Content-Range": f"bytes {start + 1}-{SIZE - 1}/{SIZE}"})

    watch["handler"] = handler
    result = manager.install(mid, allow_download=True)
    assert (result.status, result.message) == ("error", reason)
    assert watch["ranges"] == [f"bytes={STALE}-", None, f"bytes={MIB + 5}-"]
    assert watch["part_at_restart"] == [0]
    assert not final.exists()


def test_200_on_resume_keeps_the_restart_for_a_later_416(tmp_path, watch):
    """A 200 on a resume request overwrites from byte 0 and consumes no restart."""
    manager, mid, final, part = make_manager(tmp_path)
    watch["part"] = part
    eof = ssl.SSLEOFError(8, "EOF occurred in violation of protocol")

    def handler(call, rng):
        if call == 1:
            return Resp(200, 0, fail_at=MIB + 5, failure=eof)
        if call == 2:
            raise _http(416)
        return Resp(200, 0)

    watch["handler"] = handler
    result = manager.install(mid, allow_download=True)
    assert (result.status, result.message) == ("done", "installed")
    assert watch["ranges"] == [f"bytes={STALE}-", f"bytes={MIB + 5}-", None]
    assert watch["restarts"] == ["http_416"]
    assert watch["part_at_restart"] == [0]
    assert final.read_bytes() == DATA
