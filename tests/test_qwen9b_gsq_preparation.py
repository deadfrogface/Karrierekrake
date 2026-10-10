from __future__ import annotations

import hashlib
import io
from pathlib import Path

import pytest

from core.security.model_integrity import ModelIntegrityError
from scripts import prepare_qwen9b_gsq_candidate as candidate


def fixture_meta(data: bytes) -> dict:
    return {"id": "test-candidate", "filename": "test.gguf", "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(), "rco_verified": False,
            "source_repo": "test/model", "revision": "pinned"}


def test_require_rco_blocks_before_download(tmp_path, monkeypatch):
    def unexpected(*args, **kwargs):
        pytest.fail("must not request a GSQ-only artifact when RCO is required")
    monkeypatch.setattr(candidate.urllib.request, "urlopen", unexpected)
    with pytest.raises(ModelIntegrityError, match="gsq_rco_artifact_unavailable"):
        candidate.prepare(tmp_path, fixture_meta(b"GGUFtest"), download=True, require_rco=True)
    assert not list(tmp_path.iterdir())


def test_download_checks_hash_and_cleans_partial(tmp_path, monkeypatch):
    data = b"GGUFexpected"
    monkeypatch.setattr(candidate.urllib.request, "urlopen", lambda *a, **k: io.BytesIO(b"GGUFtampered"))
    with pytest.raises(ModelIntegrityError, match="checksum_mismatch"):
        candidate.prepare(tmp_path, fixture_meta(data), download=True)
    assert not list(tmp_path.rglob("*.part"))
    assert not list(tmp_path.rglob("*.gguf"))


def test_pinned_download_and_offline_verify(tmp_path, monkeypatch):
    data = b"GGUFtest"
    requests = []
    def download(request, **kwargs):
        requests.append(request.full_url)
        return io.BytesIO(data)
    monkeypatch.setattr(candidate.urllib.request, "urlopen", download)
    meta = fixture_meta(data)
    path = candidate.prepare(tmp_path, meta, download=True)
    assert path.read_bytes() == data
    assert "/resolve/pinned/test.gguf" in requests[0]
    assert candidate.prepare(tmp_path, meta) == path
    assert len(requests) == 1


def test_existing_corrupt_file_is_preserved_and_rejected(tmp_path):
    meta = fixture_meta(b"GGUFtest")
    path = tmp_path / meta["id"] / meta["filename"]
    path.parent.mkdir()
    path.write_bytes(b"GGUFfake")
    with pytest.raises(ModelIntegrityError, match="checksum_mismatch"):
        candidate.prepare(tmp_path, meta)
    assert path.read_bytes() == b"GGUFfake"
