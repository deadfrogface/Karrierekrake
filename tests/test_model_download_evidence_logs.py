"""The app's own log proves a resume: Range sent, 206 offset, host, SHA, activation.

Offline: ``urlopen`` is replaced by a fake that redirects to a CDN host with a
signed query string, drops the body mid-file and answers the resume with 206.
"""
import hashlib
import http.client
import logging
import os

import pytest

from guenther import model_manager as models
from guenther import setup_models as setup

TOTAL = 3 * 1024 * 1024 + 17
DROP_AT = 1_234_567  # odd, not a multiple of the 1 MiB read size
DATA = bytes((i * 31 + 7) % 256 for i in range(TOTAL))
SHA = hashlib.sha256(DATA).hexdigest()
CDN = "https://cdn.example.test/blob?X-Amz-Signature=SECRET123&Expires=1"


class Resp:
    def __init__(self, status, start, fail_at=None):
        self.status, self.pos, self.fail_at = status, start, fail_at
        self.headers = {"Content-Length": str(TOTAL - start)}
        if status == 206:
            self.headers["Content-Range"] = f"bytes {start}-{TOTAL - 1}/{TOTAL}"

    def geturl(self):
        return CDN

    def read(self, size=-1):
        if self.fail_at is not None and self.pos >= self.fail_at:
            raise http.client.IncompleteRead(b"", TOTAL - self.pos)
        limit = TOTAL if self.fail_at is None else self.fail_at
        chunk = DATA[self.pos:min(limit, self.pos + size)]
        self.pos += len(chunk)
        return chunk

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def fake_net(monkeypatch, tmp_path):
    monkeypatch.setattr(models, "DOWNLOAD_RETRY_DELAY", 0)
    ranges = []

    def urlopen(req, **kwargs):
        rng = req.get_header("Range")
        ranges.append(rng)
        if rng is None:
            return Resp(200, 0, fail_at=DROP_AT)
        return Resp(206, int(rng[len("bytes="):-1]))

    monkeypatch.setattr(models.urllib.request, "urlopen", urlopen)
    entry = dict(setup.SETUP_MODEL_CATALOG["qwen3.5-4b-gsq"], approx_bytes=TOTAL, sha256=SHA,
                 filename="m.gguf", url="https://huggingface.co/org/repo/resolve/abc/m.gguf")
    monkeypatch.setitem(setup.SETUP_MODEL_CATALOG, "evidence-test", entry)
    monkeypatch.setenv("KARRIEREKRAKE_MODELS_DIR", str(tmp_path / "models"))
    monkeypatch.setattr(models.ModelManager, "disk_free_bytes", lambda self: 10**13)
    return ranges


def test_resume_evidence_is_in_app_log_in_order(fake_net, monkeypatch, caplog, tmp_path):
    root = tmp_path / "models"
    order = []
    import core.model_probe as probe
    monkeypatch.setattr(probe, "probe_in_subprocess",
                        lambda mid, cancelled: order.append(("probe", (root / "active-model.json").exists())))
    with caplog.at_level(logging.INFO, logger="karrierekrake"):
        setup.install_recommended_model("evidence-test", cancelled=lambda: False, progress=lambda p: None)
    lines = [r.getMessage() for r in caplog.records if r.name.startswith("karrierekrake")]
    text = "\n".join(lines)

    retry = next(line for line in lines if "model_download_retry" in line)
    assert "'part_bytes': %d" % DROP_AT in retry
    assert "'reason': 'connection_interrupted'" in retry
    assert f"'range': 'bytes={DROP_AT}-'" in text
    assert "'host': 'huggingface.co'" in text
    resume = [line for line in lines if "model_download_response" in line and "'status': 206" in line]
    assert len(resume) == 1
    assert f"'content_range': 'bytes {DROP_AT}-{TOTAL - 1}/{TOTAL}'" in resume[0]
    assert f"'part_bytes': {DROP_AT}" in resume[0]
    assert "'final_host': 'cdn.example.test'" in resume[0]
    assert f"'size': {TOTAL}, 'expected_size': {TOTAL}, 'sha256': '{SHA}'" in text
    names = [n for line in lines for n in ("model_download_verified", "model_probe_passed",
                                           "model_activated") if f"guenther.{n} " in line]
    assert names == ["model_download_verified", "model_probe_passed", "model_activated"]
    assert order == [("probe", False)]
    assert (root / "active-model.json").exists()
    # Signed CDN URLs and paths never reach the log.
    assert "SECRET123" not in text and "X-Amz" not in text and "/resolve/" not in text
    assert str(root) not in text


def test_request_log_has_no_range_on_first_attempt(fake_net, caplog, tmp_path):
    manager = models.ModelManager(tmp_path / "models")
    with caplog.at_level(logging.INFO, logger="karrierekrake"):
        result = manager.install("evidence-test", allow_download=True)
    assert result.status == "done"
    requests_logged = [r.getMessage() for r in caplog.records if "model_download_request" in r.getMessage()]
    assert "'range': '', 'part_bytes': 0" in requests_logged[0]
    assert f"'range': 'bytes={DROP_AT}-', 'part_bytes': {DROP_AT}" in requests_logged[1]
    assert fake_net == [None, f"bytes={DROP_AT}-"]
